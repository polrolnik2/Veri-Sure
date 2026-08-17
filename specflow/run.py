"""Build and run the rendered suite; collect the per-testpoint records.

No Makefiles: cocotb 2.x ships a programmatic runner, so this is ordinary Python.

Three details that are easy to get wrong and were verified rather than assumed:

* coverage flags belong in `build_args`, because `VM_COVERAGE` is a compile-time
  macro -- passing them at test time silently yields no coverage;
* the harness defaults every run to `coverage.dat`, so successive iterations
  clobber one another unless `plusargs` names the file per run;
* `runner.test()` raises when any test fails, and a failing suite is a *verdict*.
  Letting that propagate would turn "the design is wrong" into "the harness
  crashed", which is the blame-misattribution this pipeline exists to remove.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path

from .schema import TestpointResult


@dataclass(frozen=True)
class RunOutcome:
    """A build failure is its own verdict, never a testpoint failure -- that is
    the distinction the current system loses when a Verilator lowering error
    gets blamed on the RTL."""

    build_ok: bool
    results: dict[str, TestpointResult]
    build_log: str = ""
    coverage_dat: Path | None = None

    @property
    def failing(self) -> list[str]:
        return sorted(u for u, r in self.results.items() if r.status == "FAIL")


def _read_results(results_dir: Path) -> dict[str, TestpointResult]:
    out: dict[str, TestpointResult] = {}
    for path in sorted(Path(results_dir).glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        out[data["tp_uid"]] = TestpointResult(
            tp_uid=data["tp_uid"],
            status=data.get("status", "NOT_EXERCISED"),
            checks_invoked=tuple(data.get("checks_invoked") or ()),
            checks_failed=tuple(data.get("checks_failed") or ()),
            bins_hit=tuple(data.get("bins_hit") or ()),
            mismatches=tuple(data.get("mismatches") or ()),
        )
    return out


def run_suite(
    *,
    rtl_path: Path,
    hdl_toplevel: str,
    suite_dir: Path,
    refmodel_path: Path,
    iteration: int = 0,
    coverage: bool = True,
) -> RunOutcome:
    from cocotb_tools.runner import get_runner

    suite_dir = Path(suite_dir)
    manifest = json.loads((suite_dir / "manifest.json").read_text(encoding="utf-8"))
    results_dir = suite_dir / "results"
    if results_dir.exists():
        # Stale records from a previous iteration would be read as this run's
        # verdict for any testpoint that failed to run at all.
        shutil.rmtree(results_dir)
    results_dir.mkdir(parents=True)

    # The rendered modules `from ref_model import Model`, so the model must sit
    # beside them rather than being import-pathed in from elsewhere.
    staged_model = suite_dir / "tests" / "ref_model.py"
    staged_model.write_text(Path(refmodel_path).read_text(encoding="utf-8"), encoding="utf-8")

    build_dir = suite_dir / "sim_build"
    cov_dat = suite_dir / f"cov_{iteration}.dat"
    runner = get_runner("verilator")

    build_args = ["--coverage-line", "--coverage-toggle"] if coverage else []
    try:
        runner.build(
            sources=[str(rtl_path)],
            hdl_toplevel=hdl_toplevel,
            build_args=build_args,
            build_dir=str(build_dir),
            always=True,
        )
    except Exception as exc:  # noqa: BLE001
        return RunOutcome(False, {}, build_log=f"{type(exc).__name__}: {exc}")

    try:
        runner.test(
            test_module=list(manifest["modules"]),
            hdl_toplevel=hdl_toplevel,
            test_dir=str(suite_dir / "tests"),
            results_xml=str(suite_dir / "results.xml"),
            plusargs=[f"+verilator+coverage+file+{cov_dat.name}"],
            extra_env={
                "SPECFLOW_RESULTS": str(results_dir),
                "SPECFLOW_ITER": str(iteration),
                "PYTHONPATH": str(Path(__file__).resolve().parents[1]),
            },
        )
    except SystemExit:
        pass  # a failing suite is a verdict; the records on disk are the answer

    produced = suite_dir / "tests" / cov_dat.name
    if produced.exists():
        produced.replace(cov_dat)

    return RunOutcome(
        True,
        _read_results(results_dir),
        coverage_dat=cov_dat if cov_dat.exists() else None,
    )


def reconcile(outcome: RunOutcome, manifest: dict) -> list[str]:
    """GATE G6b: every testpoint the manifest declares must have produced a record.

    A test that crashed before `Env.finish()` leaves no JSON, and without this
    check that testpoint silently vanishes from the denominator -- making the run
    look cleaner than it was. Reported as NOT_EXERCISED rather than dropped.
    """
    return [uid for uid in manifest.get("testpoints", []) if uid not in outcome.results]
