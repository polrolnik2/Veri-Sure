# ruff: noqa: F821,E402,E501
import json
import sys
sys.path.insert(0, "/home/user/Veri-Sure")
src = open("docs/evidence/e5_report.py").read()
src = src.replace('RUN = sys.argv[1]', 'RUN = ""')
exec(src.split("cells = V.cells")[0])
from specflow import variety as V
from specflow.refmodel.oracles import RequirementOracle, decide
cells = V.cells(designs, OUT)
blob = json.load(open("docs/evidence/e5/run2-oracles.json"))
verdicts, ctl = {}, set()
for o in blob["oracles"]:
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
        if any(decide(orc, control[tp]).ok is False for tp in TESTPOINTS):
            ctl.add(o["req_uid"])


def score(label, keep):
    v = {k: p for k, p in verdicts.items() if k in keep}
    bl = V.blind(cells, v)
    eff = len({json.dumps(sorted(p.items()), default=str) for p in v.values()})
    acc = [d for d in sorted(designs)
           if not any(p.get(d) is False for p in v.values())]
    print(f"  {label:36} decide {len(v):3d} eff {eff:2d} "
          f"audit {len(set(v) & ctl):2d}={100*len(set(v) & ctl)/max(1, len(v)):4.1f}% "
          f"blind {len(bl):3d}={100*len(bl)/len(cells):4.1f}% accepts {len(acc)} {acc}")


allk = set(verdicts)
ref9 = set(V.refuted_by_the_population(verdicts))
print("\nthe run refuted 12 against its OWN 3 designs")
print(f"against the standing 9, a further {len(ref9)} are refuted")
print(f"  of them, convict the control: {len(ref9 & ctl)} of {len(ref9)}\n")
score("as frozen (102 TRUSTED)", allk)
score(f"minus 9-design refuted ({len(ref9)})", allk - ref9)
score("ceiling: reference-picked (BARRED)", allk - ctl)
