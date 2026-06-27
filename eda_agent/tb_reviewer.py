"""TBReviewer — the TB-player in the consensus game.

Structural mirror of RTLEditor: same four-tool API, same session dataclass
shape, same chat() procedure. Where RTLEditor holds the testbench frozen and
edits RTL, TBReviewer holds the RTL frozen and edits the testbench.

Tool mapping
------------
RTLEditor              TBReviewer
─────────────────────  ────────────────────────────────
list_suspect_blocks()  list_suspect_sections()
read_block(id)         read_section(section_id)
replace_block(id, sv)  replace_section(section_id, sv)
_tool_run_simulation() _tool_run_simulation()

Section slicing
---------------
The trace-report suspect_blocks for RTLEditor come from the RTL structure
(always/assign blocks, correlated with failing signals via VCD). For the
testbench there is no VCD-backed structural analysis; instead, a lightweight
parser splits the TB into top-level procedural blocks (``initial``, ``always*``,
``final``) and marks as "suspect" any that reference a failing output signal.

Rollback policy
---------------
RTLEditor rolls back on mismatch regression (count worsens without fail_time
improvement). TBReviewer only rolls back on Verilator lint failure: a correct
TB fix legitimately increases the mismatch count by exposing previously hidden
failures, so regression-based rollback would prevent valid edits.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Tuple

from agentscope.memory import InMemoryMemory
from agentscope.message import Msg
from agentscope.tool import ToolResponse

from .agents import GuidingToolkit, SafeReActAgent, clear_memory_safely
from .bash_tools import CommandResult, run_bash_command
from .config import OpenAIConfig
from .model import make_formatter, make_openai_model
from .sim_reviewer import SimReviewer
from .trace_report import build_trace_report
from .utils import failing_test_scenarios, format_failing_scenarios

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# TB section slicer (TB equivalent of trace_slicer for RTL blocks)
# ---------------------------------------------------------------------------

_PROC_KW_RE = re.compile(
    r"^\s*(initial|always(?:_ff|_comb|_latch)?|final"
    r"|task(?:\s+automatic)?|function(?:\s+automatic)?(?:\s+\S+)?)\b",
    re.MULTILINE,
)

# Keep old name as alias so existing call sites outside this module still work.
_BLOCK_KW_RE = _PROC_KW_RE


@dataclass(frozen=True)
class TbSection:
    """A top-level procedural block in a testbench."""

    id: str          # e.g. "initial_0", "always_1", "task_check_outputs"
    kind: str        # "initial" | "always" | "always_ff" | "task" | "function" | ...
    start_line: int  # 1-based
    end_line: int    # 1-based, inclusive
    trigger: str     # "@(posedge clk)" etc.; empty for non-always blocks
    refs: List[str]  # identifiers referenced in this block (for suspect detection)
    code: str        # full source text of the block


def _count_depth_change(line: str) -> int:
    """Net begin-minus-end in a line (ignores strings/comments heuristically)."""
    # Strip inline // comments
    code_part = re.sub(r"//.*", "", line)
    # Strip string literals
    code_part = re.sub(r'"[^"]*"', '""', code_part)
    opens = len(re.findall(r"\bbegin\b", code_part))
    closes = len(re.findall(r"\bend\b", code_part))
    return opens - closes


def _parse_tb_sections(tb_code: str) -> list[TbSection]:
    """Parse a testbench into top-level procedural sections.

    Handles ``initial``, ``always*``, ``final``, ``task``, and ``function``
    blocks.  Task/function extent is bounded by ``endtask``/``endfunction``;
    all other blocks by ``begin``/``end`` depth tracking.  Nested blocks are
    included in the parent section's code but not emitted separately.
    Task and function sections use the declared name in their ID
    (e.g. ``task_check_outputs``) for readability.
    """
    lines = tb_code.splitlines()
    n = len(lines)
    sections: list[TbSection] = []
    counters: dict[str, int] = {}

    i = 0
    while i < n:
        m = _PROC_KW_RE.match(lines[i])
        if m is None:
            i += 1
            continue

        # First word of the match gives the primary keyword.
        first_word = m.group(1).split()[0]  # "task", "function", "initial", etc.
        start = i

        if first_word in ("task", "function"):
            kind = first_word
            base = first_word
            terminator = re.compile(r".*\bend" + first_word + r"\b")
            # Extract declared name for a readable section ID.
            name_m = re.search(
                r"\b(?:task|function)\s+(?:automatic\s+)?(?:\S+\s+)?(\w+)\s*[;(]",
                lines[i],
            )
            name = name_m.group(1) if name_m else None
            trigger = ""
            # Check if the whole task/function fits on one line.
            if terminator.match(lines[i]):
                end = i
            else:
                j = i + 1
                while j < n:
                    if terminator.match(lines[j]):
                        break
                    j += 1
                end = min(j, n - 1)
        else:
            kind = m.group(1).split()[0]  # "always_ff" etc. (first token)
            base = "initial" if kind == "initial" else ("final" if kind == "final" else "always")
            name = None
            rest = lines[i][m.end():].strip()
            trigger = ""
            tr = re.match(r"@\s*\(([^)]*)\)", rest)
            if tr:
                trigger = f"@({tr.group(1).strip()})"
            if "begin" not in lines[i]:
                end = i
            else:
                depth = _count_depth_change(lines[i])
                if depth <= 0:
                    # begin and end on the same line
                    end = i
                else:
                    j = i + 1
                    while j < n:
                        depth += _count_depth_change(lines[j])
                        if depth <= 0:
                            break
                        j += 1
                    end = min(j, n - 1)

        code = "\n".join(lines[start : end + 1])
        refs = sorted(set(re.findall(r"\b([A-Za-z_]\w*)\b", code)))

        idx = counters.get(base, 0)
        counters[base] = idx + 1
        sid = f"{base}_{name}" if name else f"{base}_{idx}"

        sections.append(
            TbSection(
                id=sid,
                kind=kind,
                start_line=start + 1,
                end_line=end + 1,
                trigger=trigger,
                refs=refs,
                code=code,
            )
        )
        i = end + 1

    return sections


def _suspect_sections(
    sections: list[TbSection], fail_signals: list[str]
) -> list[TbSection]:
    """Sections that reference at least one failing output signal."""
    if not fail_signals:
        return sections
    suspects = [
        s for s in sections
        if any(sig in s.refs for sig in fail_signals)
    ]
    return suspects if suspects else sections


# ---------------------------------------------------------------------------
# Helpers shared with RTLEditor
# ---------------------------------------------------------------------------

def _summarize_sim_log(sim_log_json: str, *, max_chars: int = 4000) -> str:
    try:
        obj = json.loads(sim_log_json)
        stdout = str(obj.get("stdout") or "")
        stderr = str(obj.get("stderr") or "")
    except Exception:  # noqa: BLE001
        stdout, stderr = sim_log_json, ""
    interesting = [
        ln for ln in stdout.splitlines()
        if any(kw in ln for kw in (
            "[TEST ", "=== MISMATCH", "Hint:", "Mismatches:", "SIMULATION FAILED",
            "SIMULATION PASSED", "TIMEOUT",
        ))
    ]
    out = "\n".join(interesting).strip() or stdout
    if stderr.strip():
        out += "\n\n[stderr]\n" + stderr.strip()
    half = max_chars // 2
    if len(out) > max_chars:
        out = out[:half] + "\n...<snip>...\n" + out[-half:]
    return out


def _lint_tb(tb_path: str) -> Tuple[bool, str]:
    """Verilator lint-only on the testbench in isolation.

    Missing-module errors are ignored (the DUT is absent when linting alone).
    Returns (is_ok, error_excerpt).
    """
    if shutil.which("verilator") is None:
        return True, ""
    cmd = (
        f"verilator --lint-only --sv --timing -Wall -Wno-fatal --assert {tb_path}"
    )
    _ok, raw = run_bash_command(cmd, timeout=60, cwd=str(Path(tb_path).parent))
    try:
        obj = CommandResult.model_validate_json(raw)
        text = f"{obj.stdout or ''}\n{obj.stderr or ''}"
    except Exception:  # noqa: BLE001
        text = raw
    error_lines = [
        ln.strip()
        for ln in text.splitlines()
        if ln.lstrip().startswith("%Error")
        and "-MODMISSING:" not in ln
        and "Exiting due to" not in ln
    ]
    is_ok = not error_lines and "syntax error" not in text.lower()
    return is_ok, "\n".join(error_lines)


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = r"""
You are TBReviewer, an expert in SystemVerilog testbench debugging.

