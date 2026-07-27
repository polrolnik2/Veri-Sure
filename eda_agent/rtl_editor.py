from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Tuple

from agentscope.memory import InMemoryMemory
from agentscope.message import Msg
from agentscope.tool import ToolResponse

from .agents import GuidingToolkit, SafeReActAgent, clear_memory_safely
from .asserter import Asserter
from .boolean_proofer import BooleanProofer
from .config import OpenAIConfig
from .model import make_formatter, make_openai_model
from .sim_reviewer import SimReviewer, check_syntax
from .trace_report import build_trace_report
from .trace_slicer import RtlBlock
from .utils import failing_test_scenarios, format_failing_scenarios

logger = logging.getLogger(__name__)

_FAIL_TIME_HINT_RE = re.compile(
    r"Hint:\s+Output\s+'[^']+'\s+has\s+(?P<cnt>\d+)\s+mismatches\.\s+First mismatch occurred at time\s+(?P<t>\d+)\.",
    re.MULTILINE,
)
_FAIL_TIME_FAILED_RE = re.compile(
    r"SIMULATION FAILED - \d+\s+MISMATCHES DETECTED.*FIRST AT TIME\s+(?P<t>\d+)",
    re.IGNORECASE,
)


def _extract_fail_time_from_sim_log_json(sim_log_json: str) -> int | None:
    """Best-effort earliest mismatch time from a CommandResult JSON string."""
    try:
        obj = json.loads(sim_log_json)
    except Exception:  # noqa: BLE001
        return None
    stdout = str(obj.get("stdout") or "")
    times: list[int] = []
    for m in _FAIL_TIME_HINT_RE.finditer(stdout):
        try:
            if int(m.group("cnt")) > 0:
                times.append(int(m.group("t")))
        except Exception:  # noqa: BLE001
            continue
    if times:
        return min(times)
    m2 = _FAIL_TIME_FAILED_RE.search(stdout)
    if m2:
        try:
            return int(m2.group("t"))
        except Exception:  # noqa: BLE001
            return None
    return None


def _clip_text(s: str, *, max_chars: int) -> str:
    if not isinstance(s, str):
        s = str(s)
    if max_chars <= 0 or len(s) <= max_chars:
        return s
    half = max_chars // 2
    return s[:half] + "\n...<snip>...\n" + s[-half:]


