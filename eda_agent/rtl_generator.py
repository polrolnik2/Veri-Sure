from __future__ import annotations

import asyncio
import json
import re
from typing import List, Optional, Tuple

from agentscope.memory import InMemoryMemory
from agentscope.message import Msg
from pydantic import BaseModel

from .agents import SafeReActAgent, clear_memory_safely
from .config import OpenAIConfig
from .model import make_formatter, make_openai_model
from .prompts import (
    FAILED_TRIAL_PROMPT,
    GLUE_4_SHOT_EXAMPLES,
    GLUE_PORT_CHECKLIST_PROMPT,
    RTL_4_SHOT_EXAMPLES,
    TAG_ORDER_PROMPT,
)
from .sim_reviewer import check_syntax
from .utils import add_lineno, clip_text, extract_xml_tag, strip_markdown_code_fences

SYSTEM_PROMPT = r"""
You are Coder, an expert in RTL design.

You write clean, synthesizable, syntactically-correct SystemVerilog RTL that matches the Architect's contract.

Toolchain note:
- The harness uses Verilator. Keep RTL compatible with Verilator (standard synthesizable SystemVerilog).

Contract-only mode:
- Treat <contract_json> as the ONLY source of truth for interface/timing/behavior.
- <input_spec> and any testbench text are non-authoritative background and must NOT override the contract.

Contract SVA mode:
- If the contract JSON contains a `contract_sva` field (a list of SVA property objects),
  these are **orchestrator-supplied assertions** that your RTL MUST satisfy.
- Each property describes a behavioural guarantee (e.g. reset behaviour, latency, functional invariants).
- Write RTL that makes every contract_sva property pass when bound as `assert property`.

Child assumes mode (hierarchical decomposition):
- If the contract JSON contains a `child_assumes` field (a dict keyed by child module name),
  this node is a COMPOSITION NODE with child-facing PORTS.
- The child-facing ports are ALREADY listed in the contract's `io` section (prefixed
  with the child module name: child `foo`'s port `ready` is the port `foo_ready`).
- DO NOT instantiate child modules. The children connect externally via ports.
- Your RTL implements the GLUE LOGIC that wires the external ports to the
  child-facing ports, adding any FSM/mux/pipeline logic needed so that the
  parent's contract_sva properties hold, given that the child-facing ports
  behave according to the child's assumed behavior.
- Each child entry has `io_behavior` (a BLACK-BOX description of observable
  input->output behavior), `timing` (latency per output), `corner_cases`, and
  `properties` (formal SVA). Read `io_behavior`/`timing`/`corner_cases` to
  understand what the child actually does end-to-end at its INTERFACE — the
  formal `properties` alone are often a sparse, partial view and are not
  sufficient by themselves to design correct glue logic (e.g. sequencing,
  when to drive a child's control inputs, what order outputs become valid).
- Do NOT use the child's own `functional_summary` field (if present elsewhere
  in the contract) to reason about the child's behavior — it describes that
  child's INTERNAL implementation for its own RTL writer, not its observable
  interface contract. Use `io_behavior` instead.
- Think of child-facing ports as a contracted interface: the child guarantees
  the behavior in its io_behavior/timing/properties, and your glue logic uses
  them to satisfy the parent's own assertions.
- GAP ANALYSIS: the contract's `functional_summary` for a composition node
  states what the ORIGINAL (pre-decomposition) requirement was, alongside what
  each child guarantees. Do not treat this module as pure port-forwarding by
  default — actively identify anything the original requirement needs that no
  child's guarantee covers (sequencing/launch order, arbitrating between
  children, combining two children's outputs, holding or latching a result
  across cycles that no child holds, translating between representations no
  child mentions). That residual behavior must be IMPLEMENTED here as
  FSM/mux/register logic, not assumed to fall out of wiring.
"""


