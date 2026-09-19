"""Replay ONE run's whole corpus against its own population, and cache it.

Every rule variant is then set arithmetic over this cache, at no further
replay cost.  Usage:  tables.py <evidence-dir> <cache.pkl>
"""
import json
import pickle
import sys
from pathlib import Path
sys.path.insert(0, "/home/user/Veri-Sure")
from specflow import oracles_stage as OS
from specflow import population as POP
from specflow import variety as V
from specflow.refmodel.compose import choose_base
from specflow.refmodel.oracle_gen import RequirementOracle

E = Path(sys.argv[1])
OUT = Path(sys.argv[2])
contract = json.loads(Path(
    "benchmarks/baselines/i2c_master_bit_ctrl/arm_a/contract.json").read_text())
pr = json.loads((E/"probes.json").read_text())["probes"]
contract["io"] = list(contract["io"]) + [
    {"name": p["name"], "dir": "probe", "width": p.get("width", 1)} for p in pr]
contract["probes"] = [p["name"] for p in pr]
stim = json.loads((E/"stimulus.json").read_text())
stimulus_by_tp = {s["tp_uid"]: s["stimulus_steps"] for s in stim["testpoints"]}
o = json.loads((E/"oracles.json").read_text())
population = [p.read_text() for p in sorted((E/"population").glob("*.py"))]
base = choose_base(contract)
outputs = [str(p.get("name")) for p in contract["io"]
           if p.get("dir") == "output" and p.get("name")]

held = {x["req_uid"]: RequirementOracle(
    req_uid=x["req_uid"], tp_uids=list(x["tp_uids"]), clause=x.get("clause", ""),
    source=x["source"]) for x in o["oracles"]}
rows_by_design = OS._population_rows(population, contract, stimulus_by_tp,
                                     base=base, transactional=True)
cells = V.cells(rows_by_design, outputs)
shape = POP.characterise(rows_by_design, outputs)
print(f"{len(held)} frozen, {len(population)} designs, {len(cells)} cells",
      flush=True)

flat, owner, arm = {}, {}, {}
for uid in sorted(o["corpus"]):
    standing = held.get(uid)
    for i, b in enumerate(o["corpus"][uid] or []):
        k = f"{uid}#{i}"
        flat[k] = RequirementOracle(
            req_uid=k, tp_uids=list(standing.tp_uids) if standing else [],
            clause=standing.clause if standing else "", source=b["source"])
        owner[k], arm[k] = uid, b.get("arm", "?")
print(f"{len(flat)} corpus bodies -- replaying", flush=True)

verdicts, by_tp, objections = OS._population_tables(
    flat, population, contract, stimulus_by_tp, base=base, transactional=True)
print("replayed", flush=True)

idx = {c: n for n, c in enumerate(cells)}
closes = {k: frozenset(idx[c] for c in cells
                       if V.separates_at(c, by_tp.get(k) or {})) for k in flat}
tells = {k: POP.tells({d: set(v) for d, v in (objections.get(k) or {}).items()},
                      shape) for k in flat}
alive = sorted(k for k in flat
               if any(v is not None for v in (verdicts.get(k) or {}).values()))
refuted = set(V.refuted_by_the_population(verdicts))
vec = {k: json.dumps(sorted((tp, tuple(sorted(col.items())))
                            for tp, col in (by_tp.get(k) or {}).items()),
                     default=str) for k in flat}
with OUT.open("wb") as fh:
    pickle.dump({"cells": len(cells), "closes": closes, "arm": arm,
                 "owner": owner, "alive": alive, "refuted": refuted,
                 "src": {k: v.source for k, v in flat.items()},
                 "dw": {k: tells[k].dissent_weighted for k in flat},
                 "pl": {k: tells[k].placement for k in flat},
                 "vec": vec,
                 "frozen_src": {u: x.source for u, x in held.items()}}, fh)
print(f"cached {OUT}", flush=True)
