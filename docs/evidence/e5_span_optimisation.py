# ruff: noqa: F821,E402,E501,E701,E702
import json
import sys
sys.path.insert(0, "/home/user/Veri-Sure")
src = open("docs/evidence/e5_report.py").read().replace('RUN = sys.argv[1]', 'RUN = ""')
exec(src.split("cells = V.cells")[0])
from specflow import population as P, variety as V
from specflow.refmodel.oracles import RequirementOracle, decide
cells = V.cells(designs, OUT); names = sorted(designs); N_REQ = 151
shape = P.characterise(designs, OUT)
blob = json.load(open("docs/evidence/e5/run2-oracles.json"))
verdicts, objections, ctl = {}, {}, set()
for o in blob["oracles"]:
    orc = RequirementOracle(req_uid=o["req_uid"], tp_uids=list(TESTPOINTS),
                            clause=o.get("clause",""), source=o["source"])
    per, obj = {}, {}
    for d, rows in designs.items():
        hits, saw = [], False
        for tp in TESTPOINTS:
            r = decide(orc, rows[tp])
            if r.ok is None: continue
            saw = True
            if r.ok is False: hits.append(tp)
        obj[d] = frozenset(hits); per[d] = (False if hits else (True if saw else None))
    if not any(v is not None for v in per.values()): continue
    verdicts[o["req_uid"]] = per; objections[o["req_uid"]] = obj
    if any(decide(orc, control[tp]).ok is False for tp in TESTPOINTS): ctl.add(o["req_uid"])
pl = {k: P.tells(objections[k], shape).placement for k in verdicts}
conv = {k: sum(1 for v in p.values() if v is False) for k, p in verdicts.items()}

def row(label, kept):
    v = {k: p for k, p in verdicts.items() if k in kept}
    bl = V.blind(cells, v)
    acc = [d for d in names if not any(p.get(d) is False for p in v.values())]
    takes = not (set(v) & ctl)
    print(f"  {label:44} span {len(v):3d}/{N_REQ}={100*len(v)/N_REQ:5.1f}%  "
          f"audit {len(set(v)&ctl):2d}  blind {100*len(bl)/len(cells):5.1f}%  "
          f"accepts {len(acc)}+{'CORRECT' if takes else 'no'}")

print("silent (convict 0 of 9):", sum(1 for k in verdicts if conv[k]==0),
      " of", len(verdicts), " -- of those, convict the CONTROL:",
      sum(1 for k in verdicts if conv[k]==0 and k in ctl))
print()
row("as frozen (all deciding)", set(verdicts))
row("t=4", {k for k in verdicts if conv[k] <= 4})
row("t=4 + flat placement >= 0.143", {k for k in verdicts if conv[k] <= 4 and pl[k] >= 0.143})
print("\n**PLACEMENT ONLY WHERE IT IS DEFINED** -- a check with no objections has")
print("  no placement to threshold; the floor applies to objectors only:\n")
for t in (4, 5, 9):
    for floor in (0.0001, 0.143, 0.286):
        row(f"t={t}, objectors need placement >= {floor}",
            {k for k in verdicts if conv[k] <= t and (conv[k] == 0 or pl[k] >= floor)})

print("\nFINE SWEEP at t=4, floor on OBJECTORS only -- maximise span at audit 0")
objectors = [k for k in verdicts if conv[k] <= 4 and conv[k] > 0]
print(f"  {len(objectors)} objectors at t=4; placements:",
      sorted(round(pl[k], 4) for k in objectors))
best = None
for floor in sorted({round(pl[k], 6) for k in objectors} | {0.0}):
    kept = {k for k in verdicts if conv[k] <= 4 and (conv[k] == 0 or pl[k] >= floor)}
    v = {k: p for k, p in verdicts.items() if k in kept}
    bl = V.blind(cells, v)
    acc = [d for d in names if not any(p.get(d) is False for p in v.values())]
    a = len(set(v) & ctl)
    tag = "" if a else "   <- audit 0"
    print(f"  floor {floor:+.4f}  span {len(v):3d}={100*len(v)/N_REQ:5.1f}%  "
          f"audit {a}  blind {100*len(bl)/len(cells):5.1f}%  "
          f"accepts {len(acc)}+{'CORRECT' if not a else 'no'}{tag}")
    if a == 0 and (best is None or len(v) > best[1]):
        best = (floor, len(v), len(bl))
print(f"\n  BEST at audit 0: floor {best[0]:+.4f}, span {best[1]}/{N_REQ} "
      f"= {100*best[1]/N_REQ:.1f}%, blind {100*best[2]/len(cells):.1f}%")
#: The 51 TRUSTED checks that decide NOTHING here are neither kept nor dropped
#: by evidence -- the yardstick has 7 testpoints and they were authored against
#: 625. Reported separately, never folded in.
print(f"  + {len(blob['oracles']) - len(verdicts)} TRUSTED checks unevaluable "
      f"on this yardstick = {100*(best[1] + len(blob['oracles']) - len(verdicts))/N_REQ:.1f}% "
      f"if those are retained")