# A composition node and a leaf have OPPOSITE success criteria: a leaf is
# rewarded for implementing behaviour, a glue module is REJECTED for it.
# Multiplexing both through one system prompt with an `if child_assumes`
# paragraph is what produced an 85K-char glue prompt carrying four monolithic
# exemplars and ~11 mentions of glue guidance. This is the composition-node
# system prompt; it states the inverted objective first, not as a caveat.
GLUE_SYSTEM_PROMPT = r"""
You are Coder, writing the GLUE module of a hierarchical composition.

Your module does NOT implement the design's function. Its children already do.
Your only job is to WIRE them: route external inputs to child-facing inputs,
route child-facing outputs to external outputs and to sibling children, and add
the minimum reconciliation logic (registers, muxes, qualifiers, small FSMs)
needed for the parent's contract_sva to hold.

The single most common failure in this role is writing a correct-looking module
that recomputes what a child already produces, leaving the child's output ports
unread. That is called VESTIGIAL GLUE. It is detected mechanically and rejected
before simulation, no matter how good the RTL is. Every child-facing INPUT port
must be read.

Toolchain note:
- The harness uses Verilator. Keep RTL compatible with Verilator (standard
  synthesizable SystemVerilog).

Contract-only mode:
- Treat <contract_json> as the ONLY source of truth for interface/timing/behavior.
- <input_spec> and any testbench text are non-authoritative background and must
  NOT override the contract.

Contract SVA mode:
- `contract_sva` properties are orchestrator-supplied assertions your glue MUST
  satisfy, given the children behave as their `child_assumes` entries describe.

Reading the children:
- `child_assumes` is a dict keyed by child module name. Child-facing ports are
  ALREADY in the contract `io`, prefixed with the child module name
  (child `foo`'s output `y` is the port `foo_y`).
- DO NOT instantiate child modules. They are connected externally via ports.
- Use each child's `io_behavior`, `timing` and `corner_cases` to determine WHEN
  its outputs are valid and HOW to sequence its control inputs. The formal
  `properties` alone are a sparse, partial view and are not sufficient to design
  correct glue.
- Do NOT use a child's `functional_summary` — it describes that child's INTERNAL
  implementation for its own RTL writer, not its observable interface.
"""


def _is_composition_contract(contract_json: str) -> bool:
    """True when this coder call is for a GLUE node rather than a leaf.

    Keyed on `child_assumes`, the same field the orchestrator injects and the
    vestigial-glue checker keys on, so prompt selection and rejection criteria
    cannot drift apart.
    """
    if not contract_json:
        return False
    try:
        obj = json.loads(contract_json)
    except (ValueError, TypeError):
        return "child_assumes" in contract_json
    return bool(isinstance(obj, dict) and obj.get("child_assumes"))


PARSE_REPAIR_PROMPT = r"""
Your previous response could not be parsed by the program.

Parser error:
{parse_error}

Previous response (truncated):
<bad_output>
{bad_output}
</bad_output>

Please output again, strictly following the required tags in <output_format>, and output NOTHING else.
Do NOT output JSON. Do NOT wrap code in Markdown code fences (```).

The <bad_output> above is shown ONLY so you can see what failed to parse. It is
not a draft to tidy up. If it describes a different module than the contract
above -- different module name, different ports -- discard it completely and
write the contract's module from scratch. Re-read the contract and confirm the
module name and every port name match it before you answer.
"""

PLACEHOLDER_REPAIR_PROMPT = r"""
Your previous response does not look like a real implementation attempt: {reason}

The contract JSON was already provided to you at the start of this conversation and is repeated below for reference -- it is NOT missing.

<contract_json>
{contract_json}
</contract_json>

Write the ACTUAL RTL module implementing this contract now. Do NOT output a placeholder, a stub, or a request for more information -- implement the real module per the contract above.

Previous response (truncated):
<bad_output>
{bad_output}
</bad_output>

Please output again, strictly following the required tags in <output_format>, and output NOTHING else.
Do NOT output JSON. Do NOT wrap code in Markdown code fences (```).
"""

