from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from dataclasses import asdict, dataclass, field
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
from .sim_reviewer import SimReviewer, check_syntax, multidriven_signals
from .trace_report import build_trace_report
from .trace_slicer import RtlBlock
from .utils import (
    constant_output_lag_note,
    operand_passthrough_note,
    missing_output_evidence_note,
    failing_test_scenarios,
    format_failing_scenarios,
    latency_carrier_mismatch_note,
    latency_confirmed_note,
    mismatch_input_skew_note,
    oracle_contradiction_note,
)

logger = logging.getLogger(__name__)

_FAIL_TIME_HINT_RE = re.compile(
    r"Hint:\s+Output\s+'[^']+'\s+has\s+(?P<cnt>\d+)\s+mismatches\.\s+First mismatch occurred at time\s+(?P<t>\d+)\.",
    re.MULTILINE,
)
_FAIL_TIME_FAILED_RE = re.compile(
    r"SIMULATION FAILED - \d+\s+MISMATCHES DETECTED.*FIRST AT TIME\s+(?P<t>\d+)",
    re.IGNORECASE,
)


#: Values that turn the rollback guard OFF. Anything else -- including a typo,
#: an empty string, or a word nobody intended -- leaves it ON, so a mistake in
#: this variable fails safe INTO the guard rather than silently out of it.
_GUARD_OFF_WORDS = frozenset({"off", "0", "false", "no"})


def resolve_rollback_guard(explicit: bool | None = None, env=None) -> bool:
    """Whether an edit that increases the mismatch count should be reverted.

    An explicit argument always wins; `None` consults `EDA_ROLLBACK_GUARD`.
    """
    if explicit is not None:
        return bool(explicit)
    source = os.environ if env is None else env
    return str(source.get("EDA_ROLLBACK_GUARD", "on")).strip().lower() not in _GUARD_OFF_WORDS


def _extract_fail_time_from_sim_log_json(sim_log_json: str) -> int | None:
    """Best-effort earliest mismatch time from a CommandResult JSON string.

    On the specflow backend there is no Verilog testbench and therefore none of
    the `Hint: Output '<x>' has N mismatches...` lines these regexes look for.
    The temporal coordinate is `trace.fail_step` -- the earliest stimulus step
    at which any testpoint diverged -- and it was simply never read, so this
    returned None on every call.

    That mattered because the ONLY escape from the rollback guard is
    `new_fail_time > prev_fail_time` (see `_judge_replace_action_execution`).
    With both sides None the comparison is dead, the allowance never fires, and
    the guard degrades to a strictly greedy filter that cannot accept any edit
    which trades a small regression for a later first failure. On
    i2c_master_bit_ctrl that stalled the loop at 91 failing testpoints with four
    consecutive rollbacks -- the guard rejecting each partial step of a repair
    that only pays off once several parts land together.
    """
    try:
        obj = json.loads(sim_log_json)
    except Exception:  # noqa: BLE001
        return None
    if str(obj.get("format") or "") == "specflow":
        step = (obj.get("trace") or {}).get("fail_step")
        try:
            return int(step) if step is not None else None
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


def _summarize_sim_log_json(
    sim_log_json: str, *, max_chars: int = 12000, max_value_rows: int = 40
) -> str:
    """Return a compact excerpt from a CommandResult JSON string.

    ``max_chars`` was 4000, which predates this function keeping any per-sample
    mismatch rows (B88). The measured shape on the fp_adder root is ~2.9k of
    scenario verdicts, hints and banner, plus ~110 chars per value row; 40 rows
    therefore needs ~7.3k total. The budget is set so the head+tail clip in
    :func:`_clip_text` does not engage at all for that shape -- a mid-excerpt
    snip would cut a hole in the middle of the value rows, and the skew
    detectors compare row *i* against row *i-N*, so a hole is precisely the
    damage they cannot absorb.
    """
    stdout = ""
    stderr = ""
    try:
        obj = json.loads(sim_log_json)
        stdout = str(obj.get("stdout") or "")
        stderr = str(obj.get("stderr") or "")
    except Exception:  # noqa: BLE001
        return _clip_text(sim_log_json, max_chars=max_chars)

    # An already-structured payload is passed through, not filtered. The
    # vocabulary below was written for a SystemVerilog testbench's stdout, and
    # the comment further down records what happens when a backend speaks a
    # different one: every value row is silently dropped. It happened again.
    # specflow's rows read "CHK-0000 sda_oen: expected=1 got=0 on ena=1, ...",
    # which carries `got=` and `exp` but not the literal "mismatch" the filter
    # requires -- so the debugger received 22 testpoint headers naming the
    # diverging outputs and zero concrete values, and spent its budget on one
    # no-op edit and two cosmetic reformats.
    if str(obj.get("format") or "") == "specflow":
        body = stdout if not stderr else f"{stdout}\n\n[stderr]\n{stderr}"
        return _clip_text(body.strip(), max_chars=max_chars)

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
    # The composition context (the assembler's port maps) is prepended to
    # stdout by the caller so the payload stays valid CommandResult JSON. It is
    # not a "finding", so none of the vocabulary below matches it -- and it is
    # the one thing a glue repairer cannot work without, since it has no tool
    # that can read the wrapper or the children. Kept verbatim, ahead of
    # everything else.
    interesting: list[str] = []
    ctx_start = stdout.find("=== COMPOSITION CONTEXT")
    if ctx_start != -1:
        ctx_end = stdout.find("=== END COMPOSITION CONTEXT", ctx_start)
        if ctx_end != -1:
            end = stdout.find("\n", ctx_end)
            interesting.extend(stdout[ctx_start:(end if end != -1 else len(stdout))].splitlines())
    # The per-sample VALUE rows (B88). Every value-based note in the debug
    # prompt -- operand_passthrough_note, constant_output_lag_note,
    # mismatch_input_skew_note, the latency chain -- reads THIS excerpt, and
    # none of the patterns below matched a row like
    #
    #     MISMATCH at time 80000: a=.. b=.. rnd_mode=0 | sum got=X exp=Y
    #     MISMATCH SUM: a=.. b=.. rnd=2 | got=X exp=Y
    #
    # The nearest one, `"mismatch" in low and "detected" in low`, wants the
    # BANNER ("MISMATCHES DETECTED"), and a value row does not say "detected".
    # So the rows were dropped and every value-based detector read an excerpt
    # with nothing to detect. Swept all 17 debugger prompts in run
    # `fp_adder_e2e`: ZERO carried a single `got=` row, and zero carried a
    # passthrough note -- including the leaf F14 was measured on, so that
    # detector had never once fired in production.
    #
    # This is also why the missing-output-evidence note reads "records the
    # VALUES for only 0 of 168": true of the excerpt, false of the testbench,
    # which recorded all 168. It was accusing the TB of the excerpt's defect.
    value_rows: list[str] = []
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
        elif "mismatch" in low and "got=" in low and "exp" in low:
            value_rows.append(line)

    # Kept CONSECUTIVE from the first, never sampled across the log: the skew
    # detectors compare row i against row i-N, so a scattered sample destroys
    # exactly the structure they exist to find.
    if value_rows:
        kept = value_rows[:max_value_rows]
        dropped = len(value_rows) - len(kept)
        interesting.extend(kept)
        if dropped:
            # No silent caps -- a truncated list that does not say it was
            # truncated reads as the whole population, which is how a 60%
            # passthrough rate would get reported as if measured on 40 rows.
            interesting.append(
                f"[... {dropped} further mismatch rows omitted from this excerpt; "
                f"{len(value_rows)} were recorded in full in the saved log]"
            )
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
3) Call _tool_list_suspect_blocks(), then _tool_read_block(block_id) for the most
   relevant one. Never guess a block_id -- list them first; an invented id costs
   a whole iteration and returns nothing.
