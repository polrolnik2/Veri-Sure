# ruff: noqa: F821,E402
"""The plan's SELECTION leg, applied to the full-pipeline set.

Every figure reported from the full run so far used no selection rule at all.
"as frozen" is the pipeline's own output; the only filter applied on top was
`variety.refuted_by_the_population`, which is a rejection rule, not selection;
and the reference-picked line is barred. `population.select` -- `placement`,
`max_convictions`, the `t` sweep, the machinery the plan calls its endpoint --
had never been run on any of it.

Zero model calls. The control is scored last and never selects.
"""
import json
import sys

sys.path.insert(0, "/home/user/Veri-Sure")
src = open("docs/evidence/e5_report.py").read().replace('RUN = sys.argv[1]', 'RUN = ""')
exec(src.split("cells = V.cells")[0])
from specflow import population as P
from specflow import variety as V
from specflow.refmodel.oracles import RequirementOracle, decide

cells = V.cells(designs, OUT)
blob = json.load(open("docs/evidence/e5/run2-oracles.json"))
names = sorted(designs)
#: `select` takes flat rows per population member; the yardstick's testpoints
#: are concatenated in a fixed order so every check sees the same trace.
POP = [[r for tp in sorted(TESTPOINTS) for r in designs[d][tp]] for d in names]

corpus, verdicts, ctl = {}, {}, set()


def decider(oracle):
    """A `DecideOn`: run the check on one design's flat rows.

    `select` hands a check the population member's rows, so the testpoints are
    concatenated into one trace. A check written for a single testpoint sees a
    longer trace than it was authored against -- noted because it can change a
    verdict, and because the per-testpoint verdicts below are computed the
    other way and the two columns must not be read as the same measurement.
    """
    def f(rows):
        r = decide(oracle, list(rows))
        return None if r.broken else r.ok
    return f


for o in blob["oracles"]:
    orc = RequirementOracle(req_uid=o["req_uid"], tp_uids=list(TESTPOINTS),
                            clause=o.get("clause", ""), source=o["source"])
    per = {}
    for d, rows in designs.items():
        vals = [r.ok for tp in TESTPOINTS
                if (r := decide(orc, rows[tp])).ok is not None]
        per[d] = (False if any(v is False for v in vals)
                  else (True if vals else None))
    if not any(v is not None for v in per.values()):
        continue
    verdicts[o["req_uid"]] = per
    corpus[o["req_uid"]] = decider(orc)
    if any(decide(orc, control[tp]).ok is False for tp in TESTPOINTS):
        ctl.add(o["req_uid"])

print(f"{len(corpus)} deciding checks over {len(POP)} designs, {len(cells)} cells\n")


def score(label, kept):
    v = {k: p for k, p in verdicts.items() if k in kept}
    bl = V.blind(cells, v)
    eff = len({json.dumps(sorted(p.items()), default=str) for p in v.values()})
    acc = [d for d in names if not any(p.get(d) is False for p in v.values())]
    print(f"  {label:34} kept {len(v):3d} eff {eff:2d} "
          f"audit {len(set(v) & ctl):2d}={100*len(set(v) & ctl)/max(1, len(v)):5.1f}% "
          f"blind {len(bl):3d}={100*len(bl)/len(cells):5.1f}% accepts {len(acc)} {acc}")


#: **ONE SCORING FOR EVERY ROW, AND THE FIRST VERSION OF THIS DRIVER HAD TWO.**
#: `population.select` hands a check the population member's testpoints
#: CONCATENATED into one trace, while the columns here are per-testpoint
#: verdicts. Taking the kept sets from `select` and scoring them per-testpoint
#: mixed two measurements and produced a sweep in which every threshold looked
#: worse than not selecting -- the exact opposite of what one scoring shows.
#: So the sweep is computed directly from the per-testpoint verdicts, and
#: `select` is called afterwards only to record how far the two disagree.
def convicts(p):
    return sum(1 for v in p.values() if v is False)


def classes(acc):
    sig = {d: json.dumps([[r["outputs"] for r in designs[d][tp]]
                          for tp in sorted(TESTPOINTS)], sort_keys=True)
           for d in acc}
    seen = {}
    for d in acc:
        seen.setdefault(sig[d], []).append(d)
    return list(seen.values())


print("THE t SWEEP -- keep a check convicting at most t of the population\n")
for t in range(0, len(names) + 1):
    kept = {k for k, p in verdicts.items() if convicts(p) <= t}
    v = {k: p for k, p in verdicts.items() if k in kept}
    acc = [d for d in names if not any(p.get(d) is False for p in v.values())]
    bl = V.blind(cells, v)
    eff = len({json.dumps(sorted(p.items()), default=str) for p in v.values()})
    #: THE SECOND HALF OF THE PLAN'S HEADLINE. One class is a success only if
    #: the correct design is in it, so whether the SET rejects the control is
    #: reported beside the class count and never folded into it.
    print(f"  t={t}  kept {len(v):3d} eff {eff:2d} "
          f"audit {100*len(set(v) & ctl)/max(1, len(v)):5.1f}% "
          f"blind {100*len(bl)/len(cells):5.1f}%  accepts {len(acc)} in "
          f"{len(classes(acc))} class(es)  set rejects control: "
          f"{bool(kept & ctl)}")

ref = set(V.refuted_by_the_population(verdicts))
drop8 = {k for k, p in verdicts.items() if convicts(p) > len(names) - 1}
print(f"\n`refuted_by_the_population` drops {len(ref)}; "
      f"`max_convictions = {len(names)-1}` drops {len(drop8)}; "
      f"identical: {ref == drop8}")
print("  -- a rejection rule IS selection, and this one is a point on the sweep")

v = {k: p for k, p in verdicts.items() if k not in ctl}
acc = [d for d in names if not any(p.get(d) is False for p in v.values())]
print(f"\nreference-picked (BARRED): kept {len(v)} accepts {len(acc)} {acc} "
      f"in {len(classes(acc))} class(es)")

print("\nHOW FAR `select`'s OWN SCORING DISAGREES (concatenated trace):")
for t in (0, 4, 8):
    try:
        sel = P.select(corpus, POP, ruleset=P.Ruleset(
            max_convictions=t, min_population=2, use_gates=False))
        mine = {k for k, p in verdicts.items() if convicts(p) <= t}
        print(f"  t={t}: select keeps {len(sel.kept)}, per-testpoint keeps "
              f"{len(mine)}, agreeing on {len(set(sel.kept) & mine)}")
    except Exception as exc:
        print(f"  t={t}: refused -- {exc}")
