"""A threshold WITH A FLOOR OF ONE BODY PER REQUIREMENT.

    e6_floor.py <corpus-dir> <golden-suite-dir>

`SELECT.md` measured a global threshold on the 476-body pool and found the trade
sharply: one class is reachable at `t=2` and costs 21 points of span, and no
constricting row reaches the 90% bar. The reason is structural, not a tuning
problem -- a global threshold drops checks, and a requirement whose every body is
dropped loses its coverage. At `t=6`, 280 of 476 bodies survive and 15% of
requirements have nothing left.

**THE PLAN SAYS WHAT THE OFFSET IS AND A GLOBAL THRESHOLD CANNOT DELIVER IT:**

> more distinct checks per requirement means selection can drop a bad check
> WITHOUT DROPPING THE REQUIREMENT. This is what offsets selection's span cost.

So: apply the threshold, and where it would empty a requirement, keep that
requirement's BEST body instead.

    keep every body passing `max_convictions = t` (and `min_placement = p`);
    for any requirement left with none, keep its single best body, ranked by
    fewest population convictions, then highest `placement`, then source order.

**THE FLOOR IS POPULATION-ONLY, LIKE THE THRESHOLD.** "Best" is fewest
convictions of the spec-derived designs and highest placement -- both read the
population and neither reads the control. A floor chosen by which body spares
golden would be gating on the grade.

## What each column should do, stated before the run

    span       PRESERVED EXACTLY at the unselected pool's value, by construction:
               every requirement that had a body still has one.
    blindness  between the pool's and the accepted set's. Bodies above the
               threshold are all kept, so most separators survive; the floor
               contributes one body where the threshold contributed none.
    audit      bounded by the threshold EXCEPT on the floored requirements,
               which is where a conviction can still come from. That exception
               is the whole risk and it is reported as its own number.

Golden is RUN and never read.
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, "/home/user/Veri-Sure")
from specflow import population as P  # noqa: E402
from specflow.oracles_stage import _population_rows, _population_tables  # noqa: E402
from specflow.probes import declared_probes  # noqa: E402
from specflow.refmodel.compose import choose_base  # noqa: E402
from specflow.refmodel.oracle_gen import RequirementOracle  # noqa: E402
from specflow.refmodel.oracles import well_formed  # noqa: E402
from specflow.refmodel.rtl_trace import decide_rtl, load_traces  # noqa: E402
from specflow.refmodel.temporal import licenses_a_cycle_count  # noqa: E402
from specflow.scorecard import score  # noqa: E402

SRC, GOLD = Path(sys.argv[1]), Path(sys.argv[2])
blob = json.loads((SRC / "oracles.json").read_text())
oracles, corpus = blob["oracles"], (blob.get("corpus") or {})
_n = json.loads((SRC / "normalized.json").read_text())
normalized = _n["normalized"] if isinstance(_n, dict) else _n
requirements = json.loads((SRC / "requirements.json").read_text())["requirements"]
text_of = {r["uid"]: str(r.get("text") or "") for r in requirements}
_s = json.loads((SRC / "stimulus.json").read_text())
stim = _s["testpoints"] if isinstance(_s, dict) else _s
by_tp = {s["tp_uid"]: s.get("stimulus_steps") or [] for s in stim}
contract = json.loads((GOLD / "contract.json").read_text())
plan = json.loads((SRC / "testplan.json").read_text())["elements"]
population = [p.read_text() for p in sorted((SRC / "population").glob("*.py"))]
traces = load_traces(GOLD / "suite" / "results")
seen = {n for t in traces.values() for e in (t.get("edges") or [])
        for n, v in (e.get("dut") or {}).items() if v is not None}
absent = tuple(n for n in declared_probes(contract) if n not in seen)
accepted = {x["req_uid"]: x for x in oracles}
base = choose_base(contract)
outputs = [str(p.get("name")) for p in (contract.get("io") or [])
           if p.get("dir") == "output" and p.get("name")]
SEQ = re.compile(r"\b(after|then|subsequently|following|in response to|once|"
                 r"thereafter|next)\b", re.I)
EQ = ("sta_condition", "sto_condition")


def demote(x):
    t = text_of.get(x["req_uid"], "")
    if SEQ.search(t) or licenses_a_cycle_count(t):
        return x
    out = re.sub(r"after_activation\s*=\s*True", "after_activation=False",
                 x["source"])
    out = re.sub(r"^(\s*follows\s*=\s*)True", r"\1False", out, flags=re.M)
    return {**x, "source": out} if out != x["source"] else x


def advance(tr, probes):
    out = {}
    for tp, t in tr.items():
        edges = [dict(e) for e in (t.get("edges") or [])]
        duts = [dict(e.get("dut") or {}) for e in edges]
        for i, e in enumerate(edges):
            d = dict(duts[i])
            nxt = duts[i + 1] if i + 1 < len(duts) else {}
            for n in probes:
                if n in d:
                    d[n] = nxt.get(n)
            e["dut"] = d
        out[tp] = {**t, "edges": edges}
    return out


def pool():
    out = list(oracles)
    for uid, members in sorted(corpus.items()):
        anchor = accepted.get(uid)
        if anchor is None:
            continue
        for m in members:
            src = m.get("source") or ""
            if not src or src == anchor["source"]:
                continue
            o = RequirementOracle(req_uid=uid, tp_uids=list(anchor["tp_uids"]),
                                  clause=anchor.get("clause", ""), source=src)
            if well_formed(o, contract, plan) is None:
                out.append({**anchor, "source": src})
    return out


def keyed(bodies):
    held, req_of, n = {}, {}, {}
    for b in bodies:
        uid = str(b["req_uid"])
        i = n.get(uid, 0)
        n[uid] = i + 1
        key = uid if i == 0 else f"{uid}#{i}"
        held[key] = RequirementOracle(
            req_uid=uid, tp_uids=list(b.get("tp_uids") or []),
            clause=str(b.get("clause") or ""), source=str(b["source"]))
        req_of[key] = uid
    return held, req_of


def card(bodies, tr):
    held, _ = keyed(bodies)
    v = {}
    for r in decide_rtl(list(held.values()), tr, contract, transactional=True,
                        stimulus_by_tp=by_tp):
        if r.broken or r.ok is None:
            continue
        per = v.setdefault(r.req_uid, {})
        per[r.tp_uid] = per.get(r.tp_uid, True) and bool(r.ok)
    return score(oracles=bodies, normalized=normalized, stimulus_by_tp=by_tp,
                 contract=contract, population=population,
                 requirements=requirements, audit_verdicts=v,
                 audit_absent=absent)


everything = [demote(x) for x in pool()]
adv = advance(traces, EQ)
print(f"POOL {len(everything)} well-formed bodies, licence rule applied; "
      "phase rule on the control")
print("target: span > 0.90, blindness < 0.10, audit = 0\n", flush=True)

rows_by_design = _population_rows(population, contract, by_tp, base=base,
                                  transactional=True)
shape = P.characterise(rows_by_design, outputs)
held, req_of = keyed(everything)
_verd, _by_tp, objections = _population_tables(
    held, population, contract, by_tp, base=base, transactional=True)


def stats(key):
    per = _verd.get(key, {})
    hits = sum(1 for v in per.values() if v is False)
    decided = sum(1 for v in per.values() if v is not None)
    obj = objections.get(key, {})
    place = P.tells(obj, shape).placement if any(obj.values()) else 0.0
    return hits, decided, place


def choose(t, p):
    """`(kept keys, floored requirement uids)`."""
    kept, by_req = set(), {}
    for k in held:
        hits, decided, place = stats(k)
        by_req.setdefault(req_of[k], []).append((hits, -place, k))
        if decided == 0 or hits > t:
            continue
        if p is not None and any(objections.get(k, {}).values()) and place < p:
            continue
        kept.add(k)
    floored = []
    for uid, cands in by_req.items():
        if any(k in kept for _h, _p, k in cands):
            continue
        #: **THE FLOOR, AND IT IS POPULATION-ONLY.** Fewest convictions of the
        #: spec-derived designs, then highest placement, then source order --
        #: none of which is the control.
        kept.add(sorted(cands)[0][2])
        floored.append(uid)
    return kept, sorted(floored)


print(f"  {'ruleset':26} {'kept':>5} {'floored':>8} {'classes':>8}  accepted",
      flush=True)
ranked = []
grid = [(t, None) for t in (0, 1, 2, 3, 4)] \
    + [(t, p) for t in (1, 2, 3) for p in (0.05, 0.1, 0.143, 0.2)]
for t, p in grid:
    kept, floored = choose(t, p)
    names = [d for d in sorted(rows_by_design)
             if not any(_verd.get(k, {}).get(d) is False for k in kept)]
    classes = len({shape.cluster[d] for d in names if d in shape.cluster})
    label = f"t={t}" + (f", place>={p}" if p is not None else "")
    ranked.append(((classes != 1), classes, -len(kept), label,
                   frozenset(kept), len(floored)))
    print(f"  {label:26} {len(kept):5} {len(floored):8} {classes:8}  "
          f"{''.join(names) or '(none)'}", flush=True)

ranked.sort()
_miss, classes, _nk, label, kept, n_floored = ranked[0]
if classes != 1:
    print(f"\n**NO CONFIGURATION ACCEPTS EXACTLY ONE CLASS**; closest is "
          f"{label} at {classes}.")
print(f"\nCHOSEN ({classes} of {shape.effective_size()} class(es), target 1): "
      f"{label}   {n_floored} requirement(s) floored")
chosen = [b for b, k in zip(everything, held) if k in kept]
c = card(chosen, adv)
print(f"\n  bodies    {len(chosen)} of {len(everything)}")
print(f"  SPAN      {c.span:.4f}  {'MET' if c.span > 0.90 else 'NOT MET'}")
print(f"  BLINDNESS {c.blindness:.4f}  "
      f"{'MET' if (c.blindness or 1) < 0.10 else 'NOT MET'}")
print(f"  AUDIT     {c.control_convicted_by}/{c.control_judges} = {c.audit:.4f}"
      f"  {'MET' if c.audit == 0 else 'NOT MET'}")
print(f"  eff_size  {c.effective_size}")
