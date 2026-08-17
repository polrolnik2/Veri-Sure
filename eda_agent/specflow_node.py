"""Node execution on the specflow backend.

Written as its own path rather than threaded through `_run_instance`'s
SystemVerilog-shaped control flow. That flow is organised around a single
monolithic `tb.sv` -- three mutually exclusive generation branches, a lint-repair
loop, a mock-DUT alignment pass and a log-marker verdict -- and none of those
steps has a counterpart here. Interleaving would have produced a function whose
branches were half dead on either backend.

Kept from the original path: the contract, `RTLGenerator`, and `RTLEditor` for
repair. Replaced: the oracle, the verdict, and the failure payload the repair
agent receives.

`RTLEditor` needs no changes at all, because it is already parameterised on a
reviewer object. `SpecflowReviewer` below has the same three-value shape as
`SimReviewer.review()`, so the editor's `run_simulation` tool keeps working while
the oracle underneath it becomes the cocotb suite and the Python reference model.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Tuple

from .config import OpenAIConfig
from .rtl_editor import RTLEditor
from .rtl_generator import RTLGenerator
from .sim_reviewer import check_syntax

logger = logging.getLogger(__name__)


def format_failures(payload: list[dict], *, limit: int = 40) -> str:
    """Turn per-testpoint records into the repair agent's prompt payload.

    Deliberately not a log excerpt. `rtl_editor` receives a keyword-filtered
    slice of simulator stdout today, and the recorded failure of that approach
    was 210 MISMATCH lines carrying two actual values. Here every line already
    names the check, both values, and the stimulus that produced them -- and
    every failing testpoint is present, not only the first one hit.
    """
    if not payload:
        return ""

    lines: list[str] = []
    shown = 0
    for entry in payload:
        checks = ", ".join(entry.get("failed_checks") or [])
        lines.append(f"[{entry['testpoint']}] FAIL -- checks {checks}")
        for m in entry.get("mismatches") or []:
            if shown >= limit:
                lines.append("  ... further mismatches omitted")
                break
            ctx = ", ".join(f"{k}={v}" for k, v in (m.get("ctx") or {}).items())
            lines.append(
                f"  {m.get('check')}: expected={m.get('expected')} got={m.get('got')}"
                + (f" on {ctx}" if ctx else "")
            )
            shown += 1
    return "\n".join(lines)


class SpecflowReviewer:
    """`SimReviewer`-shaped adapter over the specflow verdict.

    Returns `(is_pass, mismatch_cnt, sim_output)` so `RTLEditor` is unchanged.
    `mismatch_cnt` is the count of *failing testpoints*, which is what the
    editor's rollback judgement compares round to round -- a count that falls as
    repairs land, exactly as the mismatch count did.
    """

    def __init__(self, *, built, hdl_toplevel: str, output_dir: Path):
        self._built = built
        self._top = hdl_toplevel
        self._dir = Path(output_dir)
        self._iteration = 0
        self.golden_rtl_path = None  # rtl_editor getattrs this

    def review(self) -> Tuple[bool, int, str]:
        from specflow.integration import failure_payload, judge

        verdict, info = judge(
            rtl_path=self._dir / "rtl.sv",
            hdl_toplevel=self._top,
            suite_dir=self._built.suite_dir,
            refmodel_path=self._built.refmodel_path,
            bins=self._built.bins,
            iteration=self._iteration,
        )
        self._iteration += 1

        payload = failure_payload(self._built.suite_dir)
        stdout = format_failures(payload) or verdict.reason

        # A build failure is reported as such rather than as failing testpoints,
        # so the editor is not sent after RTL logic for a lowering error.
        sim_output = json.dumps(
            {
                "stdout": stdout,
                "stderr": "" if info.get("build_ok") else verdict.reason,
                "verdict": verdict.outcome,
                "testpoints": info.get("results", {}),
                "uncovered": info.get("uncovered", []),
            },
            indent=2,
        )
        return verdict.outcome == "ACCEPT", len(verdict.failing), sim_output


async def run_specflow_node(
    *,
    cfg: OpenAIConfig,
    spec: str,
    contract_json: str,
    output_dir_per_run: Path,
    rtl_gen: RTLGenerator,
    sim_max_retry: int = 4,
    debug_max_trials: int = 30,
    model_port: str = "replay",
    max_repairs: int = 3,
) -> Tuple[bool, str, dict[str, Any]]:
    """Build the oracle, generate RTL, repair until the gate accepts.

    Returns `(accepted, rtl_code, detail)`.
    """
    from specflow.integration import build_artifacts

    output_dir_per_run = Path(output_dir_per_run)
    detail: dict[str, Any] = {"backend": "specflow", "history": []}

    # The oracle is built first and must be certified before any RTL exists.
    # Generating RTL against an uncertified oracle would be repairing toward a
    # standard nothing verified -- and it is also what keeps the reference model
    # independent, since there is no rtl.sv in existence while it is written.
    built = build_artifacts(
        run_dir=output_dir_per_run,
        spec=spec,
        contract_json=contract_json,
        model_port=model_port,
        max_repairs=max_repairs,
    )
    detail["artifacts"] = {"ok": built.ok, "stage": built.stage, "reason": built.reason}
    if not built.ok:
        logger.error("specflow artifacts failed at %s: %s", built.stage, built.reason)
        return False, "", detail

    contract = json.loads(contract_json) if contract_json.strip() else {}
    top = str(contract.get("module_name") or "TopModule")
    rtl_path = output_dir_per_run / "rtl.sv"

    ok, rtl_code = await rtl_gen.chat(
        input_spec=spec,
        testbench="",  # the suite is not a prompt input on this backend
        interface="",
        rtl_path=str(rtl_path),
        contract_json=contract_json,
    )
    if not ok or not rtl_code.strip():
        detail["history"].append("RTL generation produced nothing")
        return False, rtl_code, detail

    rtl_path.write_text(rtl_code, encoding="utf-8")
    syntax_ok, syntax_log = check_syntax(str(rtl_path))
    if not syntax_ok:
        detail["syntax"] = syntax_log
        detail["history"].append("RTL failed syntax check")
        return False, rtl_code, detail

    reviewer = SpecflowReviewer(
        built=built, hdl_toplevel=top, output_dir=output_dir_per_run
    )
    remaining = int(debug_max_trials)

    for iteration in range(max(1, sim_max_retry)):
        is_pass, failing, sim_output = reviewer.review()
        verdict = json.loads(sim_output)["verdict"]
        detail["history"].append(f"iter {iteration}: {verdict} ({failing} failing)")
        detail["verdict"] = verdict

        if is_pass:
            return True, rtl_path.read_text(encoding="utf-8"), detail

        if verdict != "REPAIR_RTL":
            # EXTEND_TB and STALLED are not RTL problems, and reporting them as
            # one is what sends a repair agent after the wrong artifact.
            return False, rtl_path.read_text(encoding="utf-8"), detail

        if remaining <= 0:
            detail["history"].append("debug budget exhausted")
            return False, rtl_path.read_text(encoding="utf-8"), detail

        editor = RTLEditor(cfg, sim_reviewer=reviewer, max_trials=remaining)
        _, repaired, used, _ = await editor.chat(
            spec=spec,
            output_dir_per_run=str(output_dir_per_run),
            sim_failed_log=sim_output,
            sim_mismatch_cnt=failing,
            contract_json=contract_json,
            max_trials=remaining,
        )
        remaining -= max(1, int(used))
        if repaired.strip():
            rtl_path.write_text(repaired, encoding="utf-8")
        else:
            detail["history"].append("repair produced no change")
            return False, rtl_path.read_text(encoding="utf-8"), detail

    return False, rtl_path.read_text(encoding="utf-8"), detail
