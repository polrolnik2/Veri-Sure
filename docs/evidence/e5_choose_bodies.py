"""SELECTION THAT COSTS NO SPAN: choose each requirement's body, never drop one.

`select` drops CHECKS, and a requirement whose only check it drops loses its
span. But the pipeline retains every superseded body, so the same golden-free
score can choose BETWEEN a requirement's bodies instead -- and choosing between
alternatives costs nothing, where discarding costs a requirement.

The score is `placement`, which the Ruleset already defines: `(share of SPLIT
testpoints it speaks on) - (share of AGREED testpoints it speaks on)`. +1 for a
check objecting only where the designs differ, -1 for one objecting only where
they agree, and **0 for a check that objects everywhere OR nowhere** -- both
signs of the defect, in one number, already in the tree.
"""
import json
import sys
from pathlib import Path
sys.path.insert(0, "/home/user/Veri-Sure")
from specflow import oracles_stage as OS
from specflow import population as P
from specflow import variety as V
from specflow.refmodel.compose import choose_base
from specflow.refmodel.oracle_gen import RequirementOracle
from specflow.refmodel.oracles import decide, replay, transactional_view

D = Path("/tmp/claude-0/-home-user-Veri-Sure/12bb865e-7a51-5506-b55a-e5ac7cf72a4a/scratchpad")
E = Path("docs/evidence/e5u")
RUN = D / "o2"
contract = json.loads(Path(
    "benchmarks/baselines/i2c_master_bit_ctrl/arm_a/contract.json").read_text())
pr = json.loads((E/"probes.json").read_text())["probes"]
contract["io"] = list(contract["io"]) + [
    {"name": p["name"], "dir": "probe", "width": p.get("width",1)} for p in pr]
contract["probes"] = [p["name"] for p in pr]
#: THE RUN'S OWN STIMULUS, which its staging loop grew by 81 testpoints.
stim = json.loads((RUN/"specflow"/"stimulus.json").read_text()) \
    if (RUN/"specflow"/"stimulus.json").is_file() else \
    json.loads((E/"stimulus.json").read_text())
stimulus_by_tp = {s["tp_uid"]: s["stimulus_steps"] for s in stim["testpoints"]}
norm = {s["req_uid"]: s for s in json.loads((E/"normalized.json").read_text())["normalized"]}
observable = {u for u, s in norm.items() if (s.get("observable") or [])}
o = json.loads((RUN/"specflow"/"oracles.json").read_text())
population = [p.read_text() for p in sorted((RUN/"specflow"/"population").glob("*.py"))]
base = choose_base(contract)
outs = [str(p["name"]) for p in contract["io"] if p.get("dir") == "output"]

rows = OS._population_rows(population, contract, stimulus_by_tp, base=base,
                           transactional=True)
cells = V.cells(rows, outs)
shape = P.characterise(rows, outs)
print(f"{len(population)} designs, {len(stimulus_by_tp)} testpoints, "
      f"{len(cells)} cells, {len(shape.split)} split testpoint(s), "
      f"effective_size {shape.effective_size()}", flush=True)

#: EVERY BODY, keyed `uid#i`, so one table scores them all at once.
flat, owner = {}, {}
for uid, bodies in o["corpus"].items():
    if uid not in observable:
        continue
    for i, b in enumerate(bodies):
        key = f"{uid}#{i}"
        flat[key] = RequirementOracle(req_uid=key, tp_uids=[], clause="",
                                      source=b["source"])
        owner[key] = uid
print(f"{len(flat)} bodies over {len(set(owner.values()))} observable "
      f"requirement(s)", flush=True)
verd, by_tp, obj = OS._population_tables(flat, population, contract,
                                         stimulus_by_tp, base=base,
                                         transactional=True)
score = {k: P.tells({d: set(v) for d, v in (obj.get(k) or {}).items()},
                    shape).placement for k in flat}

