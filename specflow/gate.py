"""G7: the accept decision. A pure function over three JSON inputs.

No simulator, no subprocess, no agent -- which means all four verdicts are
testable on fixtures, and that matters given `tests/` held a single file before
this work.

The three-valued per-testpoint verdict is the point. `sim_review` today returns a
bool and a mismatch count, so `is_pass=True, mismatch_cnt=0` means both
"everything was checked and passed" and "nothing ran". Bolting coverage onto that
would produce a system that reports success on unexercised spec.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .coverage import CoverageReport
from .schema import GateVerdict, TestpointResult


@dataclass
class StallTracker:
    """Terminates a loop that is no longer learning anything.

    A hard gate evaluated every iteration is the variant most likely to spin, so
    this is not optional. Modelled on `rtl_editor._update_stall_tracking`
    (`:1240-1246`, `_stall_rounds = 2`): if no bin is newly covered and no check
    newly passes for N rounds, the loop is not converging and says so rather
    than exhausting its budget in silence.
    """

    patience: int = 2
    _seen_bins: set[str] = field(default_factory=set)
    _seen_passes: set[str] = field(default_factory=set)
    _idle: int = 0

    def observe(self, report: CoverageReport, results: dict[str, TestpointResult]) -> bool:
        bins = {u for u, s in report.statuses.items() if s.hit}
        passes = {u for u, r in results.items() if r.status == "PASS"}
        progressed = bool(bins - self._seen_bins) or bool(passes - self._seen_passes)
        self._seen_bins |= bins
        self._seen_passes |= passes
        self._idle = 0 if progressed else self._idle + 1
        return self.stalled

    @property
    def stalled(self) -> bool:
        return self._idle >= self.patience


def evaluate(
    *,
    results: dict[str, TestpointResult],
    report: CoverageReport,
    missing_records: list[str] | None = None,
    build_ok: bool = True,
    build_log: str = "",
    stalled: bool = False,
) -> GateVerdict:
    """The whole accept decision, in precedence order."""
    # A build failure is its own outcome. Reporting it as a testpoint failure is
    # what sends a repair agent after RTL for a Verilator lowering error.
    if not build_ok:
        return GateVerdict("REPAIR_RTL", reason=f"build failed: {build_log[:400]}")

    failing = tuple(sorted(u for u, r in results.items() if r.status == "FAIL"))
    if failing:
        return GateVerdict("REPAIR_RTL", failing=failing,
                           reason=f"{len(failing)} testpoint(s) failing")

    # G6b: a testpoint that crashed before Env.finish() left no record. Counting
    # it as covered would make the run look cleaner than it was.
    missing = tuple(sorted(missing_records or ()))
    unexercised = tuple(
        sorted({u for u, r in results.items() if r.status == "NOT_EXERCISED"} | set(missing))
    )

    undisposed = tuple(report.undisposed)
    if undisposed or unexercised:
        if stalled:
            return GateVerdict(
                "STALLED", not_exercised=unexercised or undisposed,
                reason=f"no progress; {len(undisposed)} bin(s) still uncovered",
            )
        return GateVerdict(
            "EXTEND_TB", not_exercised=unexercised or undisposed,
            reason=f"{len(undisposed)} uncovered bin(s) without a disposition",
        )

    return GateVerdict("ACCEPT", reason=f"{len(results)} testpoint(s) passed")


def write_verdict(path: Path, verdict: GateVerdict) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(
        json.dumps(
            {
                "outcome": verdict.outcome,
                "failing": list(verdict.failing),
                "not_exercised": list(verdict.not_exercised),
                "reason": verdict.reason,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
