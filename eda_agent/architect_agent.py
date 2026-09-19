from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from agentscope.memory import InMemoryMemory
from agentscope.message import Msg
from pydantic import BaseModel, field_validator

from .agents import SafeReActAgent, clear_memory_safely
from .config import OpenAIConfig
from .model import make_formatter, make_openai_model
from .prompts import ORDER_PROMPT
from .utils import extract_json_object


#: The one definition of `latency_cycles`, quoted verbatim into every prompt
#: that mentions the field. It had four wordings across `architect_agent`,
#: `contract_linter`, `rtl_generator` and `refmodel/agent`, and four wordings
#: are four fields.
LATENCY_DEFINITION = """\
`timing.<output>.latency_cycles` is the number of edges of the DECLARED CLOCK
between the edge that captures a stimulus and the edge on which <output> first
reflects it. Edges of the declared clock -- not enable ticks: a design whose FSM
advances on a prescaled `clk_en` takes more clock edges than phases, and that is
not a violation of a declared latency, it is what a prescaler is.

Give the field ONLY when the specification states the count, or when the
interface makes it observable from outside (a valid/ready/done/ack output tells
a consumer when to look). If neither holds, OMIT the field. An omitted latency
says "the specification does not determine this", which is true and harmless. A
guessed one is read downstream as a requirement, and a requirement nobody can
check against the specification is a fiction the design is then forced to
implement."""


SYSTEM_PROMPT = r"""
You are Architect, a senior hardware design lead for SystemVerilog RTL.

Goal: turn an ambiguous natural-language spec into a precise, testable "contract"
that other agents (Verifier, Coder, Debugger, Formal) will follow.

Principles:
- Be concrete: define timing/latency, reset behavior, and edge semantics when possible.
- If the spec is ambiguous, pick the smallest reasonable assumption and record it explicitly.
- Never change the interface unless the spec (or golden testbench) demands it.
- Keep the contract compact and machine-usable.
- IMPORTANT: In contract-only mode, downstream agents will treat the contract as the ONLY source of truth.
  Therefore, the contract must be complete (interface, timing, corner cases) and internally consistent.

Toolchain note:
- The simulation harness uses Verilator. When adding verifier guidance, prefer procedural checks or simple assertions
  (avoid requiring advanced SVA features that may not be supported).
"""


CONTRACT_PROMPT = r"""
Create a design contract for the DUT described in <input_spec>.

The contract will be consumed by:
- Verifier: generates a testbench consistent with the contract
- Coder: writes RTL consistent with the contract
- Debugger: fixes RTL while preserving the contract
- Formal: generates miter/spec properties from the contract

Requirements:
1) Output MUST be a single valid JSON object (no extra text).
2) Write everything in English.
3) Prefer facts from the spec. If ambiguous, add an explicit assumption.
4) If <golden_testbench> is provided, treat its interface/timing expectations as ground truth and align the contract to it.

What to include (keep it compact):
- source_of_truth: "spec" or "golden_tb"
- module_name: usually "TopModule" unless spec/golden TB indicates otherwise
- parameters: list of module parameters EXACTLY as the spec/golden TB declares them
  (each: name, default value, and type/notes when known). Include every parameter
  the interface declares — even ones derived from another (e.g. M = clog2(N));
  if the golden TB overrides a name via #(.NAME(...)) or positional #(...), that
  name MUST appear here. Use [] only if the module genuinely has no parameters.
- io: concise list of ports with direction and bit width when known.
  For every INPUT, give `idle_value` when its quiescent level is not 0 — the
  value the port holds when nothing is asking the design to do anything. An
  active-low input (`req_n`, `cs_n`, `oe_b`) idles at 1. An open-drain or
  wired-AND bus input (I2C `scl_i`/`sda_i`, a shared interrupt line) idles at 1,
  because the pull-up wins when nobody drives it. Omit it for an ordinary
  active-high input; 0 is the default and is right for most ports.
  This is not cosmetic. The testbench drives every input to its idle value
  before releasing reset so that the design and its reference model start from
  the same defined state. Get it wrong and the two begin disagreeing before the
  first stimulus, and a design that samples a bus you have declared to idle low
  will be marked broken for behaving correctly.
- clocking: whether sequential; clock/reset names and edge semantics if applicable
- timing: per-output latency, for the outputs whose latency the SPECIFICATION
  determines. Omit the entry otherwise.
{latency_definition}
  State the MINIMUM latency the function inherently needs — do not add pipeline
  stages the behaviour does not require. Prose suggesting a
  pipeline is a permission, not a requirement — it never overrides an interface
  that cannot signal completion.
- functional_summary: 3-8 bullets describing behavior precisely
- corner_cases: 3-8 bullets (overflows, resets, illegal inputs, boundary indices, etc.)
- test_plan: 5-10 bullets of directed tests the Verifier should include
- guidance:
  - verifier: TB guidance (sampling edge, latency handling, reset sequencing)
  - coder: RTL guidance (structure, state, arithmetic width, initialization)
  - debugger: common failure patterns to check first

<input_spec>
{input_spec}
</input_spec>

{golden_tb_block}
"""