frozen = json.loads((RUN/"specflow"/"oracles.json").read_text())["oracles"]
have = {x["req_uid"]: x["source"] for x in frozen}

control = Path("benchmarks/controls/i2c_master_bit_ctrl/ref_model.py").read_text()
crows, cabs = {}, ()
for tp, steps in stimulus_by_tp.items():
    try:
        rep = replay(control, contract, steps, base=base)
        crows[tp] = transactional_view(rep.rows)
        cabs = rep.unavailable
    except Exception:
        pass

def report(name, chosen):
    tbl = {uid: by_tp.get(key) or {} for uid, key in chosen.items()}
    b = V.blind_at(cells, tbl)
    dec = conv = 0
    for uid, key in chosen.items():
        vals = [v.ok for r in crows.values()
                if not (v := decide(flat[key], r, unavailable=cabs)).broken
                and v.ok is not None]
        if vals:
            dec += 1
            conv += any(x is False for x in vals)
    eff = len({json.dumps(sorted((tp, tuple(sorted(c.items())))
                                 for tp, c in t.items()), default=str)
               for t in tbl.values() if t})
    print(f"{name:<26} span {len(chosen)}/{len(observable)} = "
          f"{100*len(chosen)/len(observable):>5.1f}% | blind {len(b)}/{len(cells)} "
          f"= {100*len(b)/len(cells):>5.1f}% | audit {conv}/{dec} | eff {eff}")

#: What the run froze, expressed in the same keys.
as_frozen = {}
for uid, src in have.items():
    if uid not in observable:
        continue
    for key, orc in flat.items():
        if owner[key] == uid and orc.source == src:
            as_frozen[uid] = key
            break
report("the run's frozen set", as_frozen)

best = {}
for key in sorted(flat):
    uid = owner[key]
    if not any(v is not None for v in (verd.get(key) or {}).values()):
        continue
    if uid not in best or score[key] > score[best[uid]]:
        best[uid] = key
report("best placement per req", best)

#: THE RECORDED LEGS, swept, choosing BETWEEN a requirement's bodies rather
#: than dropping requirements. `convicts` is `max_convictions`'s quantity;
#: `dissent_weighted` is the same count with each design weighted by 1 - its
#: own dissent rate, so convicting the population's outlier costs less than
#: convicting its centre.
prof = {k: P.tells({d: set(v) for d, v in (obj.get(k) or {}).items()}, shape)
        for k in flat}
alive = {k for k in flat
         if any(v is not None for v in (verd.get(k) or {}).values())}
print()
for t in (0, 1, 2, 3, len(population)):
    #: among the bodies convicting at most t, take the best placement; fall
    #: back to the best placement overall rather than lose the requirement.
    chosen = {}
    for key in sorted(alive):
        u = owner[key]
        ok = prof[key].count <= t
        cur = chosen.get(u)
        if cur is None:
            chosen[u] = key
            continue
        cur_ok = prof[cur].count <= t
        if ok and not cur_ok:
            chosen[u] = key
        elif ok == cur_ok and score[key] > score[cur]:
            chosen[u] = key
    report(f"convicts <= {t}, then placement", chosen)

print()
for w in (2.5, 3.0, 4.0):
    chosen = {}
    for key in sorted(alive):
        u = owner[key]
        ok = prof[key].dissent_weighted <= w
        cur = chosen.get(u)
        if cur is None:
            chosen[u] = key
            continue
        cur_ok = prof[cur].dissent_weighted <= w
        if ok and not cur_ok:
            chosen[u] = key
        elif ok == cur_ok and score[key] > score[cur]:
            chosen[u] = key
    report(f"dissent_weighted <= {w}, then placement", chosen)

