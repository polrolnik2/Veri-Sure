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
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

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
    #: The waveform, when one was dumped. Carried on the outcome rather than
    #: rediscovered by path convention, so a caller can hand the repair agent a
    #: real file instead of guessing where one might be.
    wave_vcd: Path | None = None

    @property
    def failing(self) -> list[str]:
        return sorted(u for u, r in self.results.items() if r.status == "FAIL")


def _ensure_importable() -> None:
    """Put this repository on `sys.path` so the simulator subprocess inherits it.

    cocotb builds the child environment as `dict(extra_env)`, copies `os.environ`
    over the top of it, then sets `env["PYTHONPATH"] = os.pathsep.join(sys.path)`
    unconditionally (`cocotb_tools/runner.py:493`, `:235-248`). A `PYTHONPATH`
    passed through `extra_env` is therefore discarded, and the parent's
    `sys.path` is the only channel that reaches the child.

    This is load-bearing because the generated `ref_model.py` does
    `from specflow.refmodel.base import RefModel`. Under pytest that resolved by
    accident -- pytest puts the rootdir on `sys.path` -- so the suite ran green
    in the test suite while failing with `ModuleNotFoundError: No module named
    'specflow'` the moment anything else drove it. That is precisely the gap
    between "tested" and "has been run", and it surfaced on the first run
    outside pytest.
    """
    root = str(Path(__file__).resolve().parents[1])
    if root not in sys.path:
        sys.path.insert(0, root)


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
    #: Dump a waveform. On by default: without it the repair agent has no
    #: temporal view of a failure at all, which is the single largest gap
    #: measured in what it actually receives.
    trace: bool = True,
    extra_sources: Sequence[Path | str] = (),
    include_dirs: Sequence[Path | str] = (),
) -> RunOutcome:
    """Elaborate and run the suite against `rtl_path`.

    `extra_sources` carries pre-made child modules the candidate instantiates
    but does not define, and `include_dirs` the headers they need. Without them
    a hierarchical DUT cannot elaborate at all, and the run reports a build
    error that looks like a defect in the generated RTL rather than a missing
    library -- which is the wrong thing to hand a repair agent.

    They are *libraries*, not part of the oracle: the reference model still has
    to derive the composed behaviour from the specification. Supplying a child
    makes a hierarchical design simulable; it does not tell the model what the
    design should do.
    """
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
    wave = suite_dir / f"wave_{iteration}.vcd"
    runner = get_runner("verilator")

    build_args = ["--coverage-line", "--coverage-toggle"] if coverage else []

    try:
        runner.build(
            sources=[str(rtl_path), *(str(p) for p in extra_sources)],
            includes=[str(p) for p in include_dirs],
            hdl_toplevel=hdl_toplevel,
            build_args=build_args,
            build_dir=str(build_dir),
            always=True,
            # Tracing is two-sided and both sides are required: `--trace` at
            # *compile* time defines VM_TRACE, and the harness then looks for
            # `--trace` in argv at *run* time before it opens a file. `waves`
            # is cocotb's switch for the first half.
            #
            # Without a waveform this backend gives the repair agent no temporal
            # view of a failure at all: `fail_time`, `fail_outputs`,
            # `input_window` and `alignment_diagnosis` were all null or zero on
            # the last run that reached the debugger.
            waves=trace,
        )
    except Exception as exc:  # noqa: BLE001
        return RunOutcome(False, {}, build_log=f"{type(exc).__name__}: {exc}")

    _ensure_importable()
    try:
        runner.test(
            test_module=list(manifest["modules"]),
            hdl_toplevel=hdl_toplevel,
            test_dir=str(suite_dir / "tests"),
            results_xml=str(suite_dir / "results.xml"),
            plusargs=[f"+verilator+coverage+file+{cov_dat.name}"],
            # The run-time half. These are argv arguments the cocotb Verilator
            # harness parses itself -- NOT plusargs, which it forwards to the
            # model and which made it exit with "Unknown runtime argument".
            test_args=[*(["--trace", "--trace-file", str(wave)] if trace else [])],
            waves=trace,
            extra_env={
                "SPECFLOW_RESULTS": str(results_dir),
                "SPECFLOW_ITER": str(iteration),
                # PYTHONPATH deliberately absent: cocotb overwrites it from the
                # parent's sys.path, which `_ensure_importable` prepares instead.
            },
        )
    except SystemExit:
        pass  # a failing suite is a verdict; the records on disk are the answer

    produced = suite_dir / "tests" / cov_dat.name
    if produced.exists():
        produced.replace(cov_dat)

    # cocotb/Verilator writes the dump relative to the test directory.
    if trace and not wave.exists():
        for candidate in (suite_dir / "tests" / wave.name, suite_dir / "tests" / "dump.vcd",
                          build_dir / wave.name, Path.cwd() / wave.name):
            if candidate.exists():
                candidate.replace(wave)
                break

    return RunOutcome(
        True,
        _read_results(results_dir),
        coverage_dat=cov_dat if cov_dat.exists() else None,
        wave_vcd=wave if trace and wave.exists() else None,
    )


def reconcile(outcome: RunOutcome, manifest: dict) -> list[str]:
    """GATE G6b: every testpoint the manifest declares must have produced a record.

    A test that crashed before `Env.finish()` leaves no JSON, and without this
    check that testpoint silently vanishes from the denominator -- making the run
    look cleaner than it was. Reported as NOT_EXERCISED rather than dropped.
    """
    return [uid for uid in manifest.get("testpoints", []) if uid not in outcome.results]
