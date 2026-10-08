"""The plan's own metrics, read off a completed pipeline run.

span / audit / blindness / effective_size, plus the two the plan says should
replace the triple as the headline -- how many equivalence CLASSES the set
admits, and whether the correct design is among them -- plus corpus depth and
the cell-authoring yield E4 pre-registered.

**MEASURED AGAINST THE STANDING NINE DESIGNS, NOT THE RUN'S OWN THREE.** The
run used its population internally to refute and to locate cells; scoring
against that same population would be marking its own homework. The nine
`*-i2c.ref_model.py` designs are the yardstick every other figure in this
directory was taken against, so the numbers stay comparable.

The control is used for the AUDIT column only and is computed last.
"""
import collections
import glob
import importlib.util
import itertools
import json
import os
import sys

sys.path.insert(0, "/home/user/Veri-Sure")
from specflow import variety as V  # noqa: E402
from specflow.refmodel.oracles import RequirementOracle, decide  # noqa: E402

OUT = ['cmd_ack', 'busy', 'al', 'dout', 'scl_o', 'scl_oen', 'sda_o', 'sda_oen']
CMD = {"NOP": 0, "START": 1, "STOP": 2, "WRITE": 4, "READ": 8}
RUN = sys.argv[1]


def load(path):
    spec = importlib.util.spec_from_file_location(os.path.basename(path), path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m.Model


def stim(seq, *, clk_cnt=4, sda=1, scl=1, hold=6):
    out = list([{"nReset": 0, "rst": 1, "ena": 0, "cmd": 0, "din": 0,
                 "clk_cnt": clk_cnt, "scl_i": scl, "sda_i": sda}] * 2)
    for name, din in seq:
        for _ in range(hold):
            out.append({"nReset": 1, "rst": 0, "ena": 1, "cmd": CMD[name],
                        "din": din, "clk_cnt": clk_cnt,
                        "scl_i": scl, "sda_i": sda})
    return out


TESTPOINTS = {
    "TP-start":   stim([("START", 0), ("NOP", 0)]),
    "TP-write":   stim([("START", 0), ("WRITE", 1), ("NOP", 0)]),
    "TP-read":    stim([("START", 0), ("READ", 0), ("NOP", 0)]),
    "TP-stop":    stim([("START", 0), ("WRITE", 1), ("STOP", 0)]),
    "TP-arb":     stim([("START", 0), ("WRITE", 1)], sda=0),
    "TP-slow":    stim([("START", 0), ("WRITE", 0)], clk_cnt=9, hold=10),
    "TP-nostart": stim([("WRITE", 1), ("NOP", 0)]),
}


def replay(Model, steps):
    m = Model()
    m.reset()
    rows = []
    for i, inp in enumerate(steps):
        try:
            outs = m.step(dict(inp))
        except Exception:
            return None
        rows.append({"inputs": dict(inp), "outputs": dict(outs), "edge": i})
    return rows


designs = {}
for p in sorted(glob.glob("docs/evidence/*-i2c.ref_model.py")):
    name = os.path.basename(p).split("-")[0]
    try:
        M = load(p)
    except Exception:
        continue
    rows = {tp: r for tp, s in TESTPOINTS.items() if (r := replay(M, s))}
    if len(rows) == len(TESTPOINTS):
        designs[name] = rows

control = None
cp = "benchmarks/controls/i2c_master_bit_ctrl/ref_model.py"
if os.path.exists(cp):
    CM = load(cp)
    cr = {tp: replay(CM, s) for tp, s in TESTPOINTS.items()}
    if all(cr.values()):
        control = cr

cells = V.cells(designs, OUT)
blob = json.load(open(f"{RUN}/specflow/oracles.json"))
reqs = json.load(open(f"{RUN}/specflow/requirements.json"))
reqs = reqs.get("requirements", reqs) if isinstance(reqs, dict) else reqs
n_req = len(reqs)

print(f"yardstick: {len(designs)} designs, {len(cells)} cells, "
      f"control {'yes' if control else 'NO'}")
print(f"run: {n_req} requirements\n")

# ---- the plan's denominators -------------------------------------------
disp = collections.Counter((blob.get("dispositions") or {}).values())
trusted = blob.get("oracles") or []
corp = blob.get("corpus") or {}
depth = sorted(len(v) for v in corp.values())
arms = collections.Counter(b.get("arm") for v in corp.values() for b in v)
print("DISPOSITIONS ", dict(disp))
print(f"SPAN          {len(trusted)} of {n_req} = {100*len(trusted)/max(1,n_req):.1f}%")
print(f"CORPUS        {sum(depth)} bodies / {len(depth)} reqs, "
      f"median {depth[len(depth)//2] if depth else 0}, max {max(depth) if depth else 0}")
print(f"  provenance  {dict(arms)}")
print(f"  cell-authored bodies: {arms.get('cell', 0)}")

# ---- the triple ----------------------------------------------------------
verdicts, convicts_control = {}, set()
for o in trusted:
    orc = RequirementOracle(req_uid=o["req_uid"], tp_uids=list(TESTPOINTS),
                            clause=o.get("clause", ""), source=o["source"])
    per = {}
    for d, rows in designs.items():
        vals = [r.ok for tp in TESTPOINTS
                if (r := decide(orc, rows[tp])).ok is not None]
        per[d] = (False if any(v is False for v in vals)
                  else (True if vals else None))
    if any(v is not None for v in per.values()):
        verdicts[o["req_uid"]] = per
        if control and any(decide(orc, control[tp]).ok is False
                           for tp in TESTPOINTS):
            convicts_control.add(o["req_uid"])

blind = V.blind(cells, verdicts)
eff = len({json.dumps(sorted(p.items()), default=str) for p in verdicts.values()})
accepted = [d for d in sorted(designs)
            if not any(p.get(d) is False for p in verdicts.values())]


def classes(names):
    """Trace-equivalence classes among the accepted designs."""
    sig = {d: json.dumps([[r["outputs"] for r in designs[d][tp]]
                          for tp in sorted(TESTPOINTS)], sort_keys=True)
           for d in names}
    return len({sig[d] for d in names})


def diameter(names):
    if len(names) < 2:
        return 0.0
    worst = 0.0
    for a, b in itertools.combinations(sorted(names), 2):
        diff = tot = 0
        for tp in TESTPOINTS:
            for x, y in zip(designs[a][tp], designs[b][tp]):
                for k in OUT:
                    tot += 1
                    diff += (x["outputs"].get(k) != y["outputs"].get(k))
        worst = max(worst, diff / max(1, tot))
    return worst


print(f"\nDECIDE        {len(verdicts)} of {len(trusted)} TRUSTED decide on >=1 design")
print(f"EFFECTIVE     {eff} distinct verdict vectors")
print(f"AUDIT         {len(convicts_control)} of {len(verdicts)} deciding "
      f"= {100*len(convicts_control)/max(1,len(verdicts)):.1f}% convict the control")
print(f"BLINDNESS     {len(blind)} of {len(cells)} = "
      f"{100*len(blind)/max(1,len(cells)):.1f}%")
print(f"\nCONSTRICTION  accepts {len(accepted)} of {len(designs)} -> {accepted}")
print(f"  classes     {classes(accepted) if accepted else 0}  (target: 1)")
print(f"  diameter    {diameter(accepted):.3f}")

json.dump({"requirements": n_req, "span": len(trusted),
           "dispositions": dict(disp), "corpus_bodies": sum(depth),
           "corpus_median": depth[len(depth)//2] if depth else 0,
           "provenance": dict(arms), "decide": len(verdicts),
           "effective_size": eff, "audit": len(convicts_control),
           "blind": len(blind), "cells": len(cells),
           "accepted": accepted, "classes": classes(accepted) if accepted else 0,
           "diameter": diameter(accepted)},
          open("docs/evidence/e5-full-pipeline.json", "w"), indent=2)
print("\nwritten: docs/evidence/e5-full-pipeline.json")