Goal: use tool calls to minimally edit and re-simulate the testbench so that:
1) The testbench correctly encodes the Architect contract (SOURCE OF TRUTH), and
2) Either the RTL passes the corrected testbench (TB had a bug that is now fixed),
   or you confirm the testbench is already correct (RTL is the side at fault).

The RTL is FROZEN — you cannot modify it. It may be correct or incorrect.

Toolchain note:
- Simulation is run with Verilator; errors/warnings follow Verilator formatting.

Rules:
1. Do NOT modify the RTL. Only the testbench may be changed.
2. The contract is the SOURCE OF TRUTH. Fix the testbench to match the contract,
   NOT to match the RTL's observed (possibly wrong) behaviour.
3. If simulation fails but the testbench faithfully encodes the contract,
   conclude TB_CORRECT (the RTL is at fault) and call generate_response.
4. Prefer small, targeted edits. Preserve the DUT instantiation and port
   connections unless they are genuinely wrong per the contract.
5. Verilator target: keep the TB compatible (no unsupported SVA, no `continue`
   keyword, prefer simple assertions).

When done, finish by calling generate_response with a structured plain-string response in
EXACTLY this format (use literal newlines between fields):

  If you fixed the testbench:
    generate_response(response="TB_FIXED: <one-line summary of what you changed>\nCONTRACT_CLAUSE: <the specific contract requirement the original TB mis-tested>\nFIX_RATIONALE: <how the change now correctly tests that requirement>")

  If the testbench is already correct (RTL is at fault):
    generate_response(response="TB_CORRECT: <one-line summary of why TB is correct>\nCONTRACT_CLAUSE: <specific contract requirement the TB correctly tests>\nRTL_FAULT: <what the RTL is doing wrong relative to that requirement>")