REVISE_CONTRACT_PROMPT = r"""
Revise the contract below to fix the reported lint errors.

Hard rules:
- Output MUST be a single valid JSON object (no extra text).
- Do NOT invent new ports unless required by the spec/golden TB.
- Keep module_name, parameters and io consistent with the golden testbench when provided.
- In contract-only mode, all downstream agents will follow this contract strictly.

Lint errors:
{lint_errors}

Original spec (for context only; contract is the deliverable):
<input_spec>
{input_spec}
</input_spec>

Current contract:
<contract_json>
{contract_json}
</contract_json>

{golden_tb_block}
"""

EXAMPLE_OUTPUT: Dict[str, Any] = {
    "source_of_truth": "spec",
    "module_name": "TopModule",
    "parameters": [
        {"name": "WIDTH", "default": "8", "type": "int", "notes": "data bit-width"},
    ],
    "io": [
        {"name": "clk", "dir": "input", "width": 1, "notes": "posedge clock"},
        {"name": "reset", "dir": "input", "width": 1, "notes": "active-high synchronous reset"},
        {"name": "in_", "dir": "input", "width": "WIDTH", "notes": ""},
        {"name": "req_n", "dir": "input", "width": 1, "idle_value": 1,
         "notes": "active low: asserted when 0"},
        {"name": "out", "dir": "output", "width": "WIDTH", "notes": "registered output"},
    ],
    "clocking": {
        "is_sequential": True,
        "clock": {"name": "clk", "edge": "posedge"},
        "reset": {"name": "reset", "active": "high", "type": "synchronous"},
    },
    "timing": {"out": {"latency_cycles": 1, "notes": "output updates on next cycle"}},
    "functional_summary": [
        "On each rising edge, register the input.",
        "Output equals (registered input + 1) modulo 2^8.",
    ],
    "corner_cases": ["Reset behavior on first active clock edge.", "Overflow wraps around."],
    "test_plan": [
        "Reset then verify known outputs.",
        "Random inputs; check one-cycle latency.",
        "Overflow case at max value.",
    ],
    "guidance": {
        "verifier": [
            "Sample outputs on the opposite edge to avoid race (if posedge sequential, check at negedge).",
            "Where the contract declares no latency for an output, do not assume one.",
        ],
        "coder": [
            "Match the exact port list and names.",
            "Use always_ff/always_comb or equivalent; keep widths explicit.",
        ],
        "debugger": [
            "First check off-by-one-cycle issues and reset polarity/type.",
            "Check signed/unsigned and bit-width truncation.",
        ],
    },
}



class TimingSpec(BaseModel):
    """One output's timing, typed rather than an untyped bag.

    `timing` was `Dict[str, Any]`, so nothing at the boundary distinguished a
    considered figure from a typo -- and because a validation failure anywhere
    in `ContractFormat` falls back to a stub contract with `timing={}`, a single
    malformed entry could silently take the whole contract down with it.

    `latency_cycles` is OPTIONAL, and that is the substantive change. The
    architect used to be told that where the spec names no count and the
    interface carries no completion signal it should "choose 0 or 1" -- an
    instruction to invent a number in exactly the case where nothing can check
    it. On `i2c_master_bit_ctrl` that produced 3 in one run of the same spec and
    1 in the next, against a golden design that takes 5 `clk_en` phases. The
    field gated a reference-model check (G4e), set the testbench's stimulus
    pacing, and picked the model's dispatch, so an unstable guess perturbed all
    three. It now informs the RTL agent and gates nothing.
    """

    model_config = {"extra": "allow"}

    latency_cycles: Optional[int] = None
    notes: str = ""

    @field_validator("latency_cycles", mode="before")
    @classmethod
    def _only_a_usable_count(cls, value: Any) -> Optional[int]:
        """A value that is not a cycle count degrades to absent, not to a stub.

        Typing the field is only an improvement if a bad value costs less than
        it did before. It cannot cost MORE: `ContractFormat.model_validate`
        raising anywhere means `parse_output` returns a stub contract with no
        io, no clocking and `timing={}`, so one nonsense latency would take the
        whole interface down with it. Degrading to `None` says "the count is not
        determined", which is now a first-class answer and is no worse than the
        truth. `contract_linter` still reports an invalid value on a contract
        read from disk, which is the path that never passes through here.
        """
        if value is None or isinstance(value, bool):
            return None
        try:
            cycles = int(value)
        except (TypeError, ValueError):
            return None
        return cycles if cycles >= 0 else None


