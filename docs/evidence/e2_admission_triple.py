"""E2's pre-registered outputs: the TRIPLE on kept-only, admitted-only, union.

E2's own pre-registration says span alone is not the result and must not be
reported as one -- admission is not a filter, so span rises by construction.
What decides the experiment is what admission costs in AUDIT and buys in
BLINDNESS. The two frozen sets from the unbiased rerun carry the bodies, so
this is replay and set arithmetic with zero model calls.

  audit no worse on the admitted set => the gates discarded at random w.r.t.
      soundness and admission is a clean gain;
  audit worse                        => the gates constricted toward the
      correct class; a TRADE, not a win;
  blindness unimproved               => the admitted checks object where the
      kept ones already do and the span gain is NOMINAL.
"""
import glob
import importlib.util
import json
import os
import sys

sys.path.insert(0, "/home/user/Veri-Sure")
from specflow import variety as V  # noqa: E402
from specflow.refmodel.oracles import RequirementOracle, decide  # noqa: E402

OUT = ['cmd_ack', 'busy', 'al', 'dout', 'scl_o', 'scl_oen', 'sda_o', 'sda_oen']
CMD = {"NOP": 0, "START": 1, "STOP": 2, "WRITE": 4, "READ": 8}


def load(path):
    spec = importlib.util.spec_from_file_location(os.path.basename(path), path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m.Model


def stim(seq, *, clk_cnt=4, sda=1, scl=1, hold=6):
    out = [{"nReset": 0, "rst": 1, "ena": 0, "cmd": 0, "din": 0,
            "clk_cnt": clk_cnt, "scl_i": scl, "sda_i": sda}] * 2
    out = list(out)
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
print(f"designs: {len(designs)} -> {sorted(designs)}")
print(f"control: {'yes' if control else 'NO -- audit unavailable'}")

cells = V.cells(designs, OUT)
print(f"disagreement cells: {len(cells)} over {len(designs)} designs\n")

#: WHICH NORMALIZATION'S SETS. "-directonly" is the run whose driver
#: skipped `resolve_indirect`; the bare names are the corrected run. Both
#: are kept because the comparison between them is itself a measurement.
SUFFIX = sys.argv[1] if len(sys.argv) > 1 else ""
SETS = {}
for arm in ("gated", "demoted"):
    b = json.load(open(f"docs/evidence/e2u/{arm}-oracles{SUFFIX}.json"))
    SETS[arm] = {o["req_uid"]: RequirementOracle(
        req_uid=o["req_uid"], tp_uids=list(TESTPOINTS),
        clause=o.get("clause", ""), source=o["source"])
        for o in b["oracles"]}
    print(f"{arm}: {len(SETS[arm])} TRUSTED bodies")

kept = set(SETS["gated"])
admitted = set(SETS["demoted"]) - kept
print(f"\nkept {len(kept)}   admitted {len(admitted)}   "
      f"union {len(kept | admitted)}")
#: ADMISSION IS NOT ALWAYS A SUPERSET. A demoted run takes a different repair
#: path, so a uid TRUSTED under gating can be absent here. Reported rather than
#: assumed -- it changes what "admitted-only" means.
lost = kept - set(SETS["demoted"])
print(f"  TRUSTED under gating but NOT under demotion: {len(lost)}"
      f"{' -> ' + ', '.join(sorted(lost)) if lost else ''}")


def verdicts_of(oracles):
    out = {}
    for uid, oracle in oracles.items():
        per = {}
        for d, rows in designs.items():
            vals = [r.ok for tp in TESTPOINTS
                    if (r := decide(oracle, rows[tp])).ok is not None]
            per[d] = (False if any(v is False for v in vals)
                      else (True if vals else None))
        if any(v is not None for v in per.values()):
            out[uid] = per
    return out


def audit_of(oracles):
    """Checks convicting the control. The control may REJECT, never REPAIR."""
    if not control:
        return set()
    bad = set()
    for uid, oracle in oracles.items():
        for tp in TESTPOINTS:
            if decide(oracle, control[tp]).ok is False:
                bad.add(uid)
                break
    return bad


def report(label, uids, denom):
    src = {**SETS["gated"], **SETS["demoted"]}
    oracles = {u: src[u] for u in uids if u in src}
    v = verdicts_of(oracles)
    a = audit_of(oracles)
    bl = V.blind(cells, v)
    #: `effective_size` -- distinct verdict vectors. Two checks that convict
    #: exactly the same designs are one check for constriction purposes, and
    #: the plan forbids reporting a raw count in their place.
    eff = len({json.dumps(sorted(p.items()), default=str) for p in v.values()})
    acc = [d for d in sorted(designs)
           if not any(p.get(d) is False for p in v.values())]
    print(f"\n{label}")
    print(f"  span        {len(uids):3d} of {denom}  "
          f"= {100 * len(uids) / denom:.1f}%")
    print(f"  decide      {len(v):3d}   effective_size {eff}")
    print(f"  audit       {len(a):3d} of {len(v)} deciding  "
          f"= {100 * len(a) / max(1, len(v)):.1f}%  (convict the control)")
    print(f"  blindness   {len(bl):3d} of {len(cells)}  "
          f"= {100 * len(bl) / max(1, len(cells)):.1f}%")
    print(f"  accepts     {len(acc)} of {len(designs)} designs -> {acc}")
    return {"span": len(uids), "decide": len(v), "effective_size": eff,
            "audit": len(a), "blind": len(bl), "cells": len(cells),
            "accepted": acc}


out = {
    "kept_only": report("KEPT ONLY (gated TRUSTED)", kept, 40),
    "admitted_only": report("ADMITTED ONLY (demotion added)", admitted, 40),
    "union": report("UNION (demoted TRUSTED)", set(SETS["demoted"]), 40),
}
dest = f"docs/evidence/e2-admission-triple{SUFFIX}.json"
json.dump(out, open(dest, "w"), indent=2)
print(f"\nwritten: {dest}")
