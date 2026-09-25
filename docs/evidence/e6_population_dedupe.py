"""Does collapsing near-clones lower the achievable blindness?

Refutation asks whether a check convicts EVERY design. A population carrying
behavioural clones answers that question about copies: a check convicting the
consensus convicts its clones too, so it reads REFUTED and the chooser prefers
away from it -- even when it separates every DISTINCT reading cleanly.

`PopulationShape.cluster` already collapses clones ("five near-clones are one
opinion five times"). This replays one run with one design PER CLUSTER and
recomputes the cells, the refuted set and the achievable blindness.
"""
import json
import sys
from pathlib import Path
sys.path.insert(0, "/home/user/Veri-Sure")
from specflow import oracles_stage as OS
from specflow import population as POP
from specflow import probes as P
from specflow import variety as V
from specflow.refmodel.compose import choose_base
from specflow.refmodel.oracle_gen import RequirementOracle

E = Path(sys.argv[1])
base_c = json.loads(Path("benchmarks/baselines/i2c_master_bit_ctrl/arm_a/contract.json").read_text())
contract = P.in_force(E, base_c)
sbt = {s["tp_uid"]: s["stimulus_steps"] for s in
       json.loads((E/"stimulus.json").read_text())["testpoints"]}
files = sorted((E/"population").glob("*.py"))
pop = [p.read_text() for p in files]
outs = [str(p["name"]) for p in contract["io"]
        if p.get("dir") == "output" and p.get("name")]
base = choose_base(contract)

rows = OS._population_rows(pop, contract, sbt, base=base, transactional=True)
shape = POP.characterise(rows, outs)
clusters = {}
for d, c in shape.cluster.items():
    clusters.setdefault(c, []).append(d)
keep = sorted(v[0] for v in clusters.values())
print(f"{len(rows)} designs -> {len(clusters)} cluster(s); keeping {keep}")

o = json.loads((E/"oracles.json").read_text())
held = {x["req_uid"]: RequirementOracle(
    req_uid=x["req_uid"], tp_uids=list(x["tp_uids"]),
    clause=x.get("clause", ""), source=x["source"]) for x in o["oracles"]}
flat, owner = {}, {}
for uid in sorted(o["corpus"]):
    st = held.get(uid)
    for i, b in enumerate(o["corpus"][uid] or []):
        k = f"{uid}#{i}"
        flat[k] = RequirementOracle(
            req_uid=k, tp_uids=list(st.tp_uids) if st else [],
            clause=st.clause if st else "", source=b["source"])
        owner[k] = uid

for label, idx in (("all designs", list(range(len(pop)))),
                   ("one per cluster", [int(d) for d in keep])):
    sub = [pop[i] for i in idx]
    r = OS._population_rows(sub, contract, sbt, base=base, transactional=True)
    cells = V.cells(r, outs)
    verd, by_tp, _ = OS._population_tables(flat, sub, contract, sbt,
                                           base=base, transactional=True)
    ref = set(V.refuted_by_the_population(verd))
    closes = {k: {c for c in cells if V.separates_at(c, by_tp.get(k) or {})}
              for k in flat}
    per = {}
    for k in flat:
        per.setdefault(owner[k], []).append(k)
    cov = set()
    order = sorted(per, key=lambda u: (-max(len(closes[k]) for k in per[u]), u))
    for uid in order:
        tier = [k for k in per[uid] if k not in ref] or per[uid]
        pick = max(tier, key=lambda k: (bool(closes[k] - cov),
                                        len(closes[k] - cov), k))
        cov |= closes[pick]
    blind = len(cells) - len(cov)
    print(f"  {label:16} designs={len(r)} cells={len(cells):>6} "
          f"refuted={len(ref):>3}/{len(flat)} blind={blind:>6} "
          f"= {100*blind/max(1,len(cells)):.1f}%")