The `response` argument MUST be a plain string (not JSON, not a dict).
"""

INIT_PROMPT = r"""
The information below is given to help your review:
1. The Architect contract (JSON) — SOURCE OF TRUTH for interface/timing/behaviour;
2. The failing simulation log excerpt (ground truth about mismatches);
3. The RTL (frozen; do NOT modify it — it may be correct or incorrect).
<contract_json>
{contract_json}
</contract_json>
<sim_failed_log_excerpt>
{sim_failed_log_excerpt}
</sim_failed_log_excerpt>
<frozen_rtl>
{frozen_rtl}
</frozen_rtl>
"""

EXTRA_ORDER_PROMPT = r"""
Workflow (repeat until done):
1) Consider ALL failing scenarios in <failing_scenarios> together — the testbench
   runs every named scenario and reports each independently, so do not fixate on a
   single "first" mismatch. A correct fix usually resolves a whole group of related
   scenarios at once; look for the common root cause across them.
2) Use the contract + trace report to identify which outputs are failing and why.
3) Call _tool_list_suspect_sections() to see which TB blocks reference the failing signals.
4) Call _tool_read_section(section_id) for the most relevant one.
5) Make ONE small targeted change via _tool_replace_section(section_id, new_code).
6) Call _tool_run_simulation() and iterate; track which scenarios still fail.

