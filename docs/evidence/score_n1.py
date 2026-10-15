"""Score the re-normalized oracle set against the GOLDEN design.

The headline number this exists to produce: **how many checks convict a design
known to be correct**. c1-i2c's frozen set scores 43 of 110, and that figure is
the standing reason the RTL editor's convergence criterion -- "failing only
where golden fails" -- is currently unreachable. Everything else here is
context for it.

GOLDEN IS THE SCORER AND NOTHING UPSTREAM SAW IT. It reaches this script and no
earlier one: `downstream.py` passes `control_source=None`, and normalization,
the testplan, the stimulus and the check author all ran before this file did.

The witness stands in as `ref_model.py` because the runtime still requires one.
Its comparisons are not read -- the verdicts come from `decide_rtl` over the
RECORDED traces, which is the same path every other scoring in this project
uses, so the numbers are comparable to the ones already published.
"""
from __future__ import annotations

import argparse
import collections
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, "/home/user/Veri-Sure")

GOLDEN = Path("/home/user/Veri-Sure/benchmarks/chipverilog/Des/i2c/"
              "i2c_master_bit_ctrl/i2c_master_bit_ctrl.v")


def main() -> int:
    from specflow.refmodel.oracles import RequirementOracle
    from specflow.refmodel.rtl_trace import decide_rtl, load_traces
    from specflow.run import run_suite
    from specflow.tb.render import render_suite

    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", default="/home/user/runs/n1-i2c")
    ap.add_argument("--rtl", default=str(GOLDEN))
    ap.add_argument("--out", default="")
    ap.add_argument("--skip-sim", action="store_true",
                    help="decide over traces already recorded")
    a = ap.parse_args()

    run_dir = Path(a.run_dir)
    sf = run_dir / "specflow"
    out = Path(a.out) if a.out else run_dir / "score"
    out.mkdir(parents=True, exist_ok=True)
    rtl = Path(a.rtl)

    contract = json.loads((run_dir.parent / "c1-i2c/contract.json").read_text())
    tps = json.loads((sf / "testplan.json").read_text())["elements"]
    # Absent by design on a run that skipped S3. Empty bins and checks render
    # a suite that drives stimulus and records, which is all the oracles need.
    _cov = sf / "coverage_model.json"
    cov = json.loads(_cov.read_text()) if _cov.is_file() else {"bins": [], "checks": []}
    stim = json.loads((sf / "stimulus.json").read_text())
    by_tp = {t["tp_uid"]: t.get("steps") or [] for t in stim.get("testpoints") or []}
    art = json.loads((sf / "oracles.json").read_text())
    oracles = art.get("oracles") or []
    print(f"suite: {len(oracles)} checks over {len(tps)} testpoints", flush=True)

    suite = out / "suite"
    if not a.skip_sim:
        render_suite(testplan=tps, bins=cov.get("bins") or [],
                     checks=cov.get("checks") or [], contract=contract,
                     out_dir=suite, stimulus_by_tp=by_tp)
        shutil.copy(sf / "witness.py", out / "ref_model.py")
        shutil.copy(rtl, out / "rtl.sv")
        res = run_suite(
            rtl_path=out / "rtl.sv", hdl_toplevel="i2c_master_bit_ctrl",
            suite_dir=suite, refmodel_path=out / "ref_model.py",
            iteration=0, coverage=False, trace=False,
            # WITHOUT THESE THE BUILD FAILS AND THE RUN SCORES 0/0. Golden
            # includes `i2c_master_defines.v` from its own directory; omitting
            # them is an error I have already made once on this design.
            include_dirs=[str(rtl.parent), str(rtl.parent.parent)])
        print(f"build_ok: {res.build_ok}", flush=True)
        if not res.build_ok:
            print((res.sim_output or "")[-2000:])
            return 1

    traces = load_traces(suite / "results")
    print(f"traces recorded: {len(traces)}", flush=True)
    if not traces:
        print("NO TRACES -- nothing to decide; the numbers below would be a "
              "constant, not a measurement")
        return 1

    built = [RequirementOracle(**{k: o[k] for k in
                                  ("req_uid", "clause", "source", "tp_uids")
                                  if k in o}) for o in oracles]
    # Every check is decided against every testpoint it names; a check naming
    # none decides nothing, and `_worst([])` would return a constant False.
    for o in built:
        if not o.tp_uids:
            o.tp_uids = sorted(traces)
    verdicts = {r.req_uid: r.ok for r in decide_rtl(built, traces, contract)}

    c = collections.Counter(verdicts.values())
    n = len(verdicts)
    convicting = sorted(u for u, v in verdicts.items() if v is False)
    print()
    print(f"{'checks':<22}{n}")
    print(f"{'pass on golden':<22}{c[True]}")
    print(f"{'CONVICT golden':<22}{c[False]}   <-- c1-i2c frozen: 43 of 110")
    print(f"{'abstain':<22}{c[None]}")
    print(f"{'assertion coverage':<22}{100*(n-c[None])/max(n,1):.0f}%")
    print(f"{'pass rate':<22}{100*(n-c[False])/max(n,1):.0f}%")
    if convicting:
        print("\nconvicting golden: " + " ".join(convicting))
    json.dump({"verdicts": verdicts, "convicting": convicting,
               "counts": {str(k): v for k, v in c.items()}, "n": n},
              open(out / "score.json", "w"), indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