GENERATION_PROMPT = r"""
Write a complete SystemVerilog RTL module that implements the DUT.

Hard rules:
- Follow the Architect contract strictly. Do NOT invent behavior/timing not stated in the contract.
- Match the exact module name and port list.
- Declare EVERY parameter listed in the contract's `parameters`, with the given
  names and default values, in a `#( ... )` block. Do NOT drop, rename, or add
  parameters, and do NOT demote a contract parameter to a localparam — the golden
  testbench may override it by name or position. Use parameter names (not hard-coded
  literals) for the widths/values they govern.
- Produce synthesizable RTL (no delays, no testbench constructs).
- Keep the code small and readable.

In `reasoning`, write a short summary of key decisions and assumptions (no step-by-step chain-of-thought).

The module interface must EXACTLY match the contract (module name, parameter list with defaults, port names, widths).

<contract_json>
{contract_json}
</contract_json>

{examples_prompt}
<input_spec>
{input_spec}
</input_spec>
"""

KMAP_HINT_PROMPT = r"""
[K-map hint (only if the problem involves Karnaugh maps / K-maps)]:
- Carefully interpret the K-map variable ordering from the spec/contract.
- Note: x[i] in x[N:1] corresponds to x[i-1] in x[N-1:0].
- Enumerate minterms/implicants for output=1/0/don't-care as required; implement minimal logic.
- If you have a descending range like `logic x[M:N]` (M>N), do NOT use reverse selects like `x[1:2]`;
  instead use concatenation: `{x[1], x[2]}`.
"""

EXTRA_ORDER_PROMPT = r"""
Other requirements:
1. Don't use state_t to define the parameter. Use `localparam` or Use 'reg' or 'logic' for signals as registers or Flip-Flops.
2. Declare all ports as logic. For internal nets/regs, prefer logic; `wire` is fine for continuous assigns.
3. If the contract specifies a reset, use it to ensure deterministic behavior as specified.
   If the contract does NOT include a reset but the testbench expects deterministic startup, you MAY use a minimal `initial`
   initialization to avoid X-propagation in simulation (Verilator-focused). Do not rely on `initial` for core functionality.
4. For combinational logic with an always block do not explicitly specify the sensitivity list; instead use always @(*).
5. NEVER USE 'inside' operator in RTL code. Code like 'state inside {STATE_B, STATE_C, STATE_D}' should NOT be used.
6. Never USE 'unique' or 'unique0' keywords in RTL code. Code like 'unique case' should NOT be used.
7. Respect any explicit latency/timing described in the contract (e.g., next-cycle outputs).
8. WHERE THE CONTRACT DECLARES A LATENCY, IT IS A HARD CONSTRAINT, NOT A
   PREFERENCE. `timing.<output>.latency_cycles` is the number of edges of the
   DECLARED CLOCK between the edge that captures a stimulus and the edge on
   which that output first reflects it -- edges of the declared clock, not
   enable ticks, so a design whose FSM advances on a prescaled `clk_en` legitimately
   takes more clock edges than it has phases. The field is present only when the
   specification determines the count or a completion signal makes it observable.
   WHERE IT IS ABSENT, the specification does not settle the depth: build what
   the function needs and do not invent a pipeline to fill a number that is not
   there. Count the registers on the path before you finish:

     latency_cycles = 0  -> purely combinational. The output must NOT be assigned
                            with `<=` in any clocked block.
     latency_cycles = 1  -> EXACTLY ONE register. The combinational datapath reads
                            the INPUT PORTS directly and only the result is
                            registered.
     latency_cycles = N  -> exactly N registers in series on that path.

   Registering the inputs into `*_reg`/`*_s1` AND registering the result is TWO
   stages, not one — that is the single most common way this goes wrong. If the
   contract says 1, there must be no `a_reg <= a` stage feeding the datapath.
   Splitting a long computation into `_s1`/`_s2`/`_s3` pipeline stages is a
   sensible instinct and is WRONG here unless the contract asked for that depth:
   a deeper pipeline is not a better design, it is a different contract.

   Nothing downstream will catch a mistake here, and that is deliberate rather
   than an oversight. The specflow testbench compares the ordered sequence of
   output states and ignores how long each is held, precisely because a cycle
   count nothing can check against the specification is a fiction -- so it will
   not reject a design for its depth. Cycle structure depends on the hardware
   the specification does not pin down, which makes it yours: getting it right
   is your responsibility alone.
"""
# Some prompts above comes from:
# @misc{ho2024verilogcoderautonomousverilogcoding,
#       title={VerilogCoder: Autonomous Verilog Coding Agents with Graph-based Planning and Abstract Syntax Tree (AST)-based Waveform Tracing Tool},
#       author={Chia-Tung Ho and Haoxing Ren and Brucek Khailany},
#       year={2024},
#       eprint={2408.08927},
#       archivePrefix={arXiv},
#       primaryClass={cs.AI},
#       url={https://arxiv.org/abs/2408.08927},
# }

