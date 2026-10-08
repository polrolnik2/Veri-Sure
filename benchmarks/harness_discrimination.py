#!/usr/bin/env python3
"""Does the harness FAIL a design that is obviously wrong? No model calls.

`harness_liveness.py` asks whether the testbench reaches a design at all. This
asks the next question, and it is the one that separates agreement from vacuity:
given a reference model that is deliberately, trivially wrong -- it declares
every output zero, forever -- does the suite report FAIL?

A design that PASSES against an all-zeros oracle was not verified. That is not
hypothetical either. The `clock_named_clock` conformance fixture passed while
proving nothing: `runtime.py` looked the clock up as `getattr(dut, "clk")`,
found nothing on a port named `clock`, and `Env.start` only calls `reset()` when
it finds a clock -- so the reset was never driven, read 0, the DUT sat held in
reset at zero, and `_bundle` read that same reset back off the DUT so the model
reset too. Both sides returned 0 all run and agreed for the wrong reason.
Requiring the harness to REJECT a known-bad model is the only thing that caught
it, and this runs that requirement across all 64 designs.

Unlike the liveness probe, this drives the real `specflow.tb.runtime.Env`: the
declared idle values, the reset sequence, the per-edge lockstep advance, the
recorded trace and the sequence comparison. It is the benchmark-wide exercise of
that path.

Two ways a PASS here is honest rather than a defect, and both are reported
rather than hidden:

* the design really is all-zeros over the stimulus (a decoder whose enable is
  never asserted, an output that only moves on a bus transaction), in which case
  the liveness probe says its outputs never moved either;
* the design has no outputs, or does not elaborate.

So the number to read is: designs the liveness probe found LIVE, that the
harness nonetheless passes against a null oracle. That set should be empty.

Run: python -m benchmarks.harness_discrimination [--task NAME] [--jobs N]
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import traceback
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

DES = REPO / "benchmarks" / "chipverilog" / "Des"

from benchmarks.harness_liveness import contract_from_rtl  # noqa: E402
from benchmarks.run_chipverilog import child_sources, submodules  # noqa: E402
from specflow.tb.render import render_suite  # noqa: E402

#: A reference model that is wrong on purpose, in the most obvious way there is.
_NULL_MODEL = '''"""A deliberately wrong reference model: every output is zero, always."""

from specflow.refmodel.base import RefModel


class Model(RefModel):
    OUTPUT_PORTS = {outs!r}

    def reset(self):
        pass

    def step(self, inputs):
        return {{p: 0 for p in self.OUTPUT_PORTS}}
'''


def _plan(outs: list[str]) -> tuple[list[dict], list[dict], list[dict]]:
    """One testpoint, one bin, one check covering every declared output."""
    tp = [{"uid": "TP-0000", "dimension": "D0_liveness",
           "stimulus": "sweep the functional inputs",
           "expected_response": "the design's own outputs"}]
    bins = [{"uid": "BIN-0000", "covers": ["TP-0000"]}]
    checks = [{"uid": "CHK-0000", "covers": ["TP-0000"], "signals": outs}]
    return tp, bins, checks


def probe(task_dir: Path, work: Path, *, hold: int = 8, vectors: int = 12) -> dict:
    from specflow.run import run_suite

    name = task_dir.name
    rtl = task_dir / f"{name}.v"
    contract = contract_from_rtl(rtl)
    if contract is None:
        return {"task": name, "status": "no_ports"}
    outs = [p["name"] for p in contract["io"] if p["dir"] == "output"]
    if not outs:
        return {"task": name, "status": "no_outputs"}

    suite = work / "suite"
    if suite.exists():
        shutil.rmtree(suite)
    tp, bins, checks = _plan(outs)
    from specflow.tb.render import default_stimulus

    # An explicit hold, because the default of one edge per vector is 12 edges
    # for the whole testpoint -- less than one command on any prescaled design,
    # and a comparison over 12 edges is a much easier question than the suite
    # actually asks.
    steps = [{"inputs": v, "hold": hold} for v in default_stimulus(contract)[:vectors]]
    render_suite(testplan=tp, bins=bins, checks=checks, contract=contract,
                 out_dir=suite, stimulus_by_tp={"TP-0000": steps})

    model = work / "ref_model.py"
    model.write_text(_NULL_MODEL.format(outs=outs), encoding="utf-8")

    # The children a hierarchical reference instantiates but does not define.
    # Supplied to the simulator as libraries, exactly as `run_chipverilog.py`
    # supplies them -- 26 of the 64 references do not elaborate without them,
    # and a build failure there is about the invocation, not the harness.
    kids = child_sources(submodules(task_dir, name))
    inc = sorted({str(task_dir), str(task_dir.parent)} | {str(k.parent) for k in kids})
    try:
        out = run_suite(
            rtl_path=rtl, hdl_toplevel=contract["module_name"], suite_dir=suite,
            refmodel_path=model, iteration=0, coverage=False, trace=False,
            extra_sources=kids, include_dirs=inc,
        )
    except Exception as exc:  # noqa: BLE001
        return {"task": name, "status": "error", "reason": f"{type(exc).__name__}: {exc}"[:200]}
    if not out.build_ok:
        return {"task": name, "status": "build_fail", **_why(rtl, kids, inc)}

    records = sorted((suite / "results").glob("*.json"))
    if not records:
        return {"task": name, "status": "no_record"}
    record = json.loads(records[0].read_text(encoding="utf-8"))
    status = record.get("status")
    return {
        "task": name,
        "status": "rejected" if status == "FAIL" else "PASSED_A_NULL_ORACLE",
        "verdict": status,
        "signals_failed": record.get("signals_failed") or [],
        "outputs": len(outs),
    }


_ERROR = re.compile(r"%Error(?:-(\w+))?:\s*(.*)")


def _why(rtl: Path, kids: list[Path], inc: list[str]) -> dict:
    """Verilator's own reason, not the g++ tail.

    `run_suite` reports a build failure as the runner's `CalledProcessError`,
    whose text is the link command -- so "build_fail" said nothing about WHY,
    and 20 of 64 failures were indistinguishable. They are not the same thing:
    a module the benchmark references but never defines is a property of the
    corpus, while a design Verilator refuses on strictness is a porting cost.
    """
    cmd = ["verilator", "--lint-only", "--no-timing", "-Wno-fatal",
           *(f"-I{d}" for d in inc), str(rtl), *(str(k) for k in kids)]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)  # noqa: S603
    codes, first = [], ""
    for line in (proc.stderr or "").splitlines():
        m = _ERROR.match(line.strip())
        if m:
            codes.append(m.group(1) or "ERROR")
            first = first or m.group(2)[:120]
    return {"cause": codes[0] if codes else "UNKNOWN", "reason": first}


def _one(args: tuple[str, str]) -> dict:
    task, work = args
    try:
        return probe(Path(task), Path(work))
    except Exception:  # noqa: BLE001
        return {"task": Path(task).name, "status": "error",
                "reason": traceback.format_exc()[-300:]}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--task")
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--work", type=Path, default=Path("harness_discrimination"))
    ap.add_argument("--json", type=Path)
    ap.add_argument("--liveness", type=Path,
                    help="a harness_liveness.py result file, to separate an honest "
                         "PASS on a genuinely quiet design from a vacuous one")
    args = ap.parse_args(argv)

    tasks = [p.parent for p in sorted(DES.glob("*/*/description.txt"))]
    if args.task:
        tasks = [t for t in tasks if t.name == args.task]
    args.work.mkdir(parents=True, exist_ok=True)

    rows: list[dict] = []
    jobs = [(str(t), str(args.work / t.name)) for t in tasks]
    with ProcessPoolExecutor(max_workers=max(1, args.jobs)) as pool:
        futures = {pool.submit(_one, j): j for j in jobs}
        for fut in as_completed(futures):
            row = fut.result()
            rows.append(row)
            print(f"  {row['task']:<28} {row['status']}"
                  + (f"  ({row.get('reason', '')[:70]})" if row.get("reason") else ""))

    by_status: dict[str, int] = {}
    for row in rows:
        by_status[row["status"]] = by_status.get(row["status"], 0) + 1
    print(f"\n{len(rows)} tasks: {by_status}")

    causes: dict[str, list[str]] = {}
    for row in rows:
        if row["status"] == "build_fail":
            causes.setdefault(row.get("cause", "UNKNOWN"), []).append(row["task"])
    for cause, tasks in sorted(causes.items()):
        print(f"  build_fail/{cause}: {len(tasks)} -- {', '.join(sorted(tasks))}")

    passed = [r for r in rows if r["status"] == "PASSED_A_NULL_ORACLE"]
    if args.liveness and args.liveness.exists():
        live = {r["task"] for r in json.loads(args.liveness.read_text(encoding="utf-8"))
                if r.get("status") == "live"}
        vacuous = [r for r in passed if r["task"] in live]
        quiet = [r for r in passed if r["task"] not in live]
        print(f"\npassed a null oracle: {len(passed)}"
              f"  -- {len(quiet)} whose outputs never moved (honest),"
              f" {len(vacuous)} LIVE and still passed (a harness defect)")
        for r in vacuous:
            print(f"  !! {r['task']}")
    elif passed:
        print(f"\npassed a null oracle: {[r['task'] for r in passed]}")
        print("  (pass --liveness to separate a genuinely quiet design from a vacuous one)")

    if args.json:
        args.json.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
