"""The hard-gated loop: coverage closure outer, correctness repair inner.

Nested rather than interleaved. Interleaving wastes stimulus generation on RTL
that is about to change; repairing first lets a run declare victory on spec that
was never exercised. So the loop repairs to convergence on what is currently
covered, then expands coverage, and a newly covered bin that fails re-enters
repair.

Acceptance requires zero FAIL **and** zero uncovered bin without a disposition.
G8 then converts that provisional accept into a final one.

The convergence guard is not optional. A hard gate evaluated every iteration is
the variant most likely to stall, so three mechanisms back it: formal
unreachability discharge removes bins that are impossible rather than merely
unreached, a stall detector ends a loop that is no longer learning, and the
budget is explicit and caller-supplied rather than hard-coded -- unlike
`tb_lint_max_retry`, `tb_align_max_trials` and `debug_max_trials`, none of which
can be set from any CLI today.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Protocol

from .coverage import STIMULUS_GAP, build_report, freeze_denominator
from .gate import StallTracker, evaluate, write_verdict
from .run import reconcile, run_suite
from .schema import GateVerdict


class RtlRepair(Protocol):
    """Supplied by the caller -- in production, `RTLEditor`."""

    def __call__(self, *, failing: list[str], results: dict, iteration: int) -> bool: ...


class TestcaseExtender(Protocol):
    def __call__(self, *, uncovered: list[str], report, iteration: int) -> bool: ...


@dataclass
class LoopOutcome:
    verdict: GateVerdict
    iterations: int
    history: list[str] = field(default_factory=list)

    @property
    def accepted(self) -> bool:
        return self.verdict.outcome == "ACCEPT"


def run_loop(
    *,
    rtl_path: Path,
    hdl_toplevel: str,
    suite_dir: Path,
    refmodel_path: Path,
    bins: list[dict],
    repair_rtl: RtlRepair | None = None,
    extend_tb: TestcaseExtender | None = None,
    discharge: Callable[[list[str]], dict] | None = None,
    max_iterations: int = 8,
    stall_patience: int = 2,
) -> LoopOutcome:
    suite_dir = Path(suite_dir)
    manifest = json.loads((suite_dir / "manifest.json").read_text(encoding="utf-8"))

    # Frozen once, at loop entry, and read every iteration after. The coverage
    # model may grow when a testcase is added; the denominator may not.
    denominator = freeze_denominator(bins, suite_dir / "denominator.json")

    tracker = StallTracker(patience=stall_patience)
    dispositions: dict[str, dict] = {}
    testcases: list[dict] = []
    history: list[str] = []
    verdict = GateVerdict("STALLED", reason="loop did not run")

    for iteration in range(max_iterations):
        outcome = run_suite(
            rtl_path=rtl_path, hdl_toplevel=hdl_toplevel, suite_dir=suite_dir,
            refmodel_path=refmodel_path, iteration=iteration,
        )
        report = build_report(
            denominator=denominator, results=outcome.results,
            dispositions=dispositions, testcases=testcases or None,
        )
        stalled = tracker.observe(report, outcome.results)

        verdict = evaluate(
            results=outcome.results,
            report=report,
            missing_records=reconcile(outcome, manifest),
            build_ok=outcome.build_ok,
            build_log=outcome.build_log,
            stalled=stalled,
        )
        history.append(f"iter {iteration}: {verdict.outcome} -- {verdict.reason}")
        write_verdict(suite_dir / "gate_verdict.json", verdict)

        if verdict.outcome == "ACCEPT":
            return LoopOutcome(verdict, iteration + 1, history)

        if verdict.outcome == "STALLED":
            return LoopOutcome(verdict, iteration + 1, history)

        if verdict.outcome == "REPAIR_RTL":
            if repair_rtl is None or not repair_rtl(
                failing=list(verdict.failing), results=outcome.results,
                iteration=iteration,
            ):
                history.append("repair made no change; stopping")
                return LoopOutcome(
                    GateVerdict("STALLED", failing=verdict.failing,
                                reason="RTL repair made no progress"),
                    iteration + 1, history,
                )
            continue

        # EXTEND_TB. Discharge first: a bin that is provably unreachable should
        # never be handed to a testcase agent, which would burn calls trying to
        # reach it and then report failure.
        uncovered = report.undisposed
        if discharge is not None and uncovered:
            proved = discharge(uncovered)
            if proved:
                dispositions.update(proved)
                history.append(f"discharged {sorted(proved)}")
                continue

        still = [
            u for u in uncovered
            if report.statuses[u].category in {STIMULUS_GAP, None}
            or u not in dispositions
        ]
        if extend_tb is None or not extend_tb(
            uncovered=still, report=report, iteration=iteration
        ):
            history.append("no testcase could be added; stopping")
            return LoopOutcome(
                GateVerdict("STALLED", not_exercised=tuple(still),
                            reason="uncovered bins with no way to reach them"),
                iteration + 1, history,
            )

    return LoopOutcome(
        GateVerdict("STALLED", reason=f"budget of {max_iterations} iterations exhausted"),
        max_iterations, history,
    )