Rules:
- Do NOT modify the RTL.
- Change only the contract-relevant parts (expected values, stimulus timing, check logic).
- Keep the testbench Verilator-compatible.

You will receive a structured trace-grounded report (JSON) that includes:
1) earliest mismatch time, 2) (expected vs actual) values, 3) alignment diagnosis,
4) failing output signals — use these to identify which TB section to fix.

Use tools:
- _tool_list_suspect_sections()
- _tool_read_section(section_id)
- _tool_replace_section(section_id, new_code)
- _tool_run_simulation()

When simulation passes (or you confirm TB is correct), call generate_response using the
structured format from the system prompt (TB_FIXED or TB_CORRECT + CONTRACT_CLAUSE + rationale).
"""


# ---------------------------------------------------------------------------
# Session state (mirrors _EditSession in rtl_editor.py)
# ---------------------------------------------------------------------------

@dataclass
class _TBReviewSession:
    tb_path: str
    rtl_path: str
    output_dir: str
    last_mismatch_cnt: int
    sim_reviewer: SimReviewer
    max_trials: int

    is_done: bool = False
    action_calls: int = 0
    trace_report: Dict[str, Any] | None = None
    sections_by_id: Dict[str, TbSection] | None = None
    fail_signals: List[str] = field(default_factory=list)

    def read_tb(self) -> str:
        return Path(self.tb_path).read_text(encoding="utf-8")

    def read_tb_with_lineno(self) -> str:
        lines = self.read_tb().splitlines()
        return "\n".join(f"{i + 1}: {ln}" for i, ln in enumerate(lines)) + "\n"

    def write_tb(self, content: str) -> None:
        Path(self.tb_path).write_text(content, encoding="utf-8")

    def run_simulation(self) -> Dict[str, Any]:
        is_pass, mismatch_cnt, sim_output = self.sim_reviewer.review()
        self.last_mismatch_cnt = mismatch_cnt
        try:
            Path(self.output_dir, "tb_review_sim_output.json").write_text(
                sim_output, encoding="utf-8"
            )
        except Exception:  # noqa: BLE001
            pass
        return {
            "is_sim_pass": is_pass,
            "sim_mismatch_cnt": mismatch_cnt,
            "sim_output_excerpt": _summarize_sim_log(sim_output),
            "sim_output_path": str(Path(self.output_dir, "tb_review_sim_output.json")),
        }

    def list_suspect_sections(self) -> list[dict[str, Any]]:
        if self.sections_by_id is None:
            return []
        return [
            {
                "id": s.id,
                "kind": s.kind,
                "trigger": s.trigger,
                "start_line": s.start_line,
                "end_line": s.end_line,
            }
            for s in self.sections_by_id.values()
        ]

    def read_section(self, section_id: str) -> str:
        if not self.sections_by_id or section_id not in self.sections_by_id:
            return f"ERROR: Unknown section_id '{section_id}'. Use list_suspect_sections() first."
        s = self.sections_by_id[section_id]
        lines = s.code.splitlines()
        return (
            "\n".join(f"{s.start_line + i}: {ln}" for i, ln in enumerate(lines))
            + "\n"
        )

    def replace_section(self, section_id: str, new_code: str) -> Dict[str, Any]:
        if not self.sections_by_id or section_id not in self.sections_by_id:
            return {
                "is_action_executed": False,
                "error_msg": f"Unknown section_id '{section_id}'. Use list_suspect_sections() first.",
            }

        self.action_calls += 1
        if self.action_calls > self.max_trials:
            return {
                "is_action_executed": False,
                "error_msg": "Reached maximum review trials; refusing further edits.",
            }

        s = self.sections_by_id[section_id]
        old_text = self.read_tb()
        old_lines = old_text.splitlines()
        start_idx = s.start_line - 1  # 0-based
        end_idx = s.end_line - 1      # 0-based, inclusive

        if start_idx < 0 or end_idx >= len(old_lines) or start_idx > end_idx:
            return {
                "is_action_executed": False,
                "error_msg": (
                    f"Section {section_id} line range {s.start_line}–{s.end_line} "
                    f"is out of bounds (TB has {len(old_lines)} lines)."
                ),
            }

        new_lines = old_lines[:start_idx] + new_code.rstrip("\n").splitlines() + old_lines[end_idx + 1:]
        new_text = "\n".join(new_lines) + ("\n" if old_text.endswith("\n") else "")
        self.write_tb(new_text)

        # Lint check — rollback on failure
        is_ok, lint_excerpt = _lint_tb(self.tb_path)
        if not is_ok:
            self.write_tb(old_text)
            return {
                "is_action_executed": False,
                "error_msg": f"Testbench lint error — edit rolled back.\n{lint_excerpt}",
            }

        # Re-simulate and refresh sections
        sim_result = self.run_simulation()
        self._refresh_sections()

        if sim_result["is_sim_pass"]:
            self.is_done = True

        return {"is_action_executed": True, **sim_result}

    def _refresh_sections(self) -> None:
        """Re-parse TB sections and re-identify suspects after an edit."""
        try:
            all_sections = _parse_tb_sections(self.read_tb())
            suspects = _suspect_sections(all_sections, self.fail_signals)
            self.sections_by_id = {s.id: s for s in suspects}
        except Exception:  # noqa: BLE001
            pass

    def trace_summary(self) -> Dict[str, Any]:
        tr = self.trace_report or {}
        fail_outputs = tr.get("fail_outputs") or []
        alignment = tr.get("alignment_diagnosis") or {}

        alignment_compact: Dict[str, Any] = {}
        if isinstance(alignment, dict):
            for sig, info in alignment.items():
                if not isinstance(info, dict):
                    continue
                alignment_compact[str(sig)] = {
                    "best_alignment": info.get("best_alignment"),
                    "match_rate_current": info.get("match_rate_current"),
                    "match_rate_dut_lag1": info.get("match_rate_dut_lag1"),
                    "samples_considered": info.get("samples_considered"),
                }

        return {
            "fail_time": tr.get("fail_time"),
            "total_mismatches": tr.get("total_mismatches"),
            "fail_outputs": [
                {"sig": fo.get("sig"), "expected": fo.get("expected"), "actual": fo.get("actual")}
                for fo in fail_outputs
                if isinstance(fo, dict)
            ][:5],
            "alignment_diagnosis": alignment_compact,
            "failing_signals": self.fail_signals,
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _response_is_terminal(msg: Any) -> bool:
    """Return True if the agent called generate_response (TB_FIXED or TB_CORRECT)."""
    content = str(getattr(msg, "content", "") or "")
    return bool(re.search(r"\bTB_(?:FIXED|CORRECT)\b", content))


# ---------------------------------------------------------------------------
# TBReviewer agent
# ---------------------------------------------------------------------------

class TBReviewer:
    """TB-player in the consensus game — structural mirror of RTLEditor.

    Holds the RTL frozen; reviews and optionally repairs the testbench using
    the same four-tool loop (list → read → replace → simulate) that RTLEditor
    uses on the RTL side.
    """

    def __init__(
        self,
        cfg: OpenAIConfig,
        *,
        sim_reviewer: SimReviewer,
        max_trials: int = 10,
    ) -> None:
        self._cfg = cfg
        self.sim_reviewer = sim_reviewer
        self.max_trials = int(max_trials)
        self._session: _TBReviewSession | None = None

        toolkit = GuidingToolkit()
        toolkit.register_tool_function(self._tool_list_suspect_sections)
        toolkit.register_tool_function(self._tool_read_section)
        toolkit.register_tool_function(self._tool_replace_section)
        toolkit.register_tool_function(self._tool_run_simulation)

        self._agent = SafeReActAgent(
            name="TBReviewer",
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

    # ------------------------------------------------------------------
    # Tools
    # ------------------------------------------------------------------

    async def _tool_list_suspect_sections(self) -> ToolResponse:
        """List TB sections that reference failing output signals (suspect check logic)."""
        if self._session is None:
            return ToolResponse(content=[{"type": "text", "text": "ERROR: No active session."}])
        sections = self._session.list_suspect_sections()
        return ToolResponse(content=[{"type": "text", "text": json.dumps(sections, indent=2)}])

    async def _tool_read_section(self, section_id: str) -> ToolResponse:
        """Read a TB section by section_id with 1-based line numbers."""
        if self._session is None:
            return ToolResponse(content=[{"type": "text", "text": "ERROR: No active session."}])
        return ToolResponse(
            content=[{"type": "text", "text": self._session.read_section(section_id)}]
        )

    async def _tool_replace_section(self, section_id: str, new_code: str) -> ToolResponse:
        """Replace a TB section, lint-check, re-simulate (rollback on lint failure)."""
        if self._session is None:
            return ToolResponse(content=[{"type": "text", "text": "ERROR: No active session."}])
        result = await asyncio.to_thread(self._session.replace_section, section_id, new_code)
        if self._session.trace_report:
            result.setdefault("trace_summary", self._session.trace_summary())
        return ToolResponse(content=[{"type": "text", "text": json.dumps(result, indent=4)}])

    async def _tool_run_simulation(self) -> ToolResponse:
        """Run simulation of frozen RTL + current testbench; returns pass/fail and trace."""
        if self._session is None:
            return ToolResponse(content=[{"type": "text", "text": "ERROR: No active session."}])
        result = await asyncio.to_thread(self._session.run_simulation)
        # Refresh trace after standalone re-simulations
        try:
            sim_log_path = Path(self._session.output_dir) / "tb_review_sim_output.json"
            if sim_log_path.exists():
                sim_log_json = sim_log_path.read_text(encoding="utf-8")
                report, _ = build_trace_report(
                    rtl_path=Path(self._session.rtl_path),
                    sim_log_json=sim_log_json,
                    output_dir=Path(self._session.output_dir),
                )
                self._session.trace_report = report
                result["trace_summary"] = self._session.trace_summary()
        except Exception:  # noqa: BLE001
            pass
        return ToolResponse(content=[{"type": "text", "text": json.dumps(result, indent=4)}])

    # ------------------------------------------------------------------
    # Main entry point (mirrors RTLEditor.chat)
    # ------------------------------------------------------------------

    async def chat(
        self,
        *,
        contract_json: str,
        output_dir_per_run: str,
        sim_failed_log: str,
        sim_mismatch_cnt: int,
        max_trials: int | None = None,
    ) -> Tuple[bool, str, int]:
        """Review (and optionally repair) the testbench.

        Returns ``(is_sim_pass, tb_code, used_trials)``.
        ``tb_code`` is whatever ``tb.sv`` contains when the session ends.
        """
        self.reset()
        session_max = int(max_trials) if max_trials is not None else self.max_trials
        if session_max < 0:
            session_max = 0

        tb_path = str(Path(output_dir_per_run) / "tb.sv")
        rtl_path = str(Path(output_dir_per_run) / "rtl.sv")

        # Build trace report to identify failing signals
        report, _ = {}, []
        try:
            report, _ = build_trace_report(
                rtl_path=Path(rtl_path),
                sim_log_json=sim_failed_log,
                output_dir=Path(output_dir_per_run),
            )
        except Exception:  # noqa: BLE001
            pass

        fail_signals: list[str] = []
        for fo in (report.get("fail_outputs") or []):
            if isinstance(fo, dict) and isinstance(fo.get("sig"), str):
                fail_signals.append(str(fo["sig"]))
        fail_signals = sorted(set(fail_signals))

        # Parse TB and identify suspect sections
        tb_text = Path(tb_path).read_text(encoding="utf-8")
        all_sections = _parse_tb_sections(tb_text)
        suspects = _suspect_sections(all_sections, fail_signals)

        self._session = _TBReviewSession(
            tb_path=tb_path,
            rtl_path=rtl_path,
            output_dir=output_dir_per_run,
            last_mismatch_cnt=sim_mismatch_cnt,
            sim_reviewer=self.sim_reviewer,
            max_trials=session_max,
            trace_report=report if isinstance(report, dict) else None,
            sections_by_id={s.id: s for s in suspects},
            fail_signals=fail_signals,
        )

        try:
            Path(output_dir_per_run, "sim_failed_log.json").write_text(
                sim_failed_log, encoding="utf-8"
            )
        except Exception:  # noqa: BLE001
            pass

        frozen_rtl = ""
        try:
            frozen_rtl = Path(rtl_path).read_text(encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass

        sim_excerpt = _summarize_sim_log(sim_failed_log)
        init = INIT_PROMPT.format(
            contract_json=contract_json,
            sim_failed_log_excerpt=sim_excerpt,
            frozen_rtl=frozen_rtl[:6000] + ("\n...<snip>...\n" if len(frozen_rtl) > 6000 else ""),
        )

        trace_json = json.dumps(
            self._session.trace_summary() if self._session.trace_report else {},
            indent=2,
        )

        # All scenarios that failed, with timing pointers, presented as a set to
        # resolve together — not a single first-failure. Each line carries the first
        # mismatch time + the scenario's time window so the reviewer can locate it.
        scenarios = failing_test_scenarios(sim_excerpt)
        scenarios_block = (
            "<failing_scenarios>\n"
            + (
                "These named TB scenarios are ALL currently failing — review them "
                "together, not one-at-a-time. Times index wave.vcd:\n"
                + format_failing_scenarios(scenarios) + "\n"
                if scenarios
                else "(no per-scenario [TEST] markers parsed; rely on the failing "
                "signals/trace below)\n"
            )
            + "</failing_scenarios>"
        )

        first_prompt = (
            f"{init}\n\n"
            f"{scenarios_block}\n\n"
            f"<trace_report_json>\n{trace_json}\n</trace_report_json>\n\n"
            f"{EXTRA_ORDER_PROMPT}\n\n"
            "Start by calling _tool_list_suspect_sections(), then _tool_read_section(section_id) "
            "for the most relevant one, then apply one _tool_replace_section(section_id, new_code), "
            "then _tool_run_simulation()."
        )
        try:
            Path(output_dir_per_run, "tb_reviewer_prompt.txt").write_text(
                first_prompt + "\n", encoding="utf-8"
            )
        except Exception:  # noqa: BLE001
            pass

        _justification: str = ""

        response = await self._agent(Msg("user", first_prompt, role="user"))
        if _response_is_terminal(response):
            self._session.is_done = True
            _justification = str(getattr(response, "content", "") or "")

        for _ in range(session_max):
            if self._session.is_done:
                break
            response = await self._agent(
                Msg(
                    "user",
                    "Continue reviewing. If mismatches remain and a TB section is at fault, "
                    "call _tool_read_section(section_id) then "
                    "_tool_replace_section(section_id, new_code) once, then "
                    "_tool_run_simulation(). If the TB is already correct per the contract, "
                    "call generate_response using the structured format from the system prompt.",
                    role="user",
                )
            )
            if _response_is_terminal(response) and not _justification:
                self._session.is_done = True
                _justification = str(getattr(response, "content", "") or "")

        tb_code = Path(tb_path).read_text(encoding="utf-8")
        used = int(getattr(self._session, "action_calls", 0))
        return self._session.is_done, tb_code, used, _justification
