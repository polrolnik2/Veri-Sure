"""The triple on one run's own corpus, with and without the refutation
preference, scored by the run's own scorecard. Zero model calls.

    e6_boundary.py <evidence-dir> [<out.json>]

Exists to price ONE change: `Window.extent`. Before it, an invariant was
asserted over the row that CLOSED its window -- the row at which the window's
scope has already ended -- so "while A, B holds" convicted every design that
ever left A. The proof is design-free (`test_a_window_does_not_govern_the_row_
that_closed_it`); this measures what it was costing.
"""
import json
import sys
from pathlib import Path
sys.path.insert(0, "/home/user/Veri-Sure")
from specflow import oracles_stage as OS
from specflow import population as POP
from specflow import scorecard as SC
from specflow import variety as V
from specflow.refmodel.compose import choose_base
from specflow.refmodel.oracle_gen import RequirementOracle

E = Path(sys.argv[1])
contract = json.loads(Path(
    "benchmarks/baselines/i2c_master_bit_ctrl/arm_a/contract.json").read_text())
pr = json.loads((E / "probes.json").read_text())["probes"]
contract["io"] = list(contract["io"]) + [
    {"name": p["name"], "dir": "probe", "width": p.get("width", 1)} for p in pr]
contract["probes"] = [p["name"] for p in pr]
stim = json.loads((E / "stimulus.json").read_text())
stimulus_by_tp = {s["tp_uid"]: s["stimulus_steps"] for s in stim["testpoints"]}
o = json.loads((E / "oracles.json").read_text())
reqs = json.loads((E / "requirements.json").read_text())["requirements"]
norm = json.loads((E / "normalized.json").read_text())["normalized"]
population = [p.read_text() for p in sorted((E / "population").glob("*.py"))]
control = Path("benchmarks/controls/i2c_master_bit_ctrl/ref_model.py").read_text()
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
flat, owner = {}, {}
for uid in sorted(o["corpus"]):
    standing = held.get(uid)
    for i, b in enumerate(o["corpus"][uid] or []):
        k = f"{uid}#{i}"
        flat[k] = RequirementOracle(
            req_uid=k, tp_uids=list(standing.tp_uids) if standing else [],
            clause=standing.clause if standing else "", source=b["source"])
        owner[k] = uid
print(f"{E.name}: {len(held)} frozen, {len(flat)} bodies, {len(population)} "
      f"designs, {len(cells)} cells -- replaying", flush=True)

verdicts, by_tp, objections = OS._population_tables(
    flat, population, contract, stimulus_by_tp, base=base, transactional=True)
closes = {k: frozenset(n for n, c in enumerate(cells)
                       if V.separates_at(c, by_tp.get(k) or {})) for k in flat}
tells = {k: POP.tells({d: set(v) for d, v in (objections.get(k) or {}).items()},
                      shape) for k in flat}
alive = {k for k in flat
         if any(v is not None for v in (verdicts.get(k) or {}).values())}
refuted = set(V.refuted_by_the_population(verdicts))
frozen_src = {u: x.source for u, x in held.items()}
per_req: dict[str, list[str]] = {}
for k in flat:
    if k in alive and owner[k] in frozen_src:
        per_req.setdefault(owner[k], []).append(k)
for u in per_req:
    per_req[u].sort(key=lambda k: int(k.rsplit("#", 1)[1]))


def choose(use_ref: bool, maxdw: float) -> dict:
    """`_choose_bodies`'s own key, over the cached tables."""
    covered, out = set(), {}
    order = sorted(per_req,
                   key=lambda u: (-max(len(closes[k]) for k in per_req[u]), u))
    for uid in order:
        tier = ([k for k in per_req[uid] if k not in refuted] or per_req[uid]
                ) if use_ref else per_req[uid]
        pick = max(tier, key=lambda k: (bool(closes[k] - covered),
                                        tells[k].dissent_weighted <= maxdw,
                                        len(closes[k] - covered),
                                        tells[k].placement,
                                        flat[k].source == frozen_src.get(uid)))
        covered |= closes[pick]
        out[uid] = flat[pick].source
    return out


meta = {x["req_uid"]: x for x in o["oracles"]}
maps = {}
for use_ref in (True, False):
    name = f"refute_{'on' if use_ref else 'off'}"
    chosen = maps[name] = choose(use_ref, 2.0)
    rows = [{"req_uid": u, "tp_uids": list(meta[u]["tp_uids"]),
             "clause": meta[u].get("clause", ""), "source": s}
            for u, s in chosen.items()]
    card = SC.score(oracles=rows, normalized=norm,
                    stimulus_by_tp=stimulus_by_tp, contract=contract,
                    population=population, requirements=reqs,
                    audit_control=control)
    print(f"\n{E.name} / {name}\n" + SC.render(card))
    print("  TARGET: " + ("MET" if card.meets(span=0.9, blindness=0.1, audit=0.0)
                          else "NOT MET"), flush=True)
if len(sys.argv) > 2:
    Path(sys.argv[2]).write_text(json.dumps(maps, indent=1))
    print(f"\nwrote {sys.argv[2]}")
