#!/usr/bin/env python3
"""Where does a reference model start disagreeing with the RTL, and why. Debug only.

`golden_check.py` says a model scores 113/168. It does not say why any one of
the 55 failed, and the failure it reports is the wrong place to look: both bugs
in the hand-written control oracle were "read a value from the wrong clock
generation", and neither showed up at the edge where it happened. Each surfaced
many edges later, in a different signal, after the model had fallen a whole
command behind the DUT.

What found them was comparing the two sides' INTERNALS edge by edge against the
Verilog. This runs that comparison as an instrument instead of by hand:

    python -m benchmarks.divergence_trace --run <run-dir> --model <ref_model.py> \\
        --dut <golden.v> --top i2c_master_bit_ctrl --tp TP-0035 \\
        --internal cnt,clk_en,sSCL,sSDA,dSCL,dSDA,sta_condition --hold 60

It prints one row per clock edge -- the driven inputs, both sides' outputs, and
both sides' internals -- and marks the first edge on which any named signal
disagrees. Naming the right internals is the analyst's job; they are read off
the DUT by `getattr` and off the model by attribute of the same name, so a
signal the model calls something else needs `dut_name=model_name`.

**Never a gate, and never shown to an agent.** It reads a model's private state,
which is not a contract; a repair agent told "your `sta_condition` is early"
would be acting on an implementation detail of the oracle rather than on the
requirement it failed.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from benchmarks.golden_check import _stimulus_from  # noqa: E402
from specflow.run import run_suite  # noqa: E402
from specflow.tb.render import render_suite  # noqa: E402


def _fmt(value: object) -> str:
    return "-" if value is None else str(value)


def _row(names: list[str], dut: dict, model: dict) -> str:
    cells = []
    for n in names:
        d, m = dut.get(n), model.get(n)
        mark = " " if d == m else "!"
        cells.append(f"{n}={_fmt(d)}/{_fmt(m)}{mark}")
    return " ".join(cells)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run", required=True, type=Path)
    ap.add_argument("--model", required=True, type=Path)
    ap.add_argument("--dut", required=True, type=Path)
    ap.add_argument("--top", required=True)
    ap.add_argument("--tp", required=True, help="one testpoint uid, e.g. TP-0035")
    ap.add_argument("--internal", default="",
                    help="comma-separated; `dut_name=model_name` when they differ")
    ap.add_argument("--include", action="append", default=[])
    ap.add_argument("--hold", type=int, default=1)
    ap.add_argument("--out", type=Path, default=Path("divergence_trace"))
    ap.add_argument("--edges", type=int, default=200, help="rows to print")
    ap.add_argument("--from-edge", type=int, default=0)
    ap.add_argument("--idle-high", action="append", default=[])
    args = ap.parse_args(argv)

    contract = json.loads((args.run / "contract.json").read_text(encoding="utf-8"))
    for port in contract.get("io") or []:
        if port.get("name") in set(args.idle_high):
            port["idle_value"] = 1

    src = args.run / "specflow"
    testplan = json.loads((src / "testplan.json").read_text(encoding="utf-8"))
    testplan = testplan.get("elements") or testplan.get("testplan") or testplan
    cov = json.loads((src / "coverage_model.json").read_text(encoding="utf-8"))
    # One testpoint: the point is a readable trace, and rendering the whole
    # suite would run 167 others to print one.
    testplan = [t for t in testplan if (t.get("uid") or t.get("tp_uid")) == args.tp]
    if not testplan:
        raise SystemExit(f"{args.tp} is not in {src / 'testplan.json'}")

    work = args.out
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    render_suite(
        testplan=testplan, bins=cov.get("bins") or [], checks=cov.get("checks") or [],
        contract=contract, out_dir=work / "suite",
        stimulus_by_tp=_stimulus_from(src / "suite", args.hold),
    )
    shutil.copy(args.model, work / "ref_model.py")

    names = [n.strip() for n in args.internal.split(",") if n.strip()]
    dut_names = [n.split("=")[0] for n in names]
    os.environ["SPECFLOW_TRACE_INTERNALS"] = ",".join(dut_names)
    result = run_suite(
        rtl_path=args.dut, hdl_toplevel=args.top, suite_dir=work / "suite",
        refmodel_path=work / "ref_model.py", iteration=99,
        coverage=False, trace=False, include_dirs=args.include,
    )
    if not result.build_ok:
        print(f"BUILD FAILED\n{result.build_log[-3000:]}")
        return 1

    dump = work / "suite" / "results" / f"{args.tp}.trace.json"
    if not dump.exists():
        print(f"no trace written at {dump}; the testpoint did not reach finish()")
        return 1
    data = json.loads(dump.read_text(encoding="utf-8"))
    outputs, edges = data["outputs"], data["edges"]

    print(f"{args.tp}: {len(edges)} edges, hold={args.hold}")
    print(f"outputs {outputs}   internals {dut_names}")
    print("dut/model, ! marks a disagreement\n")

    first = None
    shown = 0
    for row in edges:
        disagrees = (
            any(row["dut"].get(n) != row["model"].get(n) for n in outputs)
            or any(row["dut_internal"].get(n) != row["model_internal"].get(n)
                   for n in dut_names)
        )
        if disagrees and first is None:
            first = row["edge"]
        if row["edge"] < args.from_edge or shown >= args.edges:
            continue
        shown += 1
        mark = "<<<" if row["edge"] == first else "   "
        print(f"e{row['edge']:<5} step{row['step']:<3} {mark} "
              f"{_row(outputs, row['dut'], row['model'])}  |  "
              f"{_row(dut_names, row['dut_internal'], row['model_internal'])}")

    print()
    if first is None:
        print("no disagreement on any named signal over the whole trace")
    else:
        print(f"first disagreement at edge {first} "
              f"(inputs {edges[first]['inputs']})")
    print(f"full trace: {dump}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