4) STAGE the change. _tool_replace_block, _tool_add_block and _tool_remove_block
   all edit a staged buffer: they do not compile, do not simulate, and DO NOT
   COST A TRIAL. So a repair that needs several blocks to change together is one
   batch, not several rejected attempts -- stage every part of it before
   committing anything.
5) _tool_check_staged() -- free and unlimited -- settles syntax and driver
   problems before you pay for a build. Use it; a commit that fails to compile
   costs a trial for something this would have told you for nothing.
6) _tool_commit() compiles and simulates the batch. THIS IS THE TRIAL, and the
   only one. If it improves, the batch is latched. If it does not, the accepted
   RTL is untouched and YOUR STAGED EDITS ARE KEPT -- adjust them and commit
   again rather than starting over. _tool_discard_staged() throws the batch away
   and costs nothing.

Rules:
- Edits are free; commits are not. Think in batches, and commit a coherent
  change rather than a fragment.
- _tool_read_block shows the STAGED text with the line numbers a commit would
  write, so it always reflects your own pending edits. _tool_list_suspect_blocks
  describes the last ACCEPTED design and does not move until a commit lands.
- Removing a block retires its id: reading it afterwards says "removed in this
  staged batch", which is your own edit and not an error.
- If a removal takes away a signal's last driver, add the replacement driver in
  THE SAME batch. Nothing warns you at simulation -- the signal simply goes X
  and every check that reads it stops deciding.
- Do not modify the testbench. Only modify the RTL code.
- Preserve the module interface and the contract's timing assumptions.
- Only modify code inside suspect blocks.
- Keep RTL synthesizable and Verilator-compatible (avoid fancy SVA, no delays).

You will also receive a structured trace-grounded bug report (JSON) that includes:
1) earliest mismatch time, 2) (expected vs actual) values when available, 3) a short input window,
4) a dynamically sliced list of suspect always/assign blocks.

You MUST only modify code inside suspect blocks.
Use tools:
- _tool_list_suspect_blocks()
- _tool_read_block(block_id)
- _tool_replace_block(block_id, new_code)   stage a replacement   free
- _tool_add_block(anchor_id, code)          stage a NEW block after anchor_id,
                                            or at module end with "endmodule"
- _tool_remove_block(block_id)              stage a deletion      free
- _tool_check_staged()                      syntax + drivers      free, unlimited
- _tool_discard_staged()                    back to accepted RTL  free
- _tool_commit()                            build + simulate      ONE TRIAL
- _tool_run_simulation()

These are the exact names the tool schema exposes. Earlier revisions of this
prompt named them without the `_tool_` prefix, which is not what is registered:
across a full live run the model made 0 calls to any bare name, and its attempts
to guess block ids (`Unknown block_id 'A1'`) came from skipping the listing step
rather than calling it under a name the prompt had got wrong.

When simulation passes, end with generate_response using this format:
  generate_response(response="RTL_FIXED: <one-line summary>\nCONTRACT_CLAUSE: <specific contract requirement violated>\nFIX_RATIONALE: <how this change satisfies that requirement>")
