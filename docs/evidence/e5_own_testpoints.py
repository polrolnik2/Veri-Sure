# ruff: noqa: E402
"""Score the frozen set on the testpoints it was actually authored against.

**EVERY FIGURE REPORTED FROM THIS RUN SO FAR USED THE WRONG TRACES.** The
yardstick is seven synthetic testpoints from `e4b_constriction.py`; the 102
frozen checks name 409 testpoints of the run's own, and the OVERLAP IS ZERO.
Scoring overrode each check's `tp_uids` with the seven, so every check ran
against traces it never named -- the 51 that decided did so incidentally.

Here each check is replayed on the testpoints IT names, from the run's own
`stimulus.json`, through `refmodel.oracles.replay` -- the same function the
stage itself uses. A hand-rolled harness cannot substitute: a stimulus step
is `{inputs, hold}` (and sometimes `reset`), not a port dict, and expanding
it to edges is `replay`'s job. Zero model calls; the control is scored last
and never selects.
"""
import glob
import json
import os
import sys

sys.path.insert(0, "/home/user/Veri-Sure")
from specflow import population as P
from specflow import variety as V
from specflow.refmodel.compose import choose_base
from specflow.refmodel.oracles import (RequirementOracle, decide,
                                      replay, transactional_view)

OUT = ['cmd_ack', 'busy', 'al', 'dout', 'scl_o', 'scl_oen', 'sda_o', 'sda_oen']
RUN = sys.argv[1] if len(sys.argv) > 1 else (
    "/tmp/claude-0/-home-user-Veri-Sure/"
    "12bb865e-7a51-5506-b55a-e5ac7cf72a4a/scratchpad/e5run")
N_REQ = 151


CONTRACT = json.loads(
    open("docs/evidence/e3_contract.json").read())
BASE = choose_base(CONTRACT)

stim = {t["tp_uid"]: t["stimulus_steps"]
        for t in json.load(open(f"{RUN}/specflow/stimulus.json"))["testpoints"]}
print(f"stimulus: {len(stim)} testpoints from the run itself")

sources = {}
for p in sorted(glob.glob("docs/evidence/*-i2c.ref_model.py")):
    sources[os.path.basename(p).split("-")[0]] = open(p).read()
for i in range(3):
    f = f"docs/evidence/e5/pop{i}.ref_model.py"
    if os.path.exists(f):
        sources[f"pop{i}"] = open(f).read()
CONTROL_SRC = open("benchmarks/controls/i2c_master_bit_ctrl/ref_model.py").read()


def rows_for(src):
    """`testpoint -> rows`, through the stage's own replay."""
    out = {}
    for tp, steps in stim.items():
        try:
            rep = replay(src, CONTRACT, steps, base=BASE)
        except Exception:
            continue
        if rep.rows:
            out[tp] = transactional_view(rep.rows)
    return out


designs = {}
for name, src in sources.items():
    r = rows_for(src)
    if len(r) > len(stim) * 0.9:
        designs[name] = r
    else:
        print(f"  skip {name}: replayed {len(r)}/{len(stim)}")
control = rows_for(CONTROL_SRC)
control = control if len(control) > len(stim) * 0.9 else None
print(f"designs replayed: {len(designs)} -> {sorted(designs)}; "
      f"control {'yes' if control else 'NO'}")

cells = V.cells(designs, OUT)
print(f"disagreement cells on the run's own testpoints: {len(cells)}\n")

blob = json.load(open("docs/evidence/e5/run2-oracles.json"))
verdicts, objections, ctl = {}, {}, set()
for o in blob["oracles"]:
    #: **ITS OWN TESTPOINTS.** This is the whole correction.
    tps = [t for t in (o.get("tp_uids") or []) if t in stim]
    if not tps:
        continue
    orc = RequirementOracle(req_uid=o["req_uid"], tp_uids=tps,
                            clause=o.get("clause", ""), source=o["source"])
    per, obj = {}, {}
    for d, rows in designs.items():
        hits, saw = [], False
        for tp in tps:
            if tp not in rows:
                continue
            r = decide(orc, rows[tp])
            if r.ok is None:
                continue
            saw = True
            if r.ok is False:
                hits.append(tp)
        obj[d] = frozenset(hits)
        per[d] = (False if hits else (True if saw else None))
    if not any(v is not None for v in per.values()):
        continue
    verdicts[o["req_uid"]] = per
    objections[o["req_uid"]] = obj
    if control and any(decide(orc, control[tp]).ok is False
                       for tp in tps if tp in control):
        ctl.add(o["req_uid"])

print(f"DECIDE   {len(verdicts)} of {len(blob['oracles'])} TRUSTED checks "
      f"decide on >=1 design   (the yardstick gave 51)")
conv = {k: sum(1 for v in p.values() if v is False) for k, p in verdicts.items()}
print(f"  of those, object to nothing: {sum(1 for k in conv if conv[k] == 0)}")
print(f"  convict the control:         {len(ctl)}")

shape = P.characterise(designs, OUT)
pl = {k: P.tells(objections[k], shape).placement for k in verdicts}
print(f"  population effective_size: {shape.effective_size()}; "
      f"split testpoints {len(shape.split)} of {len(shape.testpoints)}\n")


def row(label, kept):
    v = {k: p for k, p in verdicts.items() if k in kept}
    bl = V.blind(cells, v)
    acc = [d for d in sorted(designs)
           if not any(p.get(d) is False for p in v.values())]
    takes = not (set(v) & ctl)
    print(f"  {label:42} span {len(v):3d}/{N_REQ}={100*len(v)/N_REQ:5.1f}%  "
          f"audit {len(set(v) & ctl):3d}={100*len(set(v) & ctl)/max(1, len(v)):5.1f}%  "
          f"blind {100*len(bl)/max(1, len(cells)):5.1f}%  "
          f"accepts {len(acc)}+{'CORRECT' if takes else 'no'}")


row("as frozen", set(verdicts))
N = len(designs)
for t in (0, 2, 4, 6, N - 1):
    row(f"max_convictions = {t}", {k for k in verdicts if conv[k] <= t})
print()
for t in (4, N - 1):
    for floor in (0.05, 0.1, 0.2):
        row(f"t={t}, objectors need placement >= {floor}",
            {k for k in verdicts if conv[k] <= t and (conv[k] == 0 or pl[k] >= floor)})
json.dump({"decide": len(verdicts), "cells": len(cells),
           "silent": sum(1 for k in conv if conv[k] == 0), "audit": len(ctl)},
          open("docs/evidence/e5-own-testpoints.json", "w"), indent=2)
