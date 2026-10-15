"""Fill the pool, then SELECT -- the plan's endpoint, on the run's own testpoints.

    e6_select.py <corpus-dir> <golden-suite-dir>

The plan's central direction is "fill the pool, then select": admission and
authoring are selection's INPUT, not its competitors. Until `scorecard.score`
stopped keying checks by `req_uid`, neither half was measurable -- a deeper pool
collapsed to one body per requirement, and `POOL.md` records the sweep reading
122, 241 and 349 checks and being 122 every time. It now carries a set.

## Every rule here is golden-free, and the CHOICE of threshold is too

  `max_convictions = t`   drop a check convicting more than `t` of the
                          spec-derived designs. Reads the population only.
  `min_placement = p`     keep a check whose objections land where the
                          population SPLITS -- `(share of split testpoints it
                          speaks on) - (share of agreed testpoints it speaks
                          on)`. Reads the population only.

**AND THE THRESHOLD IS PICKED BY A POPULATION-ONLY CRITERION, NOT BY THE AUDIT
COLUMN.** Picking `t` and `p` because they give `audit = 0` is gating on the
grade and is barred, however the rule is worded -- the bar is about what a choice
is DETERMINED by. So the criterion is the plan's own primary metric:

    keep the configurations that accept EXACTLY ONE equivalence class, and among
    those take the highest span.

**EXACTLY ONE, NOT FEWEST -- AND THE FIRST VERSION OF THIS FILE SAID FEWEST.**
The grid answered it in one run: `pool, unselected` and eight of the seventeen
rows accept ZERO designs, so "fewest" ranked total over-constriction first. The
plan is explicit and I had not read it closely enough: "Accepting exactly one
class is a success only if the correct design is in it -- otherwise it is the
screened set's failure wearing a good number", and "None, or one excluding the
correct design => over-constricted".

Classes come from `PopulationShape.cluster`, single-link clustering on pair
distance among the spec-derived designs. The audit column is computed afterwards
for whatever the criterion picked, and reported -- never consulted. Whether the
CONTROL is in the accepted class is exactly what `audit = 0` says, so that half of
the plan's success test is the reported number rather than an input to the
choice.

`min_placement`'s sign matters and the recorded result had it backwards:
`population.py` carries the retraction. `placement < 0.0017` "keeps the 126 t=0
checks, which score 0 by objecting to nothing, plus 25 of which 24 convict all
seven designs, which score ~0 by objecting to everything" -- a check convicting
both sides of a pair separates neither. The corrected leg is a MINIMUM, and its
threshold has never been measured on a run's own testpoints. That is what the
sweep below is for.

## ONE POPULATION REPLAY FOR THE WHOLE SWEEP, AND `score` ONLY FOR THE WINNER

A first version of this file called `score` -- and so `_population_tables` --
once per grid row: seventeen replays of 476 bodies over 7 designs and 482
testpoints, which is hours. `_population_tables`'s own docstring says why that is
the wrong shape: "each used to replay the population for itself. With the scope
widened to every testpoint that is 3 x 499 replays per instrument per round; done
once it is 3 x 499 for all of them."

So the population is replayed ONCE, and the sweep's only job -- picking the
configuration by CLASSES ACCEPTED -- needs nothing but that table and
`shape.cluster`. Blindness and audit are not computed per row and are not what
the choice is made on. The chosen configuration is then scored by
`scorecard.score` with the RTL audit column, so the headline triple comes from the
shipped function rather than from anything reimplemented here.

Golden is RUN and never read.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, "/home/user/Veri-Sure")
from specflow import population as P  # noqa: E402
from specflow.probes import declared_probes  # noqa: E402
from specflow.refmodel.compose import choose_base  # noqa: E402
from specflow.refmodel.oracle_gen import RequirementOracle  # noqa: E402
from specflow.refmodel.oracles import well_formed  # noqa: E402
from specflow.refmodel.rtl_trace import decide_rtl, load_traces  # noqa: E402
from specflow.scorecard import score  # noqa: E402

SRC, GOLD = Path(sys.argv[1]), Path(sys.argv[2])
blob = json.loads((SRC / "oracles.json").read_text())
oracles, corpus = blob["oracles"], (blob.get("corpus") or {})
_n = json.loads((SRC / "normalized.json").read_text())
normalized = _n["normalized"] if isinstance(_n, dict) else _n
requirements = json.loads((SRC / "requirements.json").read_text())["requirements"]
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


def pool() -> list[dict]:
    """The accepted set plus every OTHER well-formed corpus body.

    Admission is by `well_formed` and nothing else -- the same mechanical screen
    the pipeline already applies, which is why admitting is not a judgement.
    """
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


def keyed(bodies: list[dict]) -> tuple[dict, dict]:
    """`(key -> RequirementOracle, key -> req_uid)`, first body keeps the uid --
    the same identity scheme `scorecard.score` uses, so the two agree."""
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


def card_for(bodies: list[dict]):
    """The triple for a set of bodies, audit from the RTL control."""
    held, _ = keyed(bodies)
    v: dict = {}
    for r in decide_rtl(list(held.values()), traces, contract,
                        transactional=True, stimulus_by_tp=by_tp):
        if r.broken or r.ok is None:
            continue
        per = v.setdefault(r.req_uid, {})
        per[r.tp_uid] = per.get(r.tp_uid, True) and bool(r.ok)
    return score(oracles=bodies, normalized=normalized, stimulus_by_tp=by_tp,
                 contract=contract, population=population,
                 requirements=requirements, audit_verdicts=v,
                 audit_absent=absent)


from specflow.oracles_stage import (_population_rows,  # noqa: E402
                                    _population_tables)

everything = pool()
print(f"corpus {sum(len(v) for v in corpus.values())} bodies over {len(corpus)} "
      f"requirement(s); accepted {len(oracles)}; POOL {len(everything)} "
      f"well-formed bodies\n", flush=True)

rows_by_design = _population_rows(population, contract, by_tp, base=base,
                                  transactional=True)
shape = P.characterise(rows_by_design, outputs)
print(f"population: {len(shape.designs)} design(s), effective_size "
      f"{shape.effective_size()}, {len(shape.split)} split testpoint(s) of "
      f"{len(shape.testpoints)}\n", flush=True)

held, req_of = keyed(everything)
_verd, _by_tp, objections = _population_tables(
    held, population, contract, by_tp, base=base, transactional=True)

#: **WHY `P.select` IS NOT CALLED, WHICH NEEDS SAYING.** Its signature takes
#: `population: Sequence[Rows]` -- one flat row list per design -- and decides
#: each check by running it over that. Here a design's rows are per TESTPOINT
#: (`{tp: rows}`), and flattening them would hand each check one concatenated
#: trace, so "convicts this design" would stop meaning what it means everywhere
#: else on this branch. Feeding a shipped function the wrong shape is worse than
#: not calling it.
#:
#: So the two legs are evaluated here from the table `scorecard.score` itself
#: uses -- `_population_tables`, one replay for all instruments -- and the
#: non-trivial half, `placement`, still comes from the shipped `P.tells` rather
#: than being re-derived. What is reimplemented is two comparisons: `hits > t`
#: and `placement < p`, plus the objectors-only refinement `population.py`
#: records ("a check that objects NOWHERE scores exactly 0, the same score as
#: one that objects EVERYWHERE" -- a flat floor discards both, and on the
#: full-pipeline set the refinement kept 33 checks instead of 6 at identical
#: audit and blindness).
def legs(key: str, t: int, p: float | None) -> str:
    """`""` to keep, else which leg dropped it."""
    per = _verd.get(key, {})
    hits = sum(1 for v in per.values() if v is False)
    decided = sum(1 for v in per.values() if v is not None)
    if decided == 0:
        return "silent"
    if hits > t:
        return "over_strict"
    if p is not None:
        obj = objections.get(key, {})
        if any(obj.values()) and P.tells(obj, shape).placement < p:
            return "placement"
    return ""

print("target: span > 0.90, blindness < 0.10, audit = 0")
print("criterion: FEWEST CLASSES ACCEPTED, then higher span. The audit column "
      "is\n           reported for the winner and never consulted.\n")

#: span's denominator, the same rule `score` uses: requirements that are
#: behavioural AND state an observable obligation.
obs = {str(n.get("req_uid") or n.get("uid")) for n in normalized
       if (n.get("observable") or [])}
kinds = {r["uid"]: str(r.get("unit_kind") or "") for r in requirements}
denom = {u for u in obs if kinds.get(u) == "behavioural"}


def span_of(keys) -> float:
    covered = {req_of[k] for k in keys} & denom
    return len(covered) / len(denom) if denom else 0.0


print(f"  {'ruleset':30} {'kept':>5} {'span*':>7} {'classes':>8}  accepted")
rows = []
#: **WIDENED AROUND t=2, WHICH THE FIRST RUN SHOWED IS THE ONLY ONE-CLASS ROW.**
#: That is not threshold-picking by the grade: the class count is population-only
#: and the audit column has not been looked at for any row here.
grid = [(None, None)] + [(t, None) for t in (0, 1, 2, 3, 4, 5, 6)] \
    + [(2, p) for p in (0.0, 0.05, 0.1, 0.143, 0.2, 0.3)] \
    + [(1, p) for p in (0.1, 0.143)] \
    + [(3, p) for p in (0.1, 0.143, 0.2)] \
    + [(4, p) for p in (0.143, 0.2, 0.3)]
for t, p in grid:
    if t is None:
        keep_keys, label = set(held), "pool, unselected"
    else:
        keep_keys = {k for k in held if not legs(k, t, p)}
        label = f"t={t}" + (f", placement>={p}" if p is not None else "")
    if not keep_keys:
        print(f"  {label:30} {0:>5}   (empty set)")
        continue
    accepted_names = [d for d in sorted(rows_by_design)
                      if not any(_verd.get(k, {}).get(d) is False
                                 for k in keep_keys)]
    classes = len({shape.cluster[d] for d in accepted_names
                   if d in shape.cluster})
    sp = span_of(keep_keys)
    #: **ONE CLASS IS THE TARGET; ZERO IS THE OPPOSITE FAILURE.** Sorting on
    #: `classes` alone put the eight rows that accept NO design first.
    #: `(classes != 1, classes, -span)` keeps the one-class rows at the front,
    #: orders the rest by how far they are from one, and breaks ties on span.
    rows.append(((classes != 1), classes, -sp, label, frozenset(keep_keys)))
    print(f"  {label:30} {len(keep_keys):5} {sp:7.4f} {classes:8}  "
          f"{''.join(accepted_names) or '(none)'}", flush=True)

print("\n  span* is requirements covered over the behavioural-observable "
      "denominator,\n  computed here to rank the grid; the winner's span below "
      "comes from `score`.")

if not rows:
    print("\nno configuration kept anything")
    raise SystemExit(1)
rows.sort()
_miss, classes, negsp, label, keep_keys = rows[0]
if classes != 1:
    print(f"\n**NO CONFIGURATION ACCEPTS EXACTLY ONE CLASS.** The closest is "
          f"{label} at {classes}; zero accepted designs is total "
          f"over-constriction, not success.")
print(f"\nCHOSEN ({classes} class(es)), TIE-BROKEN ON SPAN: {label}")
print("scoring it with the RTL audit column ...", flush=True)
bodies = [b for b, k in zip(everything, held) if k in keep_keys]
c = card_for(bodies)
print(f"\n  bodies      {len(bodies)} of {len(everything)}")
print(f"  SPAN        {c.span:.4f}  {'MET' if c.span > 0.90 else 'NOT MET'}")
print(f"  BLINDNESS   {c.blindness:.4f}  "
      f"{'MET' if (c.blindness or 1) < 0.10 else 'NOT MET'}")
print(f"  AUDIT       {c.control_convicted_by}/{c.control_judges} = "
      f"{c.audit:.4f}  {'MET' if c.audit == 0 else 'NOT MET'}")
print(f"  classes accepted {classes} of {shape.effective_size()}  "
      f"(target 1)   "
      f"effective_size {c.effective_size}")
for n in c.notes:
    print(f"  note: {str(n)[:150]}")
