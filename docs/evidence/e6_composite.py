"""Everything at once, in a stated order: deep pool, both rules, then selection.

    e6_composite.py <corpus-dir> <golden-suite-dir>

The three targets have never been met together. `POOL-DEPTH.md` meets span and
blindness on the deep pool and pays for it in audit; `TRIPLE.md`'s two rules take
the accepted set's audit from 9/42 to 1/40 and leave blindness at 0.1416. This
composes them.

**THE ORDER IS STATED AND EACH STEP'S MARGINAL EFFECT IS REPORTED, BECAUSE
SUMMING PER-GATE WINS DOUBLE-COUNTS.** `LAYERED-GATES.md` is the worked example:
the `TO_END` refusal looked worth two convictions measured against the frozen set
and was worth none measured after the width guards, which had already removed
them. So no row here is quotable on its own; the column that matters is what each
row adds to the one above it.

    1  pool                  every well-formed corpus body beside the accepted set
    2  + licence rule        `|=>` demoted to `|->` where the requirement's words
                             carry no sequence word and license no cycle count
    3  + phase rule          the control's `sta_condition`/`sto_condition` read
                             one edge early -- the two probes the specification
                             writes an equation for
    4  + selection           `max_convictions` and `min_placement`, thresholds
                             chosen by FEWEST CLASSES ACCEPTED, a population-only
                             criterion

Every rule reads the requirement's text or the spec-derived population. None
reads the audit column, and the threshold in step 4 is not chosen by it either.

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


def demote(x: dict) -> dict:
    """`TRIPLE.md`'s licence rule, unchanged."""
    t = text_of.get(x["req_uid"], "")
    if SEQ.search(t) or licenses_a_cycle_count(t):
        return x
    out = re.sub(r"after_activation\s*=\s*True", "after_activation=False",
                 x["source"])
    out = re.sub(r"^(\s*follows\s*=\s*)True", r"\1False", out, flags=re.M)
    return {**x, "source": out} if out != x["source"] else x


def advance(tr, probes):
    """`TRIPLE.md`'s phase rule, unchanged."""
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


def pool() -> list[dict]:
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
    v: dict = {}
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


def show(label, c):
    def m(ok):
        return "MET" if ok else "no "
    print(f"  {label:34} SPAN {c.span:.4f} {m(c.span > 0.90)}  "
          f"BLIND {c.blindness:.4f} {m((c.blindness or 1) < 0.10)}  "
          f"AUDIT {c.control_convicted_by}/{c.control_judges} = {c.audit:.4f} "
          f"{m(c.audit == 0)}  eff {c.effective_size}", flush=True)


everything = pool()
adv = advance(traces, EQ)
print(f"POOL {len(everything)} well-formed bodies "
      f"(accepted {len(oracles)}, corpus {sum(len(v) for v in corpus.values())})")
print("target: span > 0.90, blindness < 0.10, audit = 0\n")

show("1  pool", card(everything, traces))
fixed = [demote(x) for x in everything]
show("2  + licence rule", card(fixed, traces))
show("3  + phase rule", card(fixed, adv))

#: **STEP 4.** One population replay, then the grid, then `score` on the winner.
rows_by_design = _population_rows(population, contract, by_tp, base=base,
                                  transactional=True)
shape = P.characterise(rows_by_design, outputs)
held, req_of = keyed(fixed)
_verd, _by_tp, objections = _population_tables(
    held, population, contract, by_tp, base=base, transactional=True)
obs = {str(n.get("req_uid") or n.get("uid")) for n in normalized
       if (n.get("observable") or [])}
kinds = {r["uid"]: str(r.get("unit_kind") or "") for r in requirements}
denom = {u for u in obs if kinds.get(u) == "behavioural"}


def legs(key, t, p):
    per = _verd.get(key, {})
    hits = sum(1 for v in per.values() if v is False)
    if sum(1 for v in per.values() if v is not None) == 0:
        return "silent"
    if hits > t:
        return "over_strict"
    if p is not None:
        obj = objections.get(key, {})
        if any(obj.values()) and P.tells(obj, shape).placement < p:
            return "placement"
    return ""


print(f"\n  {'ruleset':30} {'kept':>5} {'span*':>7} {'classes':>8}  accepted")
grid = [(t, None) for t in (0, 1, 2, 3, 4, 5, 6)] \
    + [(t, p) for t in (4, 6) for p in (0.05, 0.1, 0.143, 0.2)]
ranked = []
for t, p in grid:
    keep = {k for k in held if not legs(k, t, p)}
    if not keep:
        continue
    names = [d for d in sorted(rows_by_design)
             if not any(_verd.get(k, {}).get(d) is False for k in keep)]
    classes = len({shape.cluster[d] for d in names if d in shape.cluster})
    sp = len({req_of[k] for k in keep} & denom) / len(denom) if denom else 0.0
    ranked.append((classes, -sp, f"t={t}"
                   + (f", placement>={p}" if p is not None else ""),
                   frozenset(keep)))
    print(f"  t={t}{f', placement>={p}' if p is not None else '':<14} "
          f"{len(keep):5} {sp:7.4f} {classes:8}  {''.join(names) or '(none)'}",
          flush=True)

if ranked:
    ranked.sort()
    classes, _negsp, label, keep = ranked[0]
    print(f"\nFEWEST CLASSES ({classes} of {shape.effective_size()}), "
          f"TIE-BROKEN ON SPAN: {label}")
    chosen = [b for b, k in zip(fixed, held) if k in keep]
    c = card(chosen, adv)
    show("4  + selection", c)
    print(f"\n  bodies {len(chosen)} of {len(fixed)}")
    print(f"  SPAN      {c.span:.4f}  {'MET' if c.span > 0.90 else 'NOT MET'}")
    print(f"  BLINDNESS {c.blindness:.4f}  "
          f"{'MET' if (c.blindness or 1) < 0.10 else 'NOT MET'}")
    print(f"  AUDIT     {c.control_convicted_by}/{c.control_judges} = "
          f"{c.audit:.4f}  {'MET' if c.audit == 0 else 'NOT MET'}")
