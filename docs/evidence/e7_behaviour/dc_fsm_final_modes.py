"""dc_fsm_final_modes.py -- which error modes the dc_fsm luna14 designs still carry, and how much of each.

The qualitative analysis's replica model (qualitative/or1200_dc_fsm/model.py: golden plus 19
switchable deviations) is fitted to each design's open-loop trace, every testpoint reset fresh as
the harness now runs it. Flags are added greedily while they reduce the cells off golden, then
pruned. For each full-session final, a mode's share is the cells off golden that adding that one
mode to golden accounts for (the modes overlap a little).
-> docs/evidence/e7/DC-FSM-FINAL-MODES.json, lines on stdout.
"""

import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
E = HERE.parent / "e7"
sys.path.insert(0, str(E / "qualitative" / "or1200_dc_fsm"))
import model as M  # noqa: E402

EQ = Path(os.environ.get("E7_BEHAVIOUR_WORK", "/tmp/e7_behaviour"))
RUNS_DIR = Path(os.environ.get("E7_RUNS", "/home/user/runs-cf"))
_src = (HERE / "feedback_audit.py").read_text().split("\nout = {")[0]
FA = {"__file__": str(HERE / "feedback_audit.py"), "__name__": "feedback_audit"}
exec(compile(_src, str(HERE / "feedback_audit.py"), "exec"), FA)  # simulator, no main
RUNS = ["luna12", "luna13", "luna14"]
INPUTS = ["rst", "dc_en", "dcqmem_cycstb_i", "dcqmem_ci_i", "dcqmem_we_i", "dcqmem_sel_i", "tagcomp_miss",
          "biudata_valid", "biudata_error", "start_addr"]


def stim(run):
    s = json.loads((EQ / "stim" / run / "or1200_dc_fsm.json").read_text())
    idx = [s["inputs"].index(n) for n in INPUTS]
    tps = {}
    for tp in sorted(s["tps"]):
        rows = s["tps"][tp]["rows"]
        rows = json.loads(rows) if isinstance(rows, str) else rows
        tps[tp] = [[int(r[k] or 0) for k in idx] for r in rows]
    return tps


STIM = {r: stim(r) for r in RUNS}
contract = json.loads((EQ / "corpora" / "luna14" / "or1200_dc_fsm" / "contract.json").read_text())
sim = FA["simulator"]("or1200_dc_fsm")


def trace(rtl):
    t = sim(rtl, contract)
    return {r: {tp: [[M.h2i(v) for v in row] for row in rows] for tp, rows in t[r].items()} for r in RUNS}


def cells_off(flags, tr):
    return sum(sum(M.compare(M.run_model_fresh(flags, STIM[r]), tr[r])[2]) for r in RUNS)


def fit(tr):
    cur, best = [], cells_off([], tr)
    while True:
        cand = min(((cells_off(cur + [f], tr), f) for f in M.FLAGS if f not in cur))
        if cand[0] >= best:
            break
        cur.append(cand[1])
        best = cand[0]
    for f in list(cur):
        t = [x for x in cur if x != f]
        if cells_off(t, tr) <= best:
            cur, best = t, cells_off(t, tr)
    return cur, best


golden = (FA["DES"] / "or1200" / "or1200_dc_fsm" / "or1200_dc_fsm.v").read_text()
assert cells_off([], trace(golden)) == 0, "the flags-off model must be golden"
R = RUNS_DIR / "luna14"
designs = {"start (generated, before repair)": E / "luna14/editor/or1200_dc_fsm/rtl_generated.sv",
           "original job's repaired design": E / "luna14/editor/or1200_dc_fsm/rtl.sv",
           "full session, latch alone": R / "editor-full1-cons-fv/or1200_dc_fsm/rtl.sv",
           "full session, latch + judge": R / "editor-full1-cons-fv-arb/or1200_dc_fsm/rtl.sv"}
out = {}
for name, path in designs.items():
    tr = trace(path.read_text())
    flags, resid = fit(tr)
    off = cells_off([], tr)
    out[name] = {"flags": flags, "cells_off_golden": off, "residual": resid,
                 "share": {f: off - cells_off([f], tr) for f in flags}}
    print(f"{name}: {off} cells off golden; modes {flags} (residual {resid}); "
          + ", ".join(f"{f} {100 * v / off:.0f}%" for f, v in out[name]["share"].items()))
(E / "DC-FSM-FINAL-MODES.json").write_text(json.dumps(out, indent=1) + "\n")