IF_PROMPT = r"""
The module interface is given below:
<module_interface>
{module_interface}
</module_interface>
"""

TB_PROMPT = r"""
Verifier has generated a testbench (intended to follow the contract/spec):
<testbench>
{testbench}
</testbench>
"""

FORMAT_ERROR_PROMPT = r"""
The error below has been reported by the format tool:
<format_error>
{format_error}
</format_error>
To understand the error message better, we offered a version of generated module with line number:
<module_with_lineno>
{module_with_lineno}
</module_with_lineno>
"""

EXAMPLE_OUTPUT_FORMAT = """<reasoning>
Concise rationale + key assumptions (no step-by-step chain-of-thought)
</reasoning>
<module>
Complete synthesizable SystemVerilog RTL module
</module>
"""


def looks_like_placeholder(rtl_code: str, contract_json: str) -> Optional[str]:
    """Cheap structural sanity check: does `rtl_code` look like a genuine
    implementation attempt against `contract_json`, or a stub/refusal (e.g.
    "Placeholder module - contract JSON not yet provided")?

    This is NOT a correctness check -- the simulation/debug loop downstream
    still verifies actual behavior. It exists because `chat()`'s retry loop
    previously accepted ANY response that (a) had a non-empty <module> block
    and (b) passed a bare `verilator --lint-only` syntax check -- neither of
    which distinguishes a real (if buggy) attempt from a generic stub module
    the model emits when it (incorrectly) believes the contract is missing.
    Confirmed live on booth_multiplier (2026-07-25 sweep, job 7799101): 5 of
    13 glue attempts (4, 6, 7, 8, 12) produced exactly this stub -- the
    Coder's own conversation history DOES contain <contract_json> from the
    very first turn, so this is the model losing track under a long
    conversation / cheap-model context confusion, not a plumbing gap -- but
    downstream nothing caught it, so the debug loop then burned its full
    trial budget trying to fix a module that was never attempting the real
    function, discarding a legitimately-reasonable earlier draft along the
    way (see rtl_regen_after_mismatch.sv overwriting a good rtl_code2 in
    top_agent.py).

    Returns a human-readable reason string if `rtl_code` looks like a stub,
    else ``None``. Deliberately lenient (a real module name match with SOME
    expected ports present is accepted) -- the goal is only to catch "the
    model didn't even try," never to reject a genuine but imperfect attempt
    (which the normal syntax/simulation/debug loop already handles).
    """
    try:
        contract = json.loads(contract_json)
    except Exception:  # noqa: BLE001
        return None  # can't validate without a parseable contract; don't block

    expected_name = contract.get("module_name")
    name_match = re.search(r"\bmodule\s+(\w+)", rtl_code)
    actual_name = name_match.group(1) if name_match else None
    if expected_name and actual_name and actual_name != expected_name:
        return f"module name mismatch: expected '{expected_name}', got '{actual_name}'"

    expected_ports = [
        p.get("name") for p in contract.get("io", [])
        if isinstance(p, dict) and p.get("name")
    ]
    if expected_ports:
        present = sum(
            1 for name in expected_ports
            if re.search(r"\b" + re.escape(name) + r"\b", rtl_code)
        )
        if present < max(1, len(expected_ports) // 2):
            return (
                f"only {present}/{len(expected_ports)} expected contract ports "
                "appear anywhere in the generated module -- looks like a stub, "
                "not a real implementation attempt"
            )
    return None


class RTLOutputFormat(BaseModel):
    reasoning: str
    module: str


class RTLGenerator:
    def __init__(
        self,
        cfg: OpenAIConfig,
    ):
        self._cfg = cfg
        self._agent = self._new_agent(name="Coder")
        self.generated_tb: str | None = None
        self.generated_if: str | None = None
        self.failed_trial: List[str] = []
        self.max_trials = 5
        self.last_prompt: str = ""
        self.last_raw_output: str = ""

    def reset(self):
        clear_memory_safely(self._agent)

    def _new_agent(self, *, name: str, composition: bool = False) -> SafeReActAgent:
        return SafeReActAgent(
            name=name,
            sys_prompt=GLUE_SYSTEM_PROMPT if composition else SYSTEM_PROMPT,
            model=make_openai_model(self._cfg),
            formatter=make_formatter(self._cfg.model),
            memory=InMemoryMemory(),
            max_iters=10,
        )

    def set_failed_trial(
        self, failed_sim_log: str, previous_code: str, previous_tb: str
    ) -> None:
        cur_failed_trial = FAILED_TRIAL_PROMPT.format(
            failed_sim_log=failed_sim_log,
            previous_code=add_lineno(previous_code),
            previous_tb=add_lineno(previous_tb),
        )
        self.failed_trial.append(cur_failed_trial)

    async def _call_agent(self, agent: SafeReActAgent, prompt: str) -> str:
        self.last_prompt = prompt
        msg = await agent(Msg("user", prompt, role="user"))
        text = msg.get_text_content() or ""
        self.last_raw_output = text
        return text

    def get_init_prompt_messages(self, input_spec: str, *, contract_json: str) -> List[Msg]:
        def needs_kmap_hints() -> bool:
            text = f"{input_spec}\n{contract_json}".lower()
            return any(k in text for k in ["kmap", "k-map", "karnaugh"])

        composition = _is_composition_contract(contract_json)
        parts: list[str] = [
            GENERATION_PROMPT.format(
                input_spec=input_spec,
                # A glue node gets GLUE exemplars. Handing it the monolithic
                # TopModule leaves demonstrates precisely the behaviour the
                # vestigial-glue check rejects.
                examples_prompt=(
                    GLUE_4_SHOT_EXAMPLES if composition else RTL_4_SHOT_EXAMPLES
                ),
                contract_json=contract_json,
            )
        ]
        if needs_kmap_hints():
            parts.append(KMAP_HINT_PROMPT)
        if self.generated_tb:
            parts.append(TB_PROMPT.format(testbench=self.generated_tb))
        parts.extend(self.failed_trial)
        if self.generated_if:
            parts.append(IF_PROMPT.format(module_interface=self.generated_if))
        if composition:
            # LAST, deliberately: the composition obligation is otherwise buried
            # ~21K tokens up, behind a port list that is 35% of the prompt.
            parts.append(GLUE_PORT_CHECKLIST_PROMPT)
        return [Msg("user", "\n\n".join(parts), role="user")]

    def get_order_prompt_messages(self) -> List[Msg]:
        return [
            Msg(
                "user",
                TAG_ORDER_PROMPT.format(output_format=EXAMPLE_OUTPUT_FORMAT)
                + EXTRA_ORDER_PROMPT,
                "user",
            )
        ]

    def get_format_error_prompt_messages(
        self, format_error: str, rtl_code: str
    ) -> List[Msg]:
        return [
            Msg(
                "user",
                FORMAT_ERROR_PROMPT.format(
                    format_error=format_error, module_with_lineno=add_lineno(rtl_code)
                ),
                "user",
            )
        ]

    def parse_output(self, response_text: str) -> RTLOutputFormat:
        try:
            module = strip_markdown_code_fences(extract_xml_tag(response_text, "module")).strip()
            reasoning = extract_xml_tag(response_text, "reasoning", required=False).strip()
            if not module:
                raise ValueError("Empty <module> block")
            ret = RTLOutputFormat(reasoning=reasoning, module=module)
        except Exception as e:  # noqa: BLE001
            ret = RTLOutputFormat(reasoning=f"Parse Error: {type(e).__name__}: {e}", module="")
        return ret

    async def chat(
        self,
        input_spec: str,
        testbench: str,
        interface: str,
        rtl_path: str,
        contract_json: str,
    ) -> Tuple[bool, str]:
        self.reset()
        self.generated_tb = testbench
        self.generated_if = interface

        # The agent is constructed in __init__, before any contract is known, so
        # it starts on the LEAF system prompt. A composition node needs the
        # inverted objective ("do not implement, wire") in its SYSTEM role, not
        # merely mentioned in the user turn -- rebuild it here.
        if _is_composition_contract(contract_json):
            self._agent = self._new_agent(name="Coder", composition=True)

        init = self.get_init_prompt_messages(input_spec, contract_json=contract_json)[0].content
        order = self.get_order_prompt_messages()[0].content
        prompt = f"{init}\n\n{order}"
        syntax_correct = False
        rtl_code = ""
        for _ in range(self.max_trials):
            response_text = await self._call_agent(self._agent, prompt)
            resp_obj = self.parse_output(response_text)
            if resp_obj.reasoning.startswith("Parse Error"):
                repair = PARSE_REPAIR_PROMPT.format(
                    parse_error=resp_obj.reasoning,
                    bad_output=clip_text(response_text, max_chars=6000),
                )
                prompt = f"{init}\n\n{repair}\n\n{order}"
                continue
            placeholder_reason = looks_like_placeholder(resp_obj.module, contract_json)
            if placeholder_reason:
                repair = PLACEHOLDER_REPAIR_PROMPT.format(
                    reason=placeholder_reason,
                    contract_json=contract_json,
                    bad_output=clip_text(response_text, max_chars=6000),
                )
                prompt = f"{repair}\n\n{order}"
                continue
            rtl_code = resp_obj.module
            with open(rtl_path, "w") as f:
                f.write(rtl_code)
            syntax_correct, syntax_output = await asyncio.to_thread(
                check_syntax, rtl_path
            )
            if syntax_correct:
                break
            fmt = self.get_format_error_prompt_messages(syntax_output, rtl_code)[0].content
            prompt = f"{fmt}\n\n{order}"
        return (syntax_correct, rtl_code)

    async def ablation_chat(self, input_spec: str, rtl_path: str) -> Tuple[bool, str]:
        self.reset()
        self.generated_tb = None
        self.generated_if = None

        init = self.get_init_prompt_messages(input_spec, contract_json="")[0].content
        order = self.get_order_prompt_messages()[0].content
        prompt = f"{init}\n\n{order}"
        syntax_correct = False
        rtl_code = ""
        for _ in range(self.max_trials):
            response_text = await self._call_agent(self._agent, prompt)
            resp_obj = self.parse_output(response_text)
            if resp_obj.reasoning.startswith("Parse Error"):
                repair = PARSE_REPAIR_PROMPT.format(
                    parse_error=resp_obj.reasoning,
                    bad_output=clip_text(response_text, max_chars=6000),
                )
                prompt = f"{init}\n\n{repair}\n\n{order}"
                continue
            rtl_code = resp_obj.module
            with open(rtl_path, "w") as f:
                f.write(rtl_code)
            syntax_correct, syntax_output = await asyncio.to_thread(
                check_syntax, rtl_path
            )
            if syntax_correct:
                break
            fmt = self.get_format_error_prompt_messages(syntax_output, rtl_code)[0].content
            prompt = f"{fmt}\n\n{order}"
        return (syntax_correct, rtl_code)