def _summarize_sim_log_json(sim_log_json: str, *, max_chars: int = 4000) -> str:
    """Return a compact excerpt from a CommandResult JSON string."""
    stdout = ""
    stderr = ""
    try:
        obj = json.loads(sim_log_json)
        stdout = str(obj.get("stdout") or "")
        stderr = str(obj.get("stderr") or "")
    except Exception:  # noqa: BLE001
        return _clip_text(sim_log_json, max_chars=max_chars)

    # Keep the most informative bits: mismatch banner + hints + summary.
    #
    # The original vocabulary here was written for LEAF testbenches
    # ("[TEST ...]", "=== MISMATCH DETECTED", "Mismatches: N in M"). COMPOSED
    # testbenches report through SVA assertions instead:
    #
    #   === Scenario 2: Multiply by zero (0*7) ===
    #   [145] %Error: tb.sv:156: Assertion failed in tb.a_product_valid:
    #         FAIL [cycle 14]: product_valid_when_ready
    #
    # None of that matched, so `interesting` came back EMPTY and the function
    # fell through to a head+tail clip of raw stdout -- whose head is
    # "make: Entering directory ...". Observed live on booth: the debugger's
    # very first run_simulation returned an excerpt beginning with compile
    # chatter, so it never saw the assertion, the cycle, or the scenario it was
    # supposed to fix. A glue-only blind spot: leaf TBs speak the matched
    # vocabulary, composed TBs do not.
    interesting: list[str] = []
    for line in stdout.splitlines():
        low = line.lower()
        if (
            "[TEST " in line
            or "=== MISMATCH DETECTED" in line
            or "Hint:" in line
            or line.startswith("Mismatches:")
            or "SIMULATION FAILED" in line
            or "SIMULATION PASSED" in line
            or line.strip() == "TIMEOUT"
            # --- composed/SVA vocabulary ---
            or "assertion failed" in low
            or "%error" in low
            or "fail [cycle" in low
            or line.strip().startswith("=== Scenario")
            or ("mismatch" in low and "detected" in low)
        ):
            interesting.append(line)
    out = "\n".join(interesting).strip()
    if not out:
        # Still nothing recognised: hand back the TAIL of the meaningful lines
        # rather than a head-clip dominated by the build transcript. A single
        # g++ command line is ~700 chars and would consume the whole budget.
        meaningful = [
            l for l in stdout.splitlines()
            if l.strip() and not l.startswith((
                "g++", "make:", "make[", "python3 ", "rm ", "verilator ",
                "- Verilator:", "- V e r i l a t i o n", "- S i m u l a t i o n",
                "ar ", "ranlib",
            ))
        ]
        out = "\n".join(meaningful[-40:]) if meaningful else _clip_text(stdout, max_chars=max_chars)

    if stderr.strip():
        out = out + "\n\n[stderr excerpt]\n" + _clip_text(stderr, max_chars=max(800, max_chars // 3))
    return _clip_text(out, max_chars=max_chars)


def _render_contract_sva_body(contract_json: str) -> str | None:
    """Render contract_sva from the contract JSON as an assertion module body.

    When the orchestrator supplies ``contract_sva`` in the contract, these
    replace the LLM-generated assertions entirely.  The rendered body is
    passed as ``assert_body_override`` to :meth:`Asserter.analyze`, so the
    asserter runs the contract properties instead of inventing its own.

    Returns ``None`` if no contract_sva is present (the asserter then falls
    back to its normal LLM generation).
    """
    try:
        contract = json.loads(contract_json)
    except Exception:  # noqa: BLE001
        return None
    contract_sva = contract.get("contract_sva")
    if not contract_sva or not isinstance(contract_sva, list):
        return None

    clocking = contract.get("clocking") or {}
    clk_info = (clocking.get("clock") or {}) if isinstance(clocking, dict) else {}
    rst_info = (clocking.get("reset") or {}) if isinstance(clocking, dict) else {}
    clk_name = clk_info.get("name", "clk") if isinstance(clk_info, dict) else "clk"
    rst_name = rst_info.get("name") if isinstance(rst_info, dict) else None
    rst_active = rst_info.get("active", "high") if isinstance(rst_info, dict) else "high"

    if rst_name:
        rst_expr = f"({rst_name} == 1'b0)" if rst_active == "low" else rst_name
    else:
        rst_expr = None

    lines: list[str] = []
    lines.append("  // === Contract SVA (orchestrator-supplied, replaces LLM assertions) ===")
    for prop in contract_sva:
        if not isinstance(prop, dict):
            continue
        name = prop.get("name", "golden_prop")
        body = prop.get("body", "")
        if not body:
            continue
        prop_clk = prop.get("clk", clk_name)
        prop_rst = prop.get("rst", rst_name)
        if prop_rst:
            prop_rst_expr = f"({prop_rst} == 1'b0)" if rst_active == "low" else prop_rst
            disable = f" disable iff ({prop_rst_expr})"
        else:
            disable = ""

        lines.append(f"  always @(posedge {prop_clk}) begin")
        lines.append(f"    if ({f'!{prop_rst_expr}' if prop_rst else '1'}) begin")
        lines.append(f"      {name}_check: assert ({body})")
        lines.append(f'        else asserter_log("{name}", $sformatf("CONTRACT SVA FAIL: {name}"));')
        lines.append(f"    end")
        lines.append(f"  end")
        lines.append("")

    return "\n".join(lines) if len(lines) > 1 else None


SYSTEM_PROMPT = r"""
You are Debugger, an expert in RTL debugging.

Goal: use tool calls to minimally edit and re-simulate SystemVerilog RTL so that:
1) The RTL matches the Architect contract (SOURCE OF TRUTH), and
2) The RTL passes the Verifier-generated testbench (or golden benchmark testbench).

Toolchain note:
- Simulation is run with Verilator; errors/warnings in logs may follow Verilator formatting.

Rules:
1. Do not modify the testbench. Only modify the RTL code.
2. Do not try to change or define RefModule. There is RefModule defined elsewhere if needed.
3. Always respect the simulation result. Keep debugging as long as mismatches exist.
4. Prefer small, targeted edits.
5. Preserve the module interface and the contract's timing assumptions.
6. Contract-only mode: do NOT change behavior based on input_spec if it conflicts with the contract.
7. Contract SVA mode: if the contract JSON contains a `contract_sva` field, these are hard
   specification constraints your RTL MUST satisfy. Ensure fixes do not violate them.
8. Child assumes mode: if the contract JSON contains a `child_assumes` field, this RTL is a
   COMPOSITION/GLUE module with child-facing ports (prefixed with each child module name,
   so a child `foo` with port `ready` appears as `foo_ready`) ALREADY on its port list.
   - DO NOT instantiate any child module as a fix. There are no child module definitions
     available to this RTL — child-facing ports connect externally, outside this file.
   - If a child-facing port appears unconnected, undriven, or X-valued, the fix is to wire
     it correctly within the GLUE LOGIC (assign/always blocks using existing ports), never
     to declare or instantiate a module for it.
   - Each child's `io_behavior`/`timing`/`properties` in `child_assumes` describe what that
     child guarantees on its ports — use them to determine the correct glue behavior.
     `io_behavior` is a BLACK-BOX description (no internal architecture terms); do NOT use
     a child's `functional_summary` (if present) to reason about its behavior — that field
     describes the child's own internal RTL implementation, not its observable interface.
   - VESTIGIAL GLUE is a rejection criterion unique to composition modules, and it is
     checked MECHANICALLY BEFORE any simulation runs: every child-facing INPUT port (a
     port carrying a child's RESULT into this module) must be READ somewhere in the body.
     A glue module that declares such a port and never references it has recomputed that
     child's function inline instead of composing through it, and is rejected however
     well it simulates.
   - So if you are told the composition failed and you cannot find a functional bug, check
     this FIRST: for each child-facing input port, find where its value is consumed. If a
     port has no consumer, the fix is to route it into the external output (or sibling
     child input) it belongs to and DELETE the inline logic that was recomputing it —
     not to add more logic. Deleting a redundant computation is a valid, often correct fix
     here, which is not true when debugging a leaf module.

When you are done (simulation passes), finish by calling generate_response with a
structured plain-string response in EXACTLY this format (use literal newlines between fields):
  generate_response(response="RTL_FIXED: <one-line summary of what you changed>\nCONTRACT_CLAUSE: <the specific contract requirement that was violated>\nFIX_RATIONALE: <how this change makes the RTL satisfy that requirement>")
The `response` argument MUST be a plain string (not JSON, not a dict, not a list).
"""


INIT_EDITION_PROMPT = r"""
The information below is given to help your work:
1. The Architect contract (JSON) that both TB and RTL MUST follow (SOURCE OF TRUTH);
2. The generated testbench (fixed; you must not modify it);
3. The simulation failure log excerpt (ground truth about mismatches; full log is saved on disk).
4. The input_spec is included only as background; it must NOT override the contract.
<input_spec>
{input_spec}
</input_spec>
<contract_json>
{contract_json}
</contract_json>
<generated_tb>
{generated_tb}
</generated_tb>
<sim_failed_log_excerpt>
{sim_failed_log_excerpt}
</sim_failed_log_excerpt>
{kmap_hint}
"""

KMAP_DEBUG_HINT_PROMPT = r"""
[K-map hint (only if the problem involves Karnaugh maps / K-maps)]:
- Use mismatch inputs from the sim log/trace to identify wrong minterms.
- Fix one mismatch class at a time while preserving all other truth-table entries.
"""

EXTRA_ORDER_PROMPT = r"""
Workflow (repeat until pass):
1) Use the contract + trace report + <failing_scenarios> to find the most likely
   root cause. All listed scenarios fail simultaneously — prefer a single fix that
   resolves the whole group over patching one failing case at a time.
2) Check `trace_summary.alignment_diagnosis` first:
   - If it suggests a 1-cycle shift or wrong sampling edge, fix timing/reset/edge issues before changing core logic.
   - Otherwise focus on combinational correctness in the suspect block(s).
3) Call list_suspect_blocks(), then read_block(block_id) for the most relevant one.
4) Make ONE small change in ONE block via replace_block(block_id, new_code).
5) Immediately call run_simulation() and iterate based on the new trace summary.

Rules:
- Do not modify the testbench. Only modify the RTL code.
- Preserve the module interface and the contract's timing assumptions.
- Only modify code inside suspect blocks.
- Keep RTL synthesizable and Verilator-compatible (avoid fancy SVA, no delays).

You will also receive a structured trace-grounded bug report (JSON) that includes:
1) earliest mismatch time, 2) (expected vs actual) values when available, 3) a short input window,
4) a dynamically sliced list of suspect always/assign blocks.

You MUST only modify code inside suspect blocks.
Use tools:
- list_suspect_blocks()
- read_block(block_id)
- replace_block(block_id, new_code)
- run_simulation()

When simulation passes, end with generate_response using this format:
  generate_response(response="RTL_FIXED: <one-line summary>\nCONTRACT_CLAUSE: <specific contract requirement violated>\nFIX_RATIONALE: <how this change satisfies that requirement>")
"""


@dataclass
class _EditSession:
    tb_path: str
    rtl_path: str
    output_dir: str
    last_mismatch_cnt: int
    sim_reviewer: SimReviewer
    max_trials: int

    is_done: bool = False
    action_calls: int = 0
    trace_report: Dict[str, Any] | None = None
    blocks_by_id: Dict[str, RtlBlock] | None = None
    last_fail_time: int | None = None
    # The full result dict of the MOST RECENT replace_block()/run_simulation()
    # call, regardless of whether it was accepted or rolled back. Set by the
    # tool wrappers (_tool_replace_block/_tool_run_simulation), read by
    # chat()'s "continue debugging" re-prompt so the model is handed the
    # concrete outcome of what it just tried instead of a bare "keep going" —
    # relying solely on the model re-deriving/recalling this from its own
    # conversation history is not good feedback, especially after several
    # rounds of exploration in between.
    last_action_result: Dict[str, Any] | None = None

    def read_rtl(self) -> str:
        with open(self.rtl_path, "r", encoding="utf-8") as f:
            return f.read()

    def read_rtl_with_lineno(self) -> str:
        lines = self.read_rtl().splitlines()
        return "\n".join(f"{i+1}: {line}" for i, line in enumerate(lines)) + "\n"

    def write_rtl(self, content: str) -> None:
        with open(self.rtl_path, "w", encoding="utf-8") as f:
            f.write(content)

    def run_simulation(self) -> Dict[str, Any]:
        is_sim_pass, sim_mismatch_cnt, sim_output = self.sim_reviewer.review()
        # Persist full sim output for human inspection; provide excerpt to the agent.
        try:
            Path(self.output_dir, "debug_sim_output.json").write_text(sim_output, encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass
        return {
            "is_sim_pass": is_sim_pass,
            "sim_mismatch_cnt": sim_mismatch_cnt,
            "sim_output_excerpt": _summarize_sim_log_json(sim_output),
            "sim_output_path": str(Path(self.output_dir, "debug_sim_output.json")),
        }

    def list_suspect_blocks(self) -> list[dict[str, Any]]:
        if not self.trace_report:
            return []
        return list(self.trace_report.get("suspect_blocks") or [])

    def read_block(self, block_id: str) -> str:
        if not self.blocks_by_id or block_id not in self.blocks_by_id:
            return f"ERROR: Unknown block_id '{block_id}'."
        block = self.blocks_by_id[block_id]
        lines = block.code.splitlines()
        return "\n".join(f"{block.start_line + i}: {line}" for i, line in enumerate(lines)) + "\n"

    def _refresh_trace(self, *, sim_log_json: str) -> None:
        report, suspect_blocks = build_trace_report(
            rtl_path=Path(self.rtl_path),
            sim_log_json=sim_log_json,
            output_dir=Path(self.output_dir),
        )
        self.trace_report = report
        self.blocks_by_id = {b.id: b for b in suspect_blocks} if suspect_blocks else None
        ft = report.get("fail_time")
        self.last_fail_time = int(ft) if isinstance(ft, int) else None
        (Path(self.output_dir) / "trace_report.json").write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    def trace_report_path(self) -> str:
        return str(Path(self.output_dir) / "trace_report.json")

    def trace_summary(self) -> Dict[str, Any]:
        tr = self.trace_report or {}
        suspects = tr.get("suspect_blocks") or []
        fail_outputs = tr.get("fail_outputs") or []
        alignment = tr.get("alignment_diagnosis") or {}
        timing_hints = ((tr.get("notes") or {}).get("timing_hints")) or {}

        # Compact alignment summary: keep only the best_alignment and a couple of rates per output.
        alignment_compact: Dict[str, Any] = {}
        if isinstance(alignment, dict):
            for sig, info in alignment.items():
                if not isinstance(info, dict):
                    continue
                alignment_compact[str(sig)] = {
                    "best_alignment": info.get("best_alignment"),
                    "match_rate_current": info.get("match_rate_current"),
                    "match_rate_dut_lag1": info.get("match_rate_dut_lag1"),
                    "match_rate_posedge": info.get("match_rate_posedge"),
                    "match_rate_negedge": info.get("match_rate_negedge"),
                    "samples_considered": info.get("samples_considered"),
                }

        return {
            "trace_report_path": self.trace_report_path(),
            "fail_time": tr.get("fail_time"),
            "total_mismatches": tr.get("total_mismatches"),
            "fail_outputs": [
                {"sig": fo.get("sig"), "expected": fo.get("expected"), "actual": fo.get("actual")}
                for fo in fail_outputs
                if isinstance(fo, dict)
            ][:5],
            "suspect_blocks": [
                {
                    "id": b.get("id"),
                    "clocking": b.get("clocking"),
                    "start_line": b.get("start_line"),
                    "end_line": b.get("end_line"),
                    "writes": b.get("writes"),
                }
                for b in suspects
                if isinstance(b, dict)
            ][:8],
            "alignment_diagnosis": alignment_compact,
            "timing_hints": timing_hints,
            "dut_instance": ((tr.get("notes") or {}).get("dut_instance")),
            "vcd_available": ((tr.get("notes") or {}).get("vcd_available")),
        }

    def _base_result(self) -> Dict[str, Any]:
        return {
            "is_action_executed": False,
            "is_syntax_correct": False,
            "syntax_output": "",
            "is_sim_pass": False,
            "sim_mismatch_cnt": 0,
            "sim_output": "",
            "error_msg": "",
        }

    def _judge_replace_action_execution(self, *, old_file_content: str) -> Dict[str, Any]:
        result = self._base_result()
        prev_mismatch_cnt = int(self.last_mismatch_cnt)
        prev_fail_time = self.last_fail_time
        is_syntax_correct, syntax_output = check_syntax(self.rtl_path)
        result["is_syntax_correct"] = is_syntax_correct
        result["syntax_output"] = syntax_output
        if not is_syntax_correct:
            self.write_rtl(old_file_content)
            result["error_msg"] = "Syntax error. Action rolled back."
            return result

        is_sim_pass, sim_mismatch_cnt, sim_output = self.sim_reviewer.review()
        result["is_sim_pass"] = is_sim_pass
        result["sim_mismatch_cnt"] = sim_mismatch_cnt
        try:
            Path(self.output_dir, "debug_sim_output.json").write_text(sim_output, encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass
        result["sim_output_excerpt"] = _summarize_sim_log_json(sim_output)
        result["sim_output_path"] = str(Path(self.output_dir, "debug_sim_output.json"))
        result["prev_mismatch_cnt"] = prev_mismatch_cnt
        result["prev_fail_time"] = prev_fail_time
        new_fail_time = _extract_fail_time_from_sim_log_json(sim_output)
        result["new_fail_time"] = new_fail_time

        if sim_mismatch_cnt > prev_mismatch_cnt:
            # Sometimes fixing an early-cycle issue can expose additional later-cycle mismatches.
            # Allow a small mismatch increase only if the FIRST mismatch time moves later.
            increase = int(sim_mismatch_cnt) - int(prev_mismatch_cnt)
            max_increase = min(5, max(1, int(0.1 * max(1, int(prev_mismatch_cnt)))))
            allow = (
                (prev_fail_time is not None)
                and (new_fail_time is not None)
                and (new_fail_time > prev_fail_time)
                and (increase <= max_increase)
            )
            if not allow:
                self.write_rtl(old_file_content)
                result["error_msg"] = (
                    "Mismatch_cnt increased after replacement. Action rolled back. "
                    f"(prev={prev_mismatch_cnt}, new={sim_mismatch_cnt}, prev_fail_time={prev_fail_time}, new_fail_time={new_fail_time})"
                )
                return result
            result["accept_reason"] = (
                "Accepted despite slight mismatch increase because earliest mismatch moved later "
                f"(+{increase} mismatches, fail_time {prev_fail_time}->{new_fail_time})."
            )

        if sim_mismatch_cnt == 0 and not is_sim_pass:
            self.write_rtl(old_file_content)
            result["error_msg"] = "Mismatch_cnt is 0 but simulation failed. Action rolled back."
            return result

        # Accept.
        self.last_mismatch_cnt = sim_mismatch_cnt
        if new_fail_time is not None:
            self.last_fail_time = int(new_fail_time)
        result["is_action_executed"] = True
        if is_sim_pass and sim_mismatch_cnt == 0:
            self.is_done = True
        else:
            self._refresh_trace(sim_log_json=sim_output)
            result["trace_summary"] = self.trace_summary()
        return result

    def replace_block(self, block_id: str, new_code: str) -> Dict[str, Any]:
        if not self.blocks_by_id or block_id not in self.blocks_by_id:
            return {
                "is_action_executed": False,
                "error_msg": f"Unknown block_id '{block_id}'. Use list_suspect_blocks() first.",
            }

        old_file_content = self.read_rtl()
        old_lines = old_file_content.splitlines()
        block = self.blocks_by_id[block_id]
        start = block.start_line - 1
        end = block.end_line - 1
        if start < 0 or end >= len(old_lines) or start > end:
            return {
                "is_action_executed": False,
                "error_msg": f"Invalid block range for {block_id}: {block.start_line}-{block.end_line}.",
            }

        self.action_calls += 1
        if self.action_calls > self.max_trials:
            return {
                "is_action_executed": False,
                "error_msg": "Reached maximum debug trials; refusing further edits.",
            }

        new_block_lines = new_code.rstrip("\n").splitlines()
        new_lines = old_lines[:start] + new_block_lines + old_lines[end + 1 :]
        self.write_rtl("\n".join(new_lines) + ("\n" if old_file_content.endswith("\n") else ""))

        return self._judge_replace_action_execution(old_file_content=old_file_content)


def _render_continue_debug_prompt(session: "_EditSession") -> str:
    """Build the re-prompt sent after each debug round.

    Explicitly restates the outcome of the LAST action (accepted / rolled
    back, and why) and the current accepted baseline (mismatch count, first
    failure time), instead of a bare "keep going" that relies on the model
    correctly recalling/re-deriving this from its own conversation history —
    not reliable across a long debug session with many intervening
    read_block/list_suspect_blocks calls, and especially not if the model
    just tried (incorrectly) to finish via generate_response, which on its
    own changes nothing about the actual simulation state.
    """
    last = session.last_action_result or {}
    last_action_block = ""
    if last:
        outcome = "ACCEPTED" if last.get("is_action_executed") else "ROLLED BACK / REJECTED"
        detail = last.get("error_msg") or last.get("accept_reason") or ""
        last_action_block = (
            f"Your last action's outcome: {outcome}"
            + (f" — {detail}" if detail else "")
            + f"\n(is_sim_pass={last.get('is_sim_pass')}, sim_mismatch_cnt={last.get('sim_mismatch_cnt')})\n\n"
        )

    fail_time_note = (
        f", first failure at time {session.last_fail_time}"
        if session.last_fail_time is not None else ""
    )

    return (
        f"{last_action_block}"
        f"Current accepted state: {session.last_mismatch_cnt} mismatches{fail_time_note}.\n\n"
        "Continue debugging. Preserve the contract and module interface. If mismatches remain, "
        "pick 1 suspect block and call read_block(block_id), then call replace_block(block_id, new_code) "
        "once, then run_simulation(). Do NOT call generate_response until run_simulation() reports "
        "is_sim_pass=true with 0 mismatches — an unverified claim of success is not accepted as done."
    )


class RTLEditor:
    def __init__(
        self,
        cfg: OpenAIConfig,
        *,
        sim_reviewer: SimReviewer,
        max_trials: int = 30,
        # 0 disables the sliding window (see below) entirely -- no
        # truncation, ever. Was 6, chosen purely to cap per-call token
        # count; that reasoning predates accounting for prompt caching.
        # OpenRouter's DeepSeek caching is automatic (no cache_control
        # needed): cache reads are 0.1x the normal input price, and cache
        # WRITES cost the same as an uncached call -- there is no penalty
        # for a growing, never-truncated prefix. Truncating the middle of
        # the conversation, by contrast, breaks prefix-matching for every
        # request after that point, forcing the entire remaining context to
        # be repriced as fresh (uncached) tokens even though the message
        # list is shorter -- strictly worse for total cost across a
        # multi-trial loop, not better. See tb_editor.py's TBEditor for the
        # matching default and a case where losing history also hurt
        # convergence quality, independent of cost.
        memory_window: int = 0,
        stall_rounds: int = 2,
    ) -> None:
        self._cfg = cfg
        self.sim_reviewer = sim_reviewer
        self.max_trials = int(max_trials)
        self._memory_window = int(memory_window)
        # Consecutive outer-loop rounds with no mismatch-count reduction before
        # giving up. Distinct from max_trials (a hard action-count cap): this
        # detects non-convergence early, so a stuck debugger yields back to the
        # orchestrator (decomposition) instead of grinding through its full
        # budget on rounds that are structurally not making progress.
        self._stall_rounds = max(1, int(stall_rounds))
        self._session: _EditSession | None = None

        toolkit = GuidingToolkit()
        toolkit.register_tool_function(self._tool_list_suspect_blocks)
        toolkit.register_tool_function(self._tool_read_block)
        toolkit.register_tool_function(self._tool_replace_block)
        toolkit.register_tool_function(self._tool_run_simulation)

        self._agent = SafeReActAgent(
            name="Debugger",
            sys_prompt=SYSTEM_PROMPT,
            model=make_openai_model(cfg),
            formatter=make_formatter(cfg.model),
            toolkit=toolkit,
            memory=InMemoryMemory(),
            max_iters=10,
        )

    def reset(self) -> None:
        clear_memory_safely(self._agent)
        self._session = None

    async def _tool_list_suspect_blocks(self) -> ToolResponse:
        """List dynamically sliced suspect blocks (always/assign)."""
        if self._session is None:
            return ToolResponse(content=[{"type": "text", "text": "ERROR: No active edit session."}])
        blocks = self._session.list_suspect_blocks()
        return ToolResponse(content=[{"type": "text", "text": json.dumps(blocks, indent=2)}])

    async def _tool_read_block(self, block_id: str) -> ToolResponse:
        """Read a suspect block by id with line numbers."""
        if self._session is None:
            return ToolResponse(content=[{"type": "text", "text": "ERROR: No active edit session."}])
        return ToolResponse(content=[{"type": "text", "text": self._session.read_block(block_id)}])

    async def _tool_run_simulation(self) -> ToolResponse:
        """Run simulation for current rtl.sv + tb.sv; returns pass/fail and mismatch count."""
        if self._session is None:
            return ToolResponse(content=[{"type": "text", "text": "ERROR: No active edit session."}])
        result = await asyncio.to_thread(self._session.run_simulation)
        # Keep trace_report.json in sync even when the model triggers standalone re-simulations.
        try:
            if (not result.get("is_sim_pass")) and int(result.get("sim_mismatch_cnt") or 0) > 0:
                sim_output = result.get("sim_output")
                if isinstance(sim_output, str) and sim_output.strip():
                    await asyncio.to_thread(self._session._refresh_trace, sim_log_json=sim_output)
            if self._session.trace_report:
                result["trace_summary"] = self._session.trace_summary()
        except Exception:  # noqa: BLE001
            # Tooling should never crash due to trace refresh; keep sim result.
            pass
        self._session.last_action_result = result
        return ToolResponse(content=[{"type": "text", "text": json.dumps(result, indent=4)}])

    async def _tool_replace_block(self, block_id: str, new_code: str) -> ToolResponse:
        """Replace a suspect block by id, then syntax-check + simulate (rollback if mismatch increases)."""
        if self._session is None:
            return ToolResponse(content=[{"type": "text", "text": "ERROR: No active edit session."}])
        result = await asyncio.to_thread(self._session.replace_block, block_id, new_code)
        # Even if the action was rolled back, return the latest available trace pointer/summary
        # so the agent can re-ground itself quickly.
        if self._session.trace_report:
            result.setdefault("trace_summary", self._session.trace_summary())
        self._session.last_action_result = result
        return ToolResponse(content=[{"type": "text", "text": json.dumps(result, indent=4)}])

    async def chat(
        self,
        *,
        spec: str,
        output_dir_per_run: str,
        sim_failed_log: str,
        sim_mismatch_cnt: int,
        contract_json: str,
        max_trials: int | None = None,
    ) -> Tuple[bool, str, int, str]:
        self.reset()
        tb_path = f"{output_dir_per_run}/tb.sv"
        rtl_path = f"{output_dir_per_run}/rtl.sv"
        session_max_trials = int(max_trials) if max_trials is not None else int(self.max_trials)
        if session_max_trials < 0:
            session_max_trials = 0

        self._session = _EditSession(
            tb_path=tb_path,
            rtl_path=rtl_path,
            output_dir=output_dir_per_run,
            last_mismatch_cnt=sim_mismatch_cnt,
            sim_reviewer=self.sim_reviewer,
            max_trials=session_max_trials,
        )

        with open(tb_path, "r", encoding="utf-8") as f:
            generated_tb = f.read()

        # Save full failed log for inspection, but only send a short excerpt to the agent.
        try:
            (Path(output_dir_per_run) / "sim_failed_log.json").write_text(sim_failed_log, encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass
        sim_failed_log_excerpt = _summarize_sim_log_json(sim_failed_log)

        needs_kmap_hint = any(
            k in f"{spec}\n{contract_json}".lower()
            for k in ["kmap", "k-map", "karnaugh"]
        )
        init = INIT_EDITION_PROMPT.format(
            input_spec=spec,
            contract_json=contract_json,
            generated_tb=_clip_text(generated_tb, max_chars=8000),
            sim_failed_log_excerpt=sim_failed_log_excerpt,
            kmap_hint=(KMAP_DEBUG_HINT_PROMPT if needs_kmap_hint else ""),
        )
        # Build a trace-grounded report to guide minimal patching.
        report, suspect_blocks = build_trace_report(
            rtl_path=Path(rtl_path),
            sim_log_json=sim_failed_log,
            output_dir=Path(output_dir_per_run),
        )
        (Path(output_dir_per_run) / "trace_report.json").write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        self._session.trace_report = report
        self._session.blocks_by_id = {b.id: b for b in suspect_blocks} if suspect_blocks else None
        ft0 = report.get("fail_time")
        self._session.last_fail_time = int(ft0) if isinstance(ft0, int) else None

        # Best-effort: boolean (combinational) equivalence hint from the contract summary.
        # This is NOT a source of truth; treat it only as parallel guidance.
        boolean_hint = ""
        try:
            proofer = BooleanProofer(self._cfg)
            proof_res = await proofer.prove(
                contract_json=contract_json,
                rtl_path=rtl_path,
                output_dir=output_dir_per_run,
            )
            boolean_hint = (
                "<boolean_proof_result_json>\n"
                + json.dumps(asdict(proof_res), indent=2, ensure_ascii=False)
                + "\n</boolean_proof_result_json>\n"
            )
        except Exception:  # noqa: BLE001
            boolean_hint = ""

        # Best-effort: assertion-based (sequential/timing) hint in a separate sim sandbox.
        # When contract_sva is present in the contract, use it as assert_body_override
        # so the Asserter runs the orchestrator-supplied contract SVA instead of
        # generating its own (potentially wrong) assertions via the LLM.
        asserter_hint = ""
        try:
            fail_sigs: list[str] = []
            for fo in (report.get("fail_outputs") or []):
                if isinstance(fo, dict) and isinstance(fo.get("sig"), str) and fo.get("sig"):
                    fail_sigs.append(str(fo.get("sig")))
            fail_sigs = sorted(set(fail_sigs))

            contract_sva_override = _render_contract_sva_body(contract_json)

            asserter = Asserter(self._cfg)
            asserter_res = await asserter.analyze(
                contract_json=contract_json,
                rtl_path=rtl_path,
                tb_path=tb_path,
                output_dir=output_dir_per_run,
                golden_rtl_path=getattr(self.sim_reviewer, "golden_rtl_path", None),
                target_outputs=fail_sigs,
                assert_body_override=contract_sva_override,
            )
            asserter_hint = (
                "<asserter_result_json>\n"
                + json.dumps(asdict(asserter_res), indent=2, ensure_ascii=False)
                + "\n</asserter_result_json>\n"
            )
        except Exception:  # noqa: BLE001
            asserter_hint = ""

        # All failing scenarios (with timing pointers into wave.vcd) as a set to fix
        # together, not a single first-fail.
        scenarios = failing_test_scenarios(sim_failed_log_excerpt)
        scenarios_block = (
            "<failing_scenarios>\nThese named TB scenarios are ALL failing — look for "
            "the common root cause that resolves them together. Times index wave.vcd:\n"
            + format_failing_scenarios(scenarios) + "\n</failing_scenarios>\n\n"
            if scenarios else ""
        )
        first_prompt = (
            f"{init}\n\n{scenarios_block}"
            f"<trace_report_json>\n{json.dumps(report, indent=2, ensure_ascii=False)}\n</trace_report_json>\n\n"
            f"{boolean_hint}\n{asserter_hint}\n{EXTRA_ORDER_PROMPT}\n\n"
            "Start by calling list_suspect_blocks(), then read_block(block_id) for the most relevant one, "
            "then apply one replace_block(block_id, new_code), then run_simulation()."
        )
        try:
            (Path(output_dir_per_run) / "debugger_prompt.txt").write_text(first_prompt + "\n", encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass
        _justification: str = ""
        _last_content: str = ""

        # Stall detection: tracks whether last_mismatch_cnt strictly improves
        # round-over-round (it only updates on an ACCEPTED replace_block — a
        # rolled-back action or a round where the model never acts both leave
        # it unchanged, so this naturally catches both failure modes).
        stall_count = 0
        prev_mismatch_for_stall = int(sim_mismatch_cnt)

        def _update_stall_tracking() -> None:
            nonlocal stall_count, prev_mismatch_for_stall
            if self._session.last_mismatch_cnt < prev_mismatch_for_stall:
                stall_count = 0
            else:
                stall_count += 1
            prev_mismatch_for_stall = self._session.last_mismatch_cnt

        response = await self._agent(Msg("user", first_prompt, role="user"))
        _last_content = str(getattr(response, "content", "") or "")
        if self._session.is_done:
            _justification = _last_content
        else:
            _update_stall_tracking()

        for _ in range(session_max_trials):
            if self._session.is_done:
                break
            # Once the session's action budget is exhausted, every further
            # replace_block() call is refused ("Reached maximum debug trials")
            # — the agent can no longer make progress. Stop here instead of
            # burning the remaining outer-loop iterations on calls that are
            # structurally guaranteed to fail; yield back to the caller
            # (orchestrator decomposition) immediately.
            if self._session.action_calls >= self._session.max_trials:
                break
            # No-progress detection: several consecutive rounds with no
            # mismatch-count reduction (rollbacks, no-op reasoning, or edits
            # that don't help) mean the debugger is not converging on this
            # bug — stop spending budget and let the caller decide (typically
            # decompose) rather than grinding to the hard trial cap.
            if stall_count >= self._stall_rounds:
                break
            # Sliding window: keep the initial context message + last N messages
            # to cap per-call input tokens regardless of iteration count.
            mem = self._agent.memory
            window = self._memory_window
            if window > 0 and len(mem.content) > window + 2:
                mem.content = [mem.content[0]] + mem.content[-(window):]
            response = await self._agent(
                Msg(
                    "user",
                    _render_continue_debug_prompt(self._session),
                    role="user",
                )
            )
            _last_content = str(getattr(response, "content", "") or "")
            if self._session.is_done and not _justification:
                _justification = _last_content
            elif not self._session.is_done:
                _update_stall_tracking()

        # If the model wrote RTL_FIXED:/RTL_CORRECT: as plain text but sim never passed,
        # extract it as the justification so lessons have player conclusions.
        if not _justification:
            for kw in ("RTL_FIXED:", "RTL_CORRECT:"):
                idx = _last_content.find(kw)
                if idx != -1:
                    _justification = _last_content[idx:].strip()
                    break

        with open(rtl_path, "r", encoding="utf-8") as f:
            rtl_code = f.read()
        used = int(getattr(self._session, "action_calls", 0) or 0)
        return self._session.is_done, rtl_code, used, _justification