"""


def _reads_of(rtl: str, name: str) -> int:
    """Whole-word occurrences of `name` outside comments.

    A declaration is one occurrence, so >1 means the port is consumed
    somewhere. Same counting rule the orchestrator's vestigial detector uses,
    deliberately -- two guards for one invariant must not disagree about what
    "read" means.
    """
    body = re.sub(r"/\*.*?\*/", " ", rtl, flags=re.S)
    body = re.sub(r"//[^\n]*", "", body)
    return len(re.findall(rf"\b{re.escape(name)}\b", body))


def _child_outputs_gone_dark(
    old_rtl: str, new_rtl: str, child_names: Tuple[str, ...],
) -> list[str]:
    """Child-facing inputs the edit turned from READ into unread.

    A child-facing input is an `input` port whose name begins with a child
    module name -- it carries that child's RESULT into the glue. If the glue
    stops reading one, it has recomputed that child's function inline and is no
    longer composing with it.

    Compares BEFORE against AFTER rather than judging the new text alone: a port
    that was already unread is a pre-existing defect this edit did not cause,
    and rolling back for it would trap the debugger with no legal move.
    """
    if not child_names:
        return []
    header = new_rtl.split(");", 1)[0]
    ports = [
        m.group(1)
        for m in re.finditer(r"\binput\s+(?:logic|wire|reg|bit)?\s*(?:\[[^\]]*\]\s*)?(\w+)", header)
        if m.group(1).startswith(tuple(f"{c}_" for c in child_names))
    ]
    return [
        p for p in ports
        if _reads_of(old_rtl, p) > 1 and _reads_of(new_rtl, p) <= 1
    ]


@dataclass
class _EditSession:
    # None when there is no SystemVerilog testbench -- the specflow backend's
    # oracle is a cocotb suite. Nothing in this session reads it; it is kept so
    # a post-mortem can tell which backend produced the session.
    tb_path: str | None
    rtl_path: str
    output_dir: str
    last_mismatch_cnt: int
    sim_reviewer: SimReviewer
    max_trials: int

    # Child module names from the contract's `child_assumes`, empty for a leaf.
    # Present so `_judge_replace_action_execution` can enforce the vestigial-glue
    # rule the debugger's own prompt already promises is "checked MECHANICALLY
    # BEFORE any simulation runs" -- a promise that was not true inside this
    # loop. See `_child_outputs_gone_dark`.
    child_names: Tuple[str, ...] = ()

    #: When False, an edit that increases the mismatch count is KEPT rather than
    #: reverted. The guard exists because a greedy filter is a good default; it
    #: is also, exactly, a hill-climber, and a repair needing several parts to
    #: land together has to pass through a worse state to get there. Turning it
    #: off makes the search able to cross that valley; `best_rtl` below is what
    #: keeps that from being a licence to end up worse than it started.
    rollback_on_regression: bool = True
    #: Best (lowest) mismatch count seen this session, and the RTL that produced
    #: it. Recorded on every simulated edit regardless of accept/rollback, and
    #: restored before `chat()` returns -- so with the guard off the loop is
    #: free to wander uphill while the ANSWER is still the best point found.
    best_mismatch_cnt: int | None = None
    best_rtl: str | None = None

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
    # Monotonic index for the append-only trajectory record. The debug loop used
    # to leave NO evidence of what it did: `debug_sim_output.json` and
    # `trace_report.json` are written to the same path every round, so each
    # iteration destroyed the previous one's, and no model response, tool call,
    # edit diff or per-iteration mismatch count was persisted at all. 79 minutes
    # of debugging on stage_roundpack left one prompt and one final RTL, which
    # made "why did it not converge" unanswerable -- every hypothesis about it
    # was a guess because the falsifying data did not exist.
    traj_iter: int = 0

    #: THE STAGED BUFFER. `None` means nothing is staged and the buffer IS the
    #: accepted RTL on disk. Edits mutate this and never `rtl_path`, which is
    #: what removes rollback entirely: a commit that does not improve never
    #: overwrote anything, so there is nothing to put back and the agent's work
    #: is not destroyed by a failed attempt.
    staged_rtl: str | None = None
    #: Each block's CURRENT text in the staged buffer, so a second edit to the
    #: same block anchors on what the first one wrote rather than on the
    #: original. Without it, refining your own staged edit is indistinguishable
    #: from editing against a destroyed anchor.
    staged_text: Dict[str, str] = field(default_factory=dict)
    #: Blocks removed in this batch. A later `read_block` on one of these says
    #: "removed", not "unknown block_id" -- different facts, and the second
    #: reads as the agent's mistake rather than its own edit.
    retired_ids: set = field(default_factory=set)
    #: `check_staged()` calls. Unbounded (it is static and costs about a second)
    #: but COUNTED and reported: fifty dry runs against two commits is a finding
    #: about the agent, and a silent cap would hide it.
    check_calls: int = 0

    def read_rtl(self) -> str:
        with open(self.rtl_path, "r", encoding="utf-8") as f:
            return f.read()

    def read_rtl_with_lineno(self) -> str:
        lines = self.read_rtl().splitlines()
        return "\n".join(f"{i+1}: {line}" for i, line in enumerate(lines)) + "\n"

    def write_rtl(self, content: str) -> None:
        with open(self.rtl_path, "w", encoding="utf-8") as f:
            f.write(content)

    # ------------------------------------------------------------ staging
    #
    # Edits mutate a buffer; only `commit` builds and runs. A coherent change
    # spanning several blocks could not be expressed before, because every
    # intermediate state was simulated on the spot and rolled back as a
    # regression -- and a batch legitimately passes through broken intermediate
    # states, which is the whole point.

    def staged(self) -> str:
        """The buffer edits apply to: the staged text, or the accepted RTL."""
        return self.staged_rtl if self.staged_rtl is not None else self.read_rtl()

    def _anchor_for(self, block_id: str) -> str | None:
        """This block's CURRENT text in the staged buffer.

        Falls back to the text the trace report extracted, which is right until
        the block has been staged over. Tracking it per block is what lets an
        agent REFINE its own staged edit -- anchoring on the original text
        forever would make the second edit to a block indistinguishable from an
        edit against an anchor some other edit destroyed.
        """
        if block_id in self.retired_ids:
            # REMOVED is not UNKNOWN, and not "your anchor was destroyed"
            # either. Falling through to `blocks_by_id` here would report the
            # agent's own deletion back to it as a collision with some other
            # edit -- three different facts, and only one of them is true.
            return None
        if block_id in self.staged_text:
            return self.staged_text[block_id]
        block = (self.blocks_by_id or {}).get(block_id)
        return block.code if block else None

    def _splice(self, anchor: str, replacement: str, what: str) -> Dict[str, Any]:
        """Content-anchored substitution. NEVER line numbers.

        `blocks_by_id` carries line bounds from the last trace report, and one
        staged edit shifts every line after it. Under batching a second edit
        against stale bounds would splice into the wrong place SILENTLY, so the
        anchor is the block's text and a miss is an explicit refusal.
        """
        buf = self.staged()
        found = buf.count(anchor)
        if found == 0:
            # TWO causes, and naming only one of them sends the agent looking in
            # the wrong place. Within a batch it means an earlier staged edit
            # overlapped this block; after a commit LATCHED it means the block
            # table still describes the design from before that commit, which
            # `_refresh_trace` only rebuilds when the run still has mismatches.
            return {"is_action_executed": False, "error_msg": (
                f"Cannot {what}: its text is not in the buffer. Either an earlier "
                f"staged edit overlapped it, or a commit has latched since the "
                f"block list was built. read_block({what.split()[-1]!r}) shows "
                f"what is actually there; list_suspect_blocks() rebuilds the "
                f"list against the accepted design.")}
        if found > 1:
            return {"is_action_executed": False, "error_msg": (
                f"Cannot {what}: its text appears {found} times in the staged "
                f"buffer, so a substitution would be ambiguous. Include "
                f"surrounding lines to make it unique.")}
        self.staged_rtl = buf.replace(anchor, replacement, 1)
        return {"is_action_executed": True}

    def undriven_signals(self, text: str) -> list[str]:
        """Signals a still-read name has lost its last driver for.

        The mirror of `multidriven_signals`, and it exists because the failure
        is otherwise silent: Verilator runs `-Wno-fatal` (deliberately -- the
        lint gate owns lint findings), so UNDRIVEN does not fail the build. The
        signal becomes X, the oracle X-guard turns that into an abstention, and
        removing a driver would surface only as coverage quietly falling with
        nothing naming the cause.
        """
        blocks = list((self.blocks_by_id or {}).values())
        if not blocks:
            return []
        driven = {w for b in blocks if b.code in text for w in b.writes}
        read = {r for b in blocks if b.code in text for r in b.reads}
        lost = {w for b in blocks if b.code not in text for w in b.writes}
        return sorted(w for w in lost - driven if w in read)

    def driver_warnings(self) -> list[str]:
        """Driver hazards in the staged buffer. WARNINGS, never refusals.

        A batch that removes a block and adds its replacement two edits later is
        legitimately undriven in between, so refusing here would break exactly
        the workflow staging exists for. `commit` rejects what is still
        unresolved once the batch is claimed complete.

        PURE PYTHON, from the block table, because this runs on EVERY staged
        edit. `multidriven_signals` shells out to Verilator and costs about a
        second, which is fine once per `check_staged` and far too much per
        keystroke -- so the multi-driver half here is the cheap approximation
        (a signal two surviving blocks both write) and the authoritative check
        runs where it is affordable.
        """
        text = self.staged()
        blocks = list((self.blocks_by_id or {}).values())
        out = []
        writers: Dict[str, int] = {}
        for b in blocks:
            if b.code in text and b.kind == "assign":
                for w in b.writes:
                    writers[w] = writers.get(w, 0) + 1
        multi = sorted(w for w, n in writers.items() if n > 1)
        if multi:
            out.append(f"{', '.join(multi)} look to have MORE THAN ONE "
                       f"continuous driver (confirm with check_staged)")
        gone = self.undriven_signals(text)
        if gone:
            out.append(f"{', '.join(gone)} are still read but have LOST their "
                       f"last driver")
        return out

    def stage_replace(self, block_id: str, new_code: str) -> Dict[str, Any]:
        anchor = self._anchor_for(block_id)
        if anchor is None:
            return {"is_action_executed": False, "error_msg": (
                f"removed in this staged batch: {block_id}"
                if block_id in self.retired_ids
                else f"Unknown block_id '{block_id}'. Use list_suspect_blocks() first.")}
        body = new_code.rstrip("\n")
        res = self._splice(anchor, body, f"replace {block_id}")
        if res.get("is_action_executed"):
            self.staged_text[block_id] = body
            res["warnings"] = self.driver_warnings()
        return res

    def stage_remove(self, block_id: str) -> Dict[str, Any]:
        anchor = self._anchor_for(block_id)
        if anchor is None:
            return {"is_action_executed": False, "error_msg": (
                f"removed in this staged batch: {block_id}"
                if block_id in self.retired_ids
                else f"Unknown block_id '{block_id}'. Use list_suspect_blocks() first.")}
        res = self._splice(anchor, "", f"remove {block_id}")
        if res.get("is_action_executed"):
            self.staged_text.pop(block_id, None)
            self.retired_ids.add(block_id)
            res["warnings"] = self.driver_warnings()
        return res

    def stage_add(self, anchor_id: str, code: str) -> Dict[str, Any]:
        """Insert after `anchor_id`, or before `endmodule` when that is named.

        Without this the editor can only rewrite blocks the slice found: a
        repair needing a new register, state or `always_ff` is unreachable.
        """
        body = code.rstrip("\n")
        if anchor_id == "endmodule":
            buf = self.staged()
            if buf.count("endmodule") != 1:
                return {"is_action_executed": False, "error_msg": (
                    "Cannot add at module end: 'endmodule' does not appear "
                    "exactly once.")}
            self.staged_rtl = buf.replace("endmodule", body + "\n\nendmodule", 1)
            return {"is_action_executed": True, "warnings": self.driver_warnings()}
        anchor = self._anchor_for(anchor_id)
        if anchor is None:
            return {"is_action_executed": False, "error_msg": (
                f"removed in this staged batch: {anchor_id}"
                if anchor_id in self.retired_ids
                else f"Unknown anchor '{anchor_id}'. Pass a block_id from "
                     f"list_suspect_blocks(), or \"endmodule\".")}
        res = self._splice(anchor, anchor + "\n\n" + body, f"add after {anchor_id}")
        if res.get("is_action_executed"):
            res["warnings"] = self.driver_warnings()
        return res

    def discard_staged(self) -> Dict[str, Any]:
        """Back to the last accepted RTL. Costs nothing: nothing was written."""
        self.staged_rtl = None
        self.staged_text.clear()
        self.retired_ids.clear()
        return {"is_action_executed": True}

    def _static_findings(self, text: str) -> tuple[bool, str, list[str], list[str]]:
        """Syntax and drivers for `text`, WITHOUT touching `check_calls`.

        Shared by `check_staged` (the agent's dry run, which counts) and by
        `commit`'s pre-flight (which must not). `check_calls` is reported as a
        finding about the agent -- fifty dry runs against two commits -- so
        counting commit's own internal checks there would corrupt the very
        number it exists to expose.

        Written to a scratch file because both `check_syntax` and
        `multidriven_signals` take a PATH and shell out to Verilator. The
        accepted RTL is never the file they read.
        """
        scratch = Path(self.output_dir) / "staged.sv"
        scratch.write_text(text, encoding="utf-8")
        ok, out = check_syntax(str(scratch))
        # The AUTHORITATIVE multi-driver check, which `driver_warnings` only
        # approximates because it cannot afford Verilator per edit.
        warnings = list(self.driver_warnings())
        try:
            multi = sorted(multidriven_signals(str(scratch)))
        except Exception:  # noqa: BLE001
            multi = []
        if multi:
            warnings.append(f"{', '.join(multi)} have MORE THAN ONE continuous "
                            f"driver (Verilator)")
        return ok, out, warnings, multi

    def check_staged(self) -> Dict[str, Any]:
        """Static only: syntax and drivers. No simulation, NO TRIAL.

        The expensive thing is the suite; syntax and drivers cost about a
        second. Settling those for free, then spending the trial on the question
        only simulation can answer, prices each check at what it actually costs
        -- and is what makes "a failed commit costs a trial" a fair rule rather
        than charging a typo the same as a wrong design hypothesis.
        """
        self.check_calls += 1
        ok, out, warnings, multi = self._static_findings(self.staged())
        return {"is_syntax_correct": ok, "syntax_output": out,
                "warnings": warnings, "multidriven": multi,
                "staged": self.staged_rtl is not None,
                "check_calls": self.check_calls}

    def commit(self) -> Dict[str, Any]:
        """Build and run the STAGED buffer. ONE TRIAL. Latch, or keep the batch.

        The trial is here and not on the edits, which is what `max_trials`
        always claimed to count: 30 compile-and-test cycles, with the edits
        inside each one free. A budget counting individual edits is an order of
        magnitude tighter than one counting rounds, and it charged an agent for
        thinking rather than for simulating.

        WHAT A FAILED COMMIT COSTS: a trial, and nothing else. The accepted RTL
        is byte-identical afterwards and THE STAGED BUFFER SURVIVES, so the
        agent adjusts its batch rather than starting over from the baseline.
        That is what makes `commit` itself the test -- a separate `test_staged`
        would only be a commit that refuses to bank a good result.

        The mechanism is a write-run-restore rather than a build at a scratch
        path, and the difference is worth naming: `sim_review` derives the RTL
        it compiles from its run directory (`{output_path_per_run}/rtl.sv`), so
        a genuinely separate build location means a separate run directory --
        and on the specflow backend there is no `tb.sv` to copy into one, the
        suite lives elsewhere. The OBSERVABLE contract is the same and is
        pinned: after a commit that does not latch, `read_rtl()` returns exactly
        what it returned before.

        The static pre-flight is not redundant with the judge. The judge checks
        syntax and MULTI-driver; only here is the mirror case checked -- a
        removal that took away a signal's LAST driver. Verilator runs
        `-Wno-fatal` so UNDRIVEN does not fail the build: the signal becomes X,
        the oracle X-guard turns that into an abstention, and the defect would
        surface only as coverage quietly falling with nothing naming the cause.
        """
        result = self._base_result()
        if self.staged_rtl is None:
            result["error_msg"] = (
                "Nothing is staged, so there is nothing to commit. No trial was "
                "consumed. Use add_block/replace_block/remove_block first.")
            return result

        # REFUSED BEFORE THE COUNTER MOVES, and staging stays open afterwards so
        # the agent can still be asked to explain itself.
        if self.action_calls >= self.max_trials:
            result["error_msg"] = (
                f"Reached maximum debug trials ({self.max_trials}); refusing to "
                f"commit. Staged edits are kept and staging remains open.")
            return result
        self.action_calls += 1

        accepted = self.read_rtl()
        staged = self.staged_rtl
        pre_multi = set(multidriven_signals(self.rtl_path))

        ok, syntax_out, warnings, multi = self._static_findings(staged)
        result["is_syntax_correct"] = ok
        result["syntax_output"] = syntax_out
        result["warnings"] = warnings
        result["action_calls"] = self.action_calls
        result["trials_left"] = max(0, self.max_trials - self.action_calls)
        result["staged_kept"] = True
        result["check_calls"] = self.check_calls

        if not ok:
            result["error_msg"] = (
                "Commit rejected: the staged buffer does not compile. This cost "
                "a trial -- check_staged() would have told you the same thing "
                "for free. The accepted RTL is untouched and your staged edits "
                "are kept; fix them and commit again.")
            return result

        introduced = sorted(set(multi) - pre_multi)
        if introduced:
            result["error_msg"] = (
                "Commit rejected: the batch gave " + ", ".join(introduced)
                + " MORE THAN ONE continuous driver. The accepted RTL is "
                "untouched and your staged edits are kept. Remove the duplicate "
                "assignment -- most often the replacement re-declares something "
                "that already exists outside the block it replaced.")
            return result

        lost = self.undriven_signals(staged)
        if lost:
            result["error_msg"] = (
                "Commit rejected: " + ", ".join(lost)
                + " are still read but the batch removed their LAST driver. "
                "Verilator runs -Wno-fatal, so this would not have failed the "
                "build -- the signal would go X, every check reading it would "
                "abstain, and coverage would fall with nothing naming the "
                "cause. Add the replacement driver to this batch, or restore "
                "the block you removed.")
            return result

        if self.child_names:
            went_dark = _child_outputs_gone_dark(accepted, staged, self.child_names)
            if went_dark:
                result["error_msg"] = (
                    "Commit rejected: it left " + ", ".join(sorted(went_dark))
                    + " READ BY NOTHING. That port carries a CHILD'S RESULT into "
                    "this glue, and the batch recomputed the child's function "
                    "inline instead of routing its output. Restore the "
                    "assignment that consumes the port.")
                return result

        self.write_rtl(staged)
        # The judge owns the ratchet, the fail-time allowance, `best_rtl` and the
        # restore. Reusing it keeps ONE accept criterion rather than a second
        # one here that would drift away from it.
        judged = self._judge_replace_action_execution(
            old_file_content=accepted, pre_multidriven=pre_multi,
        )
        judged["action_calls"] = self.action_calls
        judged["trials_left"] = max(0, self.max_trials - self.action_calls)
        judged["check_calls"] = self.check_calls
        judged["warnings"] = warnings
        if judged.get("is_action_executed"):
            # LATCHED: the accepted RTL now IS the staged text, so there is no
            # longer a batch pending. Anything staged next anchors on what was
            # just banked.
            self.staged_rtl = None
            self.staged_text.clear()
            self.retired_ids.clear()
            judged["staged_kept"] = False
        else:
            # The judge restored the accepted bytes. The batch is NOT discarded:
            # losing the agent's work is the cost staging exists to remove.
            judged["staged_kept"] = True
        return judged

    def note_best(self, mismatch_cnt: int, rtl_text: str) -> bool:
        """Record `rtl_text` if it is the best seen. Returns True when it is.

        Ties do NOT overwrite: the earliest RTL achieving a given count is kept,
        so a run that wanders across a plateau returns the point it reached
        first rather than the last one it happened to touch.
        """
        try:
            cnt = int(mismatch_cnt)
        except Exception:  # noqa: BLE001
            return False
        if self.best_mismatch_cnt is None or cnt < self.best_mismatch_cnt:
            self.best_mismatch_cnt = cnt
            self.best_rtl = rtl_text
            return True
        return False

    def restore_best(self) -> bool:
        """Put the best-seen RTL back on disk. Returns True if it changed anything.

        A no-op when the guard is on, because a monotone search already ends at
        its best point. Load-bearing when it is off.
        """
        if self.best_rtl is None:
            return False
        if self.read_rtl() == self.best_rtl:
            return False
        self.write_rtl(self.best_rtl)
        return True

    def run_simulation(self) -> Dict[str, Any]:
        is_sim_pass, sim_mismatch_cnt, sim_output = self.sim_reviewer.review()
        # Persist full sim output for human inspection; provide excerpt to the agent.
        try:
            Path(self.output_dir, "debug_sim_output.json").write_text(sim_output, encoding="utf-8")
            # ALSO keep this iteration's copy. The unsuffixed file is overwritten
            # every round, so a post-mortem could only ever see the last one --
            # which is how 79 minutes of stage_roundpack debugging left no record
            # of the iteration where it went wrong.
            try:
                Path(self.output_dir, f"debug_sim_output_i{self.traj_iter + 1}.json").write_text(
                    sim_output, encoding="utf-8")
            except Exception:  # noqa: BLE001
                pass
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
        """The block AS STAGED, with the line numbers a commit would write.

        Reading the trace report's copy instead would show the agent the text it
        edited away from -- and its line numbers, which one staged edit above it
        has already invalidated. Locating the block in the staged buffer makes
        both true at once, which is what lets an agent refine its own batch
        instead of guessing what is currently in it.
        """
        if block_id in self.retired_ids:
            return (f"ERROR: '{block_id}' was removed in this staged batch. It is "
                    f"not an unknown block -- you deleted it. discard_staged() "
                    f"brings it back along with the rest of the batch.")
        text = self._anchor_for(block_id)
        if text is None:
            return f"ERROR: Unknown block_id '{block_id}'."
        buf = self.staged()
        idx = buf.find(text)
        if idx < 0:
            return (f"ERROR: '{block_id}' is no longer in the staged buffer -- an "
                    f"earlier staged edit overlapped it. list_suspect_blocks() "
                    f"describes the last ACCEPTED design; discard_staged() "
                    f"returns to it.")
        start = buf.count("\n", 0, idx) + 1
        lines = text.splitlines()
        return "\n".join(f"{start + i}: {line}" for i, line in enumerate(lines)) + "\n"

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

    def _record_trajectory(
        self,
        action: str,
        *,
        result: Dict[str, Any] | None = None,
        block_id: str | None = None,
        diff: str | None = None,
        model_text: str | None = None,
    ) -> None:
        """Append one line to `debug_trajectory.jsonl`. Never raises.

        Most of this already exists in the result dict `_judge_replace_action_execution`
        builds -- prev_mismatch_cnt, new_fail_time, error_msg, accept_reason,
        is_action_executed -- and was handed to the model and then dropped on the
        floor. Recording it costs a diff and a few integers per iteration.
        """
        try:
            self.traj_iter += 1
            r = result or {}
            row = {
                "iter": self.traj_iter,
                "action": action,
                "block_id": block_id,
                "accepted": bool(r.get("is_action_executed")),
                "syntax_ok": r.get("is_syntax_correct"),
                "sim_pass": r.get("is_sim_pass"),
                "mismatch_before": r.get("prev_mismatch_cnt"),
                "mismatch_after": r.get("sim_mismatch_cnt"),
                "fail_time_before": r.get("prev_fail_time"),
                "fail_time_after": r.get("new_fail_time"),
                "rollback_reason": (r.get("error_msg") or None),
                "accept_reason": (r.get("accept_reason") or None),
                "action_calls": self.action_calls,
                "diff": (diff or "")[:4000] or None,
                "model_text": (model_text or "")[:1500] or None,
            }
            path = Path(self.output_dir, "debug_trajectory.jsonl")
            with open(path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        except Exception:  # noqa: BLE001
            # Observability must never break the loop it observes.
            pass

    def backfill_model_text(self, first_iter: int, text: str | None) -> None:
        """Attach a completed turn's reasoning to the edits it produced.

        Reading the agent's memory at TOOL time does not work: in agentscope's
        ReAct loop the tool executes before the assistant message is committed,
        so `replace_block` is logged while the reasoning for that very turn does
        not exist yet. Measured live on stage_roundpack 2026-08-02 — four
        trajectory entries, `model_text` None on every one, and no `model_turn`
        entry at all because the turn had not returned. An earlier attempt to
        read `self._agent.memory` from inside the tool passed its unit tests
        against a hand-built memory and produced nothing whatsoever in
        production, which is the same shape of mistake as B23: a probe verified
        only against the caller it was written for.

        So do it from the other side. `chat()` knows the reasoning once the turn
        returns, and knows which trajectory rows that turn wrote; this rewrites
        exactly those rows. Never raises: observability must not break the loop
        it observes.
        """
        if not text:
            return
        try:
            path = Path(self.output_dir, "debug_trajectory.jsonl")
            if not path.exists():
                return
            rows = []
            for line in path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                except Exception:  # noqa: BLE001
                    rows.append(line)
                    continue
                if (
                    isinstance(row, dict)
                    and row.get("iter", 0) >= first_iter
                    and row.get("action") == "replace_block"
                    and not row.get("model_text")
                ):
                    row["model_text"] = text[:1500]
                rows.append(json.dumps(row, ensure_ascii=False) if isinstance(row, dict) else row)
            path.write_text("\n".join(rows) + "\n", encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass

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

    def _judge_replace_action_execution(
        self, *, old_file_content: str, pre_multidriven: set[str] | None = None,
    ) -> Dict[str, Any]:
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

        # A duplicated continuous assignment is a design error, not a style
        # nit, and check_syntax is deliberately permissive about warnings so it
        # sails through. Reject BEFORE simulating: the sim would either mask it
        # (last-writer-wins) or blame the datapath for an X.
        new_multi = multidriven_signals(self.rtl_path)
        introduced = new_multi - (pre_multidriven or set())
        if introduced:
            self.write_rtl(old_file_content)
            result = self._base_result()
            result["is_syntax_correct"] = True
            result["error_msg"] = (
                "Edit rolled back: it gave "
                + ", ".join(sorted(introduced))
                + " MORE THAN ONE continuous driver. Your replacement text re-declares "
                "assignments that already exist OUTSIDE the block you replaced, so the "
                "splice duplicated them. Replace ONLY the lines inside the block, and do "
                "not repeat assignments that live elsewhere in the module."
            )
            return result

        # VESTIGIAL GLUE, enforced where the prompt already says it is enforced.
        #
        # The debugger's own instructions state this rule is "checked
        # MECHANICALLY BEFORE any simulation runs". That was true of the
        # orchestrator's composition gate and NOT true here, inside the debug
        # loop -- so the model was told a guard existed at a point where nothing
        # checked, and acted accordingly.
        #
        # Measured on fp_align_add parent_16 (2026-08-04): given
        # "Contract violation: exp_large_correct", the debugger replaced
        #     assign exp_large = fp_compare_exp_sig_exp_large;
        # with
        #     assign exp_large = ((exp_a > exp_b) || ...) ? exp_a : exp_b;
        # -- recomputing the child's function inline. That satisfies the
        # assertion and destroys the composition: the child's output is then
        # read by nothing. Six iterations and four accepted edits produced a
        # byte-identical failure each time, and the glue was headed for a
        # vestigial rejection at the gate with its whole budget already spent.
        #
        # Narrow by construction: fires only when a child-facing input that WAS
        # read becomes unread. An edit leaving the wiring intact cannot trip it,
        # and a leaf (no `child_assumes`, so `child_names` empty) is untouched.
        if self.child_names:
            went_dark = _child_outputs_gone_dark(
                old_file_content, self.read_rtl(), self.child_names,
            )
            if went_dark:
                self.write_rtl(old_file_content)
                result = self._base_result()
                result["is_syntax_correct"] = True
                result["error_msg"] = (
                    "Edit rolled back: it left "
                    + ", ".join(sorted(went_dark))
                    + " READ BY NOTHING. That port carries a CHILD'S RESULT into this "
                    "glue, and your replacement recomputed that child's function inline "
                    "instead of routing its output. This is the VESTIGIAL GLUE rejection "
                    "described in your instructions: it is checked before simulation, and "
                    "no simulation result can excuse it, because a glue that recomputes a "
                    "child has stopped composing with that child. Restore the assignment "
                    "that consumes the port. If its value looks wrong, the defect is in "
                    "the child or in how this glue drives that child's INPUTS -- say so "
                    "rather than replacing the port with your own arithmetic."
                )
                return result

        is_sim_pass, sim_mismatch_cnt, sim_output = self.sim_reviewer.review()
        result["is_sim_pass"] = is_sim_pass
        result["sim_mismatch_cnt"] = sim_mismatch_cnt
        try:
            Path(self.output_dir, "debug_sim_output.json").write_text(sim_output, encoding="utf-8")
            # ALSO keep this iteration's copy. The unsuffixed file is overwritten
            # every round, so a post-mortem could only ever see the last one --
            # which is how 79 minutes of stage_roundpack debugging left no record
            # of the iteration where it went wrong.
            try:
                Path(self.output_dir, f"debug_sim_output_i{self.traj_iter + 1}.json").write_text(
                    sim_output, encoding="utf-8")
            except Exception:  # noqa: BLE001
                pass
        except Exception:  # noqa: BLE001
            pass
        result["sim_output_excerpt"] = _summarize_sim_log_json(sim_output)
        result["sim_output_path"] = str(Path(self.output_dir, "debug_sim_output.json"))
        result["prev_mismatch_cnt"] = prev_mismatch_cnt
        result["prev_fail_time"] = prev_fail_time
        new_fail_time = _extract_fail_time_from_sim_log_json(sim_output)
        result["new_fail_time"] = new_fail_time

        # Recorded BEFORE the accept/rollback decision, because a regressing
        # edit is exactly when the best-so-far matters, and because an edit that
        # improves things is worth checkpointing whether or not a later one
        # undoes it.
        improved_best = self.note_best(sim_mismatch_cnt, self.read_rtl())
        result["best_mismatch_cnt"] = self.best_mismatch_cnt

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
            if not allow and self.rollback_on_regression:
                self.write_rtl(old_file_content)
                result["error_msg"] = (
                    "Mismatch_cnt increased after replacement. Action rolled back. "
                    f"(prev={prev_mismatch_cnt}, new={sim_mismatch_cnt}, prev_fail_time={prev_fail_time}, new_fail_time={new_fail_time})"
                )
                return result
            if not allow:
                # Guard off: keep the regression and say so plainly. The agent
                # is told the count went UP so it can judge whether it is part
                # way through a multi-part repair or simply wrong -- reporting
                # this as an ordinary acceptance would hide the one fact it
                # needs to decide that.
                result["accept_reason"] = (
                    f"KEPT DESPITE REGRESSION (rollback guard off): mismatches "
                    f"{prev_mismatch_cnt} -> {sim_mismatch_cnt} (+{increase}). "
                    f"Best seen this session is {self.best_mismatch_cnt}, and that "
                    "version is what will be returned if nothing beats it. If this "
                    "edit is one part of a repair that needs several parts to land "
                    "together, continue; if it was simply wrong, revert it yourself."
                )
            else:
                result["accept_reason"] = (
                    "Accepted despite slight mismatch increase because earliest mismatch moved later "
                    f"(+{increase} mismatches, fail_time {prev_fail_time}->{new_fail_time})."
                )
        elif improved_best:
            result["accept_reason"] = (
                f"New best: {sim_mismatch_cnt} mismatches."
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

    # `replace_block` -- the immediate-latch splice -- is DELETED, not kept for
    # compatibility. It spliced by LINE NUMBER, wrote `rtl_path` on the spot,
    # simulated, and rolled back on regression; every one of those is wrong now.
    # Line numbers shift under a staged edit above them, writing on the spot is
    # what made rollback necessary, and rolling back is what destroyed the
    # agent's work. `stage_replace` + `commit` replace it. A method left here
    # would still latch, silently, from any caller that had not been updated.


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

    staged_note = ""
    if session.staged_rtl is not None:
        pending = sorted(set(session.staged_text) | set(session.retired_ids))
        staged_note = (
            "You have edits STAGED and not yet committed"
            + (f" (blocks touched: {', '.join(pending)})" if pending else "")
            + ". They are not in the design until _tool_commit() latches them.\n\n"
        )

    return (
        f"{last_action_block}"
        f"{staged_note}"
        f"Current accepted state: {session.last_mismatch_cnt} mismatches{fail_time_note}.\n"
        f"Trials used: {session.action_calls}/{session.max_trials} "
        f"(a trial is a commit; edits and check_staged are free).\n\n"
        "Continue debugging. Preserve the contract and module interface. If mismatches remain, "
        "pick a suspect block and call _tool_read_block(block_id), stage every part of the fix with "
        "_tool_replace_block / _tool_add_block / _tool_remove_block, settle syntax and drivers with "
        "_tool_check_staged(), then call _tool_commit() ONCE for the whole batch. A commit that does "
        "not improve keeps your staged edits — adjust them rather than starting over. Do NOT call "
        "generate_response until a commit reports is_sim_pass=true with 0 mismatches — an unverified "
        "claim of success is not accepted as done."
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
        #: None reads EDA_ROLLBACK_GUARD from the environment ("off"/"0"/"false"
        #: disable it); anything explicit wins over the environment. The guard
        #: stays ON by default -- a greedy filter is the right default, and this
        #: exists to make its cost measurable rather than to remove it.
        rollback_guard: bool | None = None,
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
        # Crossing a valley takes several consecutive non-improving rounds by
        # definition, so a stall limit tuned for a monotone search will cut the
        # search off before it can get anywhere. Overridable rather than derived
        # from `rollback_guard`, because tying them together would silently
        # change one knob when the caller set the other.
        try:
            stall_rounds = int(os.environ.get("EDA_STALL_ROUNDS") or stall_rounds)
        except ValueError:
            pass
        self._stall_rounds = max(1, int(stall_rounds))
        self._rollback_guard = resolve_rollback_guard(rollback_guard)
        self._session: _EditSession | None = None

        toolkit = GuidingToolkit()
        toolkit.register_tool_function(self._tool_list_suspect_blocks)
        toolkit.register_tool_function(self._tool_read_block)
        # The STAGING surface. Edits are free and latch nothing; `commit` is the
        # trial. Without these registered the staged buffer is unreachable --
        # the methods exist on the session and no agent can call them.
        toolkit.register_tool_function(self._tool_replace_block)
        toolkit.register_tool_function(self._tool_add_block)
        toolkit.register_tool_function(self._tool_remove_block)
        toolkit.register_tool_function(self._tool_check_staged)
        toolkit.register_tool_function(self._tool_discard_staged)
        toolkit.register_tool_function(self._tool_commit)
        toolkit.register_tool_function(self._tool_run_simulation)

        # Held on the instance so `usage()` can read the cumulative counters
        # off it. Constructed inline it is reachable only through the agent.
        self._model = make_openai_model(cfg, cache_key="rtl-debug")
        self._agent = SafeReActAgent(
            name="Debugger",
            sys_prompt=SYSTEM_PROMPT,
            model=self._model,
            formatter=make_formatter(cfg.model),
            toolkit=toolkit,
            memory=InMemoryMemory(),
            max_iters=10,
        )

    def usage(self) -> tuple[int, int, int]:
        """`(input, cached, output)` for this editor's model, cumulative.

        `cached` is a SUBSET of `input`, and it is the number that decides
        whether a long tool-using loop is cheap or ruinous. A trial re-sends a
        growing conversation through a ReAct sub-loop of up to `max_iters`
        calls, so input dominates the ledger -- and a re-sent prefix that hits
        the cache and one that misses it look identical in the input total
        alone. Measured on the refmodel loop, which is the same shape: 46.1M
        input tokens on a2-i2c against 10.8M for every specflow stage combined.

        A zero here means "nothing recorded yet", not "no cache hits"; the two
        are only distinguishable because `input` is reported beside it.
        """
        from .model import get_model_cached, get_model_usage

        model = getattr(self, "_model", None)
        got = get_model_usage(model)
        return got[0], get_model_cached(model), got[1]

    def reset(self) -> None:
        clear_memory_safely(self._agent)
        self._session = None

    async def _tool_list_suspect_blocks(self) -> ToolResponse:
        """List dynamically sliced suspect blocks (always/assign)."""
        if self._session is None:
            return ToolResponse(content=[{"type": "text", "text": "ERROR: No active edit session."}])
        blocks = self._session.list_suspect_blocks()
        # §12: the slice comes from a trace report built on the last ACCEPTED
        # RTL, so after several staged edits it describes an older design. That
        # is acceptable -- the slice is a hint, not an authority -- but it has
        # to SAY so, or the agent reads stale line numbers as current ones.
        if self._session.staged_rtl is not None:
            payload = {
                "note": ("This list was built from the last ACCEPTED RTL and "
                         "does not include your staged edits. Line numbers here "
                         "predate them; read_block(block_id) shows the staged "
                         "text at the line numbers a commit would write."),
                "blocks": blocks,
            }
        else:
            payload = blocks
        return ToolResponse(content=[{"type": "text", "text": json.dumps(payload, indent=2)}])

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
        self._session._record_trajectory("run_simulation", result=result)
        return ToolResponse(content=[{"type": "text", "text": json.dumps(result, indent=4)}])

    async def _tool_replace_block(self, block_id: str, new_code: str) -> ToolResponse:
        """Stage a replacement for a suspect block. Free: no compile, no simulation, no trial. Call commit() to build and test the batch."""
        if self._session is None:
            return ToolResponse(content=[{"type": "text", "text": "ERROR: No active edit session."}])
        before = self._session._anchor_for(block_id) or ""
        result = await asyncio.to_thread(self._session.stage_replace, block_id, new_code)
        # The DIFF, not the whole file: what the model actually tried is the
        # thing that was never recorded, and it is what a post-mortem needs.
        try:
            import difflib
            diff = "".join(difflib.unified_diff(
                (before or "").splitlines(keepends=True),
                (new_code or "").splitlines(keepends=True),
                fromfile=f"{block_id}.before", tofile=f"{block_id}.after", n=2,
            ))
        except Exception:  # noqa: BLE001
            diff = None
        # model_text is filled in by chat()'s backfill once the turn returns --
        # at THIS point in agentscope's ReAct loop the assistant message for the
        # current turn has not been committed to memory yet, so there is nothing
        # here to read. See _EditSession.backfill_model_text.
        self._session._record_trajectory(
            "replace_block", result=result, block_id=block_id, diff=diff,
        )
        # Even if the action was rolled back, return the latest available trace pointer/summary
        # so the agent can re-ground itself quickly.
        if self._session.trace_report:
            result.setdefault("trace_summary", self._session.trace_summary())
        self._session.last_action_result = result
        return ToolResponse(content=[{"type": "text", "text": json.dumps(result, indent=4)}])

    async def _tool_add_block(self, anchor_id: str, code: str) -> ToolResponse:
        """Stage a NEW block after block `anchor_id`, or at module end when anchor_id is "endmodule". Free: no compile, no simulation, no trial."""
        if self._session is None:
            return ToolResponse(content=[{"type": "text", "text": "ERROR: No active edit session."}])
        result = await asyncio.to_thread(self._session.stage_add, anchor_id, code)
        self._session._record_trajectory("add_block", result=result, block_id=anchor_id,
                                         diff=code)
        self._session.last_action_result = result
        return ToolResponse(content=[{"type": "text", "text": json.dumps(result, indent=4)}])

    async def _tool_remove_block(self, block_id: str) -> ToolResponse:
        """Stage the DELETION of a suspect block. Free: no compile, no simulation, no trial. Its id is then retired, not unknown."""
        if self._session is None:
            return ToolResponse(content=[{"type": "text", "text": "ERROR: No active edit session."}])
        before = self._session._anchor_for(block_id) or ""
        result = await asyncio.to_thread(self._session.stage_remove, block_id)
        self._session._record_trajectory("remove_block", result=result,
                                         block_id=block_id, diff=before)
        self._session.last_action_result = result
        return ToolResponse(content=[{"type": "text", "text": json.dumps(result, indent=4)}])

    async def _tool_check_staged(self) -> ToolResponse:
        """Syntax and driver check on the staged batch. Static only: no simulation and NO TRIAL, so it is free and unlimited."""
        if self._session is None:
            return ToolResponse(content=[{"type": "text", "text": "ERROR: No active edit session."}])
        result = await asyncio.to_thread(self._session.check_staged)
        self._session._record_trajectory("check_staged", result=result)
        return ToolResponse(content=[{"type": "text", "text": json.dumps(result, indent=4)}])

    async def _tool_discard_staged(self) -> ToolResponse:
        """Throw away every staged edit and return to the last accepted RTL. Costs no trial."""
        if self._session is None:
            return ToolResponse(content=[{"type": "text", "text": "ERROR: No active edit session."}])
        result = await asyncio.to_thread(self._session.discard_staged)
        self._session._record_trajectory("discard_staged", result=result)
        self._session.last_action_result = result
        return ToolResponse(content=[{"type": "text", "text": json.dumps(result, indent=4)}])

    async def _tool_commit(self) -> ToolResponse:
        """Compile and simulate the staged batch. THIS IS THE TRIAL. Improved -> latched; not improved -> the accepted RTL is untouched and your staged edits are kept."""
        if self._session is None:
            return ToolResponse(content=[{"type": "text", "text": "ERROR: No active edit session."}])
        result = await asyncio.to_thread(self._session.commit)
        self._session._record_trajectory("commit", result=result)
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
        tb_text: str | None = None,
        tb_clip_chars: int = 8000,
    ) -> Tuple[bool, str, int, str]:
        """Repair `rtl.sv` until the reviewer accepts it.

        `tb_text` is what the agent is shown as the oracle. The SystemVerilog
        path leaves it None and the text is read from `<run>/tb.sv`; specflow
        supplies it directly, because its testbench is a rendered cocotb suite
        plus a Python reference model and no such file exists. Reading that path
        unconditionally is what made the specflow repair loop die with
        `FileNotFoundError` on its first iteration, having never run once.
        """
        self.reset()
        tb_path = f"{output_dir_per_run}/tb.sv"
        has_tb_file = Path(tb_path).is_file()
        rtl_path = f"{output_dir_per_run}/rtl.sv"
        session_max_trials = int(max_trials) if max_trials is not None else int(self.max_trials)
        if session_max_trials < 0:
            session_max_trials = 0

        # Child module names, when this is a composition node. Empty for a leaf,
        # which is what gates the vestigial-glue rollback in
        # `_judge_replace_action_execution` off for ordinary RTL debugging.
        child_names: Tuple[str, ...] = ()
        try:
            _c = json.loads(contract_json) if contract_json else {}
            _ca = (_c.get("spec") or _c).get("child_assumes") or _c.get("child_assumes") or {}
            child_names = tuple(k for k in _ca if isinstance(k, str))
        except Exception:  # noqa: BLE001
            pass  # a contract we cannot parse simply disables the extra guard

        self._session = _EditSession(
            tb_path=tb_path if has_tb_file else None,
            rtl_path=rtl_path,
            output_dir=output_dir_per_run,
            last_mismatch_cnt=sim_mismatch_cnt,
            sim_reviewer=self.sim_reviewer,
            max_trials=session_max_trials,
            child_names=child_names,
            rollback_on_regression=self._rollback_guard,
        )

        if tb_text is not None:
            generated_tb = tb_text
        else:
            with open(tb_path, "r", encoding="utf-8") as f:
                generated_tb = f.read()

        # Save full failed log for inspection, but only send a short excerpt to the agent.
        try:
            (Path(output_dir_per_run) / "sim_failed_log.json").write_text(sim_failed_log, encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass
        sim_failed_log_excerpt = _summarize_sim_log_json(sim_failed_log)
        # The contradiction check runs on the FULL stdout, never the excerpt.
        # It is a statement about the whole population -- "these inputs appear
        # twice with different answers" -- and the excerpt keeps only the first
        # 40 value rows. Measured on the fp_adder root: the contradicting tuple
        # sits at times 1790000-1820000, i.e. in the tail the excerpt drops, so
        # reading the excerpt would have reported a clean oracle for a log that
        # provably contains a self-contradicting one.
        try:
            _full_sim_stdout = str(json.loads(sim_failed_log).get("stdout") or "")
        except Exception:  # noqa: BLE001
            _full_sim_stdout = sim_failed_log or ""

        needs_kmap_hint = any(
            k in f"{spec}\n{contract_json}".lower()
            for k in ["kmap", "k-map", "karnaugh"]
        )
        init = INIT_EDITION_PROMPT.format(
            input_spec=spec,
            contract_json=contract_json,
            generated_tb=_clip_text(generated_tb, max_chars=tb_clip_chars),
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
            if not has_tb_file:
                # The asserter copies `tb.sv` into its proof directory and wraps
                # it. With no SystemVerilog testbench there is nothing to wrap,
                # and running it would spend an agent call to fail on a read.
                raise FileNotFoundError(tb_path)
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
        # Placed BEFORE the scenario list on purpose: that list is where the
        # timing hypothesis forms, and this is its refutation. Empty unless the
        # oracle actually proves the latency correct.
        # Exactly one of these can be non-empty: the carrier either matches on
        # every sample or it does not. Clean -> "latency is proven right, stop
        # editing it"; dirty -> "fix the latency FIRST, the data mismatches are
        # ambiguous until you do".
        # Order matters. The lag check goes FIRST: when the outputs are merely
        # late, every other note would be describing values that are not
        # evidence about the logic at all. It also covers the case the carrier
        # notes cannot see -- a module with no valid/ready handshake.
        latency_note = (
            constant_output_lag_note(sim_failed_log_excerpt)
            or latency_confirmed_note(sim_failed_log_excerpt)
            or latency_carrier_mismatch_note(sim_failed_log_excerpt)
        )
        latency_block = f"{latency_note}\n" if latency_note else ""
        # Ahead of the latency note, and of everything else: if the output is a
        # verbatim copy of an input then the computed result is not reaching the
        # output at all, and no question about WHEN it arrives -- or about the
        # arithmetic that produced it -- is worth asking yet. Kept separate from
        # the latency chain rather than folded into it because the two are not
        # alternatives: a design can be both mis-routed and mis-timed, and the
        # `or` chain would report only whichever ran first.
        passthrough_note = operand_passthrough_note(sim_failed_log_excerpt)
        passthrough_block = f"{passthrough_note}\n" if passthrough_note else ""
        # Ahead of every value-based note, because it says how much they are
        # worth. A testbench that counts mismatches without recording them
        # produces a log that looks dense with evidence and carries almost
        # none; the notes below then go quiet, and quiet reads as "checked and
        # found nothing" rather than "there was nothing to check".
        evidence_note = missing_output_evidence_note(sim_failed_log_excerpt)
        evidence_block = f"{evidence_note}\n" if evidence_note else ""
        # Ahead of EVERYTHING, including the evidence note (B89). The evidence
        # note says how much the values are worth; this says whether the
        # expected column is worth anything AT ALL. An oracle that demands two
        # different outputs for one input tuple cannot be satisfied by any
        # design, so every note below it -- and every edit the debugger might
        # make -- is chasing a target that does not exist.
        contradiction_note = oracle_contradiction_note(_full_sim_stdout)
        contradiction_block = f"{contradiction_note}\n" if contradiction_note else ""
        # Same placement rationale as the latency note: the mismatch lines are
        # read before the trace report, so the correction has to arrive before
        # the thing it corrects, not after.
        # The RTL is passed so the warning can still be issued when the cycle
        # dump is too short to measure the exact skew: a clocked block is
        # sufficient to know the pairing is wrong, even when the depth is not.
        try:
            _rtl_for_skew = Path(rtl_path).read_text(encoding="utf-8")
        except Exception:  # noqa: BLE001
            _rtl_for_skew = None
        skew_note = mismatch_input_skew_note(sim_failed_log_excerpt, _rtl_for_skew)
        skew_block = f"{skew_note}\n" if skew_note else ""
        scenarios_block = (
            "<failing_scenarios>\nThese named TB scenarios are ALL failing — look for "
            "the common root cause that resolves them together. Times index wave.vcd:\n"
            + format_failing_scenarios(scenarios) + "\n</failing_scenarios>\n\n"
            if scenarios else ""
        )
        first_prompt = (
            f"{init}\n\n{contradiction_block}{evidence_block}{passthrough_block}{skew_block}{latency_block}{scenarios_block}"
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
            """Count rounds that did not improve on the best point so far.

            With the guard ON, `last_mismatch_cnt` only ever falls, so comparing
            against the previous value and against the best are the same test.
            With the guard OFF they are not: an uphill step raises
            `last_mismatch_cnt`, and comparing to the previous value would score
            every deliberate valley-crossing move as a stall -- ending the search
            after `stall_rounds` uphill steps, which is precisely the search the
            guard was turned off to allow. Measuring against the best instead
            gives the loop N rounds to find something better than anything it has
            seen, which is the question actually being asked.
            """
            nonlocal stall_count, prev_mismatch_for_stall
            best = self._session.best_mismatch_cnt
            reference = (
                min(prev_mismatch_for_stall, best) if best is not None
                else prev_mismatch_for_stall
            )
            if self._session.last_mismatch_cnt < prev_mismatch_for_stall or (
                best is not None and best < prev_mismatch_for_stall
            ):
                stall_count = 0
            else:
                stall_count += 1
            prev_mismatch_for_stall = reference

        _turn_start_iter = self._session.traj_iter + 1
        response = await self._agent(Msg("user", first_prompt, role="user"))
        _last_content = str(getattr(response, "content", "") or "")
        self._session.backfill_model_text(_turn_start_iter, _last_content)
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
            _turn_start_iter = self._session.traj_iter + 1
            response = await self._agent(
                Msg(
                    "user",
                    _render_continue_debug_prompt(self._session),
                    role="user",
                )
            )
            _last_content = str(getattr(response, "content", "") or "")
            self._session.backfill_model_text(_turn_start_iter, _last_content)
            # The reasoning, recorded against the iteration it belongs to. Without
            # it the record shows WHAT changed but never why the model thought so
            # -- and on stage_roundpack the reasoning is the whole story: it wrote
            # its (mistaken) negedge theory into a comment in the RTL.
            self._session._record_trajectory("model_turn", model_text=_last_content)
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

        # The answer is the best point the search found. With the guard on this
        # is already where the RTL sits and the call is a no-op; with it off, the
        # loop may have ended part way up a hill it was allowed to climb, and
        # returning that would make "no guard" lose by construction rather than
        # on the merits.
        if not self._session.is_done and self._session.restore_best():
            logger.info(
                "restored best-seen RTL (%s mismatches) over the loop's final state",
                self._session.best_mismatch_cnt,
            )
        with open(rtl_path, "r", encoding="utf-8") as f:
            rtl_code = f.read()
        used = int(getattr(self._session, "action_calls", 0) or 0)
        return self._session.is_done, rtl_code, used, _justification