class ContractFormat(BaseModel):
    source_of_truth: str
    module_name: str
    parameters: List[Dict[str, Any]] = []
    io: List[Dict[str, Any]]
    clocking: Dict[str, Any]
    timing: Dict[str, TimingSpec] = {}

    @field_validator("timing", mode="before")
    @classmethod
    def _drop_unusable_entries(cls, value: Any) -> Any:
        """Same containment one level up: a bad ENTRY costs its entry, not the contract."""
        if not isinstance(value, dict):
            return {}
        return {k: v for k, v in value.items() if isinstance(v, dict)}
    functional_summary: List[str]
    corner_cases: List[str]
    test_plan: List[str]
    guidance: Dict[str, Any]
    # Orchestrator-supplied SVA contract: a first-class peer of io/parameters.
    # Threaded into ALL downstream agents alongside the interface.  Dual-role:
    # (a) spec input — generation aims to satisfy these properties;
    # (b) golden reference — the Asserter binds them as ``assert property``.
    # None when Veri-Sure runs standalone (no orchestrator).
    contract_sva: Optional[List[Dict[str, Any]]] = None


class ArchitectAgent:
    def __init__(self, cfg: OpenAIConfig) -> None:
        self._cfg = cfg
        self._agent = SafeReActAgent(
            name="Architect",
            sys_prompt=SYSTEM_PROMPT,
            model=make_openai_model(cfg, cache_key="architect"),
            formatter=make_formatter(cfg.model),
            memory=InMemoryMemory(),
            max_iters=10,
        )
        self.last_prompt: str = ""
        self.last_raw_output: str = ""

    def reset(self) -> None:
        clear_memory_safely(self._agent)

    def _read_golden_tb_excerpt(self, golden_tb_path: str, *, max_chars: int = 6000) -> str:
        try:
            text = Path(golden_tb_path).read_text(encoding="utf-8")
        except Exception:  # noqa: BLE001
            return ""
        text = text.strip()
        if not text:
            return ""
        if len(text) > max_chars:
            text = text[:max_chars] + "\n/* ... truncated ... */\n"
        return text + ("\n" if not text.endswith("\n") else "")

    def parse_output(self, response_text: str) -> ContractFormat:
        try:
            obj: Dict[str, Any] = extract_json_object(response_text)
            return ContractFormat.model_validate(obj)
        except Exception as e:  # noqa: BLE001
            # Keep the failure visible while still returning a valid object shape.
            return ContractFormat(
                source_of_truth="spec",
                module_name="TopModule",
                parameters=[],
                io=[],
                clocking={},
                timing={},
                functional_summary=[f"Contract parse error: {type(e).__name__}: {e}"],
                corner_cases=[],
                test_plan=[],
                guidance={"verifier": [], "coder": [], "debugger": []},
            )

    async def chat(self, input_spec: str, *, golden_tb_path: Optional[str] = None) -> ContractFormat:
        self.reset()

        golden_tb_block = ""
        if golden_tb_path:
            excerpt = self._read_golden_tb_excerpt(golden_tb_path)
            if excerpt:
                golden_tb_block = f"<golden_testbench>\n{excerpt}</golden_testbench>\n"

        prompt = CONTRACT_PROMPT.format(
            input_spec=input_spec, golden_tb_block=golden_tb_block,
            latency_definition=LATENCY_DEFINITION,
        )
        order = ORDER_PROMPT.format(output_format=json.dumps(EXAMPLE_OUTPUT, indent=4))
        full_prompt = f"{prompt}\n\n{order}"
        self.last_prompt = full_prompt
        msg = await self._agent(Msg("user", full_prompt, role="user"))
        text = msg.get_text_content() or ""
        self.last_raw_output = text
        return self.parse_output(text)

    async def revise_contract(
        self,
        *,
        input_spec: str,
        contract_json: str,
        lint_errors: str,
        golden_tb_path: Optional[str] = None,
    ) -> ContractFormat:
        self.reset()

        golden_tb_block = ""
        if golden_tb_path:
            excerpt = self._read_golden_tb_excerpt(golden_tb_path)
            if excerpt:
                golden_tb_block = f"<golden_testbench>\n{excerpt}</golden_testbench>\n"

        prompt = REVISE_CONTRACT_PROMPT.format(
            input_spec=input_spec,
            contract_json=contract_json,
            lint_errors=lint_errors.strip(),
            golden_tb_block=golden_tb_block,
        )
        order = ORDER_PROMPT.format(output_format=json.dumps(EXAMPLE_OUTPUT, indent=4))
        full_prompt = f"{prompt}\n\n{order}"
        self.last_prompt = full_prompt
        msg = await self._agent(Msg("user", full_prompt, role="user"))
        text = msg.get_text_content() or ""
        self.last_raw_output = text
        return self.parse_output(text)
