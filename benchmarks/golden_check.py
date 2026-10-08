"""Score a reference model against known-good RTL. A measuring instrument.

**Never a gate, and its cycle-exact verdict never reaches an agent.** This
exists because the oracle had never been measured against RTL that is known to
be correct, and the first time it was, the golden `i2c_master_bit_ctrl` failed
120 of 168 testpoints -- worse than the LLM-written candidate it was supposed to
judge. A known-correct design scoring below a generated one means the oracle is
the broken part, and the repair loop had been deforming correct RTL to match it.

Two numbers, and the second is the one that matters:

* the **pass rate** of a correct design says how much of the harness is defect.
  A perfect oracle should score 100%; anything less is ours to fix.
* the **separation** between a correct design and a wrong one says whether the
  criterion discriminates at all. A criterion that passes everything scores well
  on the first number and is worthless. Read both, never one.

`--compare cycle_exact` re-runs the same suite demanding equality at every
cycle. The gap between the two is how much of a disagreement is phasing rather
than behaviour -- which is a question about the harness, asked here, and not a
signal to hand a repair agent. Telling one its failure is "phasing only"
understates the benchmark's sequential-equivalence scoring, where a single
surplus hold cycle is a function failure.

Usage:

    python -m benchmarks.golden_check --run <run-dir> --model <ref_model.py> \\
        --dut golden=<golden.v> --dut candidate=<rtl.sv> \\
        --top i2c_master_bit_ctrl --include <dir> --hold 60
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import shutil
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from specflow.run import run_suite  # noqa: E402
from specflow.tb.render import render_suite  # noqa: E402


def _stimulus_from(suite_dir: Path, hold: int) -> dict[str, list[dict]]:
    """The stimulus a previous run generated, so two scorings are comparable.

    `hold` re-expresses each bare vector as an explicit duration. A stimulus
    written before a step could state its own duration holds for ONE edge, which
    is 3 edges per testpoint against the 26 golden needs for a single START at
    `clk_cnt=4` -- so a score taken at the default reach is answering a much
    easier question, and the reach has to be reported with it.
    """
    out: dict[str, list[dict]] = {}
    for path in sorted((suite_dir / "tests").glob("test_TP*.py")):
        for node in ast.parse(path.read_text(encoding="utf-8")).body:
            if not isinstance(node, ast.Assign) or not node.targets:
                continue
            if getattr(node.targets[0], "id", "") != "STIMULUS":
                continue
            steps = ast.literal_eval(node.value)
            if hold > 1:
                steps = [{"inputs": v, "hold": hold} for v in steps]
            out[path.stem.replace("test_TP", "TP-")] = steps
    return out


def _score(label: str, rtl: Path, suite_src: Path, out: Path, *,
           top: str, model: Path, include: list[str]) -> dict:
    run = out / label
    if run.exists():
        shutil.rmtree(run)
    shutil.copytree(suite_src, run / "suite")
    shutil.copy(model, run / "ref_model.py")
    result = run_suite(
        rtl_path=rtl, hdl_toplevel=top, suite_dir=run / "suite",
        refmodel_path=run / "ref_model.py", iteration=99,
        coverage=False, trace=False, include_dirs=include,
    )
    if not result.build_ok:
        # A BUILD FAILURE IS NOT A SCORE OF ZERO, and returning one makes it
        # read as a measurement. `0/0` has already been mistaken for an
        # instrument verdict once and retracted; it happened again here when
        # the golden i2c RTL failed to elaborate because `i2c_master_defines.v`
        # sits in the parent directory and only the module directory was on
        # `--include`. Both models then "scored" 0/0 with an identical empty
        # divergence histogram, which is precisely what a real zero-separation
        # result would look like.
        print(f"{label}: BUILD FAILED\n{result.build_log[-3000:]}")
        return {"label": label, "passed": 0, "total": 0, "by_signal": {},
                "build_failed": True}

    return {"label": label, **_tally(run / "suite" / "results")}


def _tally(results_dir: Path) -> dict:
    """`{passed, total, by_signal, sole}` from a rendered suite's results.

    `{tp}.trace.json` shares this directory and is a different artifact --
    the recording the oracles decide over, with no `status` in it (see
    `specflow/run.py:_read_results`, which guards the identical glob for the
    identical reason). Once tracing became unconditional a bare `*.json` glob
    gives every testpoint a second, statusless record that can never read
    PASS, which silently doubles `total` and halves every reported rate.
    Measured live on or1200_ctrl: 8/62 reported before this guard existed,
    8/31 the real count -- confirmed by counting the `results/*.json` files
    that are not `*.trace.json` by hand.
    """
    passed = total = 0
    by_signal: Counter = Counter()
    sole: Counter = Counter()
    for path in sorted(Path(results_dir).glob("*.json")):
        if path.name.endswith(".trace.json"):
            continue
        record = json.loads(path.read_text(encoding="utf-8"))
        total += 1
        if record.get("status") == "PASS":
            passed += 1
            continue
        failed = set(record.get("signals_failed") or [])
        for name in failed:
            by_signal[name] += 1
        if len(failed) == 1:
            # A testpoint failing on ONE output and nothing else. The `dout`
            # asymmetry -- golden leaves it unreset, so it samples the idle bus
            # while a model that resets it reads 0 -- shows up here as a single
            # dominant name, and it is what made the harness score a wrong
            # design ABOVE golden before the idle values were declared.
            sole[next(iter(failed))] += 1
    return {"passed": passed, "total": total,
            "by_signal": dict(by_signal.most_common()), "sole": dict(sole.most_common())}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run", required=True, type=Path,
                    help="a completed run dir: contract.json + specflow/")
    ap.add_argument("--model", required=True, type=Path,
                    help="the reference model to score (e.g. a golden transliteration)")
    ap.add_argument("--dut", action="append", required=True, metavar="LABEL=PATH",
                    help="repeat: at least one known-good and one known-wrong DUT")
    ap.add_argument("--top", required=True)
    ap.add_argument("--include", action="append", default=[])
    ap.add_argument("--out", type=Path, default=Path("golden_check"))
    ap.add_argument("--hold", type=int, default=1,
                    help="edges to hold each stimulus vector; report it with the score")
    ap.add_argument("--compare", choices=("transactional", "cycle_exact"),
                    default="transactional")
    ap.add_argument("--idle-high", action="append", default=[],
                    help="input whose idle value is 1 (an open-drain bus line)")
    args = ap.parse_args(argv)

    contract = json.loads((args.run / "contract.json").read_text(encoding="utf-8"))
    for port in contract.get("io") or []:
        if port.get("name") in set(args.idle_high):
            port["idle_value"] = 1

    src = args.run / "specflow"
    testplan = json.loads((src / "testplan.json").read_text(encoding="utf-8"))
    testplan = testplan.get("elements") or testplan.get("testplan") or testplan
    cov = json.loads((src / "coverage_model.json").read_text(encoding="utf-8"))

    args.out.mkdir(parents=True, exist_ok=True)
    suite_src = args.out / "rendered"
    if suite_src.exists():
        shutil.rmtree(suite_src)
    manifest = render_suite(
        testplan=testplan, bins=cov.get("bins") or [], checks=cov.get("checks") or [],
        contract=contract, out_dir=suite_src,
        stimulus_by_tp=_stimulus_from(src / "suite", args.hold),
    )
    print(f"rendered {len(manifest.modules)} testpoints, "
          f"{len(set(manifest.checks))} checks, hold={args.hold}, "
          f"compare={args.compare}")

    os.environ["SPECFLOW_COMPARE"] = args.compare
    rows = []
    for spec in args.dut:
        label, _, path = spec.partition("=")
        rows.append(_score(label, Path(path), suite_src, args.out,
                           top=args.top, model=args.model, include=args.include))

    print()
    for row in rows:
        if row.get("build_failed"):
            # Loud, and NOT a number: nothing was measured, so nothing that
            # looks like a measurement may be printed beside it.
            print(f"{row['label']:>12}: NOT MEASURED -- the DUT did not build. "
                  f"This is a usage or environment fault, not a score. Check "
                  f"that every `include file is on --include.")
            continue
        print(f"{row['label']:>12}: {row['passed']}/{row['total']}"
              f"   diverging outputs {row['by_signal']}")
    if len(rows) >= 2:
        best, worst = rows[0], rows[-1]
        gap = best["passed"] - worst["passed"]
        print(f"\nseparation ({best['label']} - {worst['label']}): {gap}")
        if gap <= 0:
            # Read this as an indictment of the instrument before the model.
            # `or1200_gmultp2_32x32` scored 36/36 against golden AND 36/36
            # against its mutant, which is the exact signature of a vacuous
            # oracle -- and the oracle was correct. `mutate.py` had picked a
            # site inside `input [`OR1200_W-1:0] X`, which only widens the port;
            # the harness drives the 32-bit contract port and `xi` is an
            # `integer`, so the "wrong" DUT was byte-for-byte golden's
            # behaviour. A correct model is OBLIGED to pass both.
            print(f"  !! separation {gap} does not mean the model is vacuous, "
                  f"and this number is not yet interpretable.")
            print(f"  !! First show that {worst['label']} differs from "
                  f"{best['label']} at all: an equivalent mutant makes every "
                  f"model score identically on both, however good or bad.")
        # No silent caps: name what a per-signal exclusion would be worth, so
        # the headline number is never read as if one output were not dominating.
        for row in rows:
            for name, count in (row.get("sole") or {}).items():
                if count >= 5:
                    print(f"  {row['label']}: {count} testpoints diverge on "
                          f"{name} ALONE -> {row['passed'] + count}/{row['total']} "
                          f"without it")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