#: **MARGINAL SEPARATION AS THE TIE-BREAK, WHICH IS BLINDNESS ITSELF.**
#: `placement` is a per-check score and two checks with the same score can
#: close the SAME cells. Greedy marginal gain asks what each one adds to the
#: set, which is the quantity the blindness figure is over. Still golden-free:
#: it reads only which cells the spec-derived designs split on.
print()
closes = {}
for key in sorted(alive):
    t = by_tp.get(key) or {}
    closes[key] = {c for c in cells if V.separates_at(c, t)}
for w in (0.0, 1.0, 2.0, 3.0):
    fit = {}
    for key in sorted(alive):
        fit.setdefault(owner[key], []).append(key)
    covered, chosen = set(), {}
    #: Requirements in descending order of what their best body could add, so
    #: the greedy pass spends its early picks where they are worth most.
    order = sorted(fit, key=lambda u: (-max(len(closes[k]) for k in fit[u]), u))
    for u in order:
        ok = [k for k in sorted(fit[u]) if prof[k].dissent_weighted <= w] or fit[u]
        pick = max(ok, key=lambda k: (len(closes[k] - covered), score[k]))
        chosen[u] = pick
        covered |= closes[pick]
    report(f"dissent_weighted <= {w}, then MARGINAL cells", chosen)
    chosen = {}
    for key in sorted(alive):
        u = owner[key]
        ok = prof[key].dissent_weighted <= w
        cur = chosen.get(u)
        if cur is None:
            chosen[u] = key
            continue
        cur_ok = prof[cur].dissent_weighted <= w
        if ok and not cur_ok:
            chosen[u] = key
        elif ok == cur_ok and score[key] > score[cur]:
            chosen[u] = key
    report(f"dissent_weighted <= {w}, then placement", chosen)

# ---------------------------------------------------------------- diagnosis
#: WHICH check the control convicts under the chosen rule, and what the
#: GOLDEN-FREE tells say about it. Diagnosis only: a rule chosen because it
#: removes this one is a rule tuned on the held-out grade, which is the thing
#: this pipeline refuses to do.
w = 2.0
fit = {}
for key in sorted(alive):
    fit.setdefault(owner[key], []).append(key)
covered, chosen = set(), {}
order = sorted(fit, key=lambda u: (-max(len(closes[k]) for k in fit[u]), u))
for u in order:
    ok = [k for k in sorted(fit[u]) if prof[k].dissent_weighted <= w] or sorted(fit[u])
    pick = max(ok, key=lambda k: (len(closes[k] - covered), score[k]))
    chosen[u] = pick
    covered |= closes[pick]

print("\nunder `dissent_weighted <= 2.0, then MARGINAL`:")
for uid, key in sorted(chosen.items()):
    vals = [v.ok for r in crows.values()
            if not (v := decide(flat[key], r, unavailable=cabs)).broken
            and v.ok is not None]
    if vals and any(x is False for x in vals):
        t = prof[key]
        print(f"  {uid} ({key}) CONVICTS THE CONTROL")
        print(f"    convicts {t.count} of {len(population)} design(s), "
              f"decided {sum(1 for v in (verd.get(key) or {}).values() if v is not None)}")
        print(f"    dissent_weighted {t.dissent_weighted:.3f}  placement "
              f"{t.placement:+.4f}  cluster_count {t.cluster_count}")
        print(f"    split_purity {t.split_purity:.3f}  indiscriminacy "
              f"{t.indiscriminacy:.3f}  mass {t.mass:.4f}")
        print(f"    cells it closes: {len(closes[key])}")
        alt = [k for k in sorted(fit[uid]) if k != key]
        print(f"    other bodies for this requirement: {len(alt)}")
        for k in alt[:4]:
            av = [v.ok for r in crows.values()
                  if not (v := decide(flat[k], r, unavailable=cabs)).broken
                  and v.ok is not None]
            print(f"      {k}: convicts {prof[k].count}, dw "
                  f"{prof[k].dissent_weighted:.3f}, closes {len(closes[k])}, "
                  f"control {'CONVICTS' if av and any(x is False for x in av) else ('spares' if av else 'cannot judge')}")
