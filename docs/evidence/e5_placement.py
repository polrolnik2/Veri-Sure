# ruff: noqa: F821,E402
"""Can t=4's residual audit be driven to 0 by `placement`, and at what span?

At `max_convictions = 4` the set accepts `h, q, s` and exactly ONE surviving
member convicts the control. This asks whether any golden-free tell separates
that one check from the other 36, and what the span is for whatever set comes
out. Zero model calls. The control is scored last and never selects.
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
N_REQ = 151

shape = P.characterise(designs, OUT)
print(f"population shape: {len(shape.designs)} designs, "
      f"effective_size {shape.effective_size}, "
      f"{len(shape.split)} split testpoint(s) of {len(shape.testpoints)}")

#: `objections[design] = the testpoints this check objects on`. Golden-free:
#: built from the check's own verdicts against spec-derived designs.
verdicts, objections, ctl, decided_any = {}, {}, set(), set()
for o in blob["oracles"]:
    orc = RequirementOracle(req_uid=o["req_uid"], tp_uids=list(TESTPOINTS),
                            clause=o.get("clause", ""), source=o["source"])
    per, obj = {}, {}
    for d, rows in designs.items():
        hits, saw = [], False
        for tp in TESTPOINTS:
            r = decide(orc, rows[tp])
            if r.ok is None:
                continue
            saw = True
            if r.ok is False:
                hits.append(tp)
        obj[d] = frozenset(hits)
        per[d] = (False if hits else (True if saw else None))
    if not any(v is not None for v in per.values()):
        continue
    decided_any.add(o["req_uid"])
    verdicts[o["req_uid"]] = per
    objections[o["req_uid"]] = obj
    if any(decide(orc, control[tp]).ok is False for tp in TESTPOINTS):
        ctl.add(o["req_uid"])

n_silent = len(blob["oracles"]) - len(decided_any)
print(f"{len(verdicts)} deciding checks; {n_silent} TRUSTED decide nothing "
      f"on this yardstick\n")


def convicts(p):
    return sum(1 for v in p.values() if v is False)


def report(label, kept):
    v = {k: p for k, p in verdicts.items() if k in kept}
    bl = V.blind(cells, v)
    acc = [d for d in names if not any(p.get(d) is False for p in v.values())]
    #: **SPAN IS OVER REQUIREMENTS, AND A SELECTED SET HAS TWO DENOMINATORS.**
    #: `min_decides >= 1` drops every check that decides nothing here, so the
    #: silent TRUSTED members are counted separately rather than folded in --
    #: they cover a requirement and adjudicate nothing on this population.
    print(f"  {label:34} kept {len(v):3d}  audit {len(set(v) & ctl):2d}="
          f"{100*len(set(v) & ctl)/max(1, len(v)):5.1f}%  "
          f"blind {100*len(bl)/len(cells):5.1f}%  accepts {len(acc)} {acc}  "
          f"span {len(v)}/{N_REQ}={100*len(v)/N_REQ:.1f}% "
          f"(+{n_silent} silent = {100*(len(v)+n_silent)/N_REQ:.1f}%)")


t4 = {k for k, p in verdicts.items() if convicts(p) <= 4}
bad = t4 & ctl
print(f"at t=4 the control-convicting member(s): {sorted(bad)}\n")
print("PLACEMENT OF EVERY t=4 MEMBER (higher = speaks where designs split)")
pl = {k: P.tells(objections[k], shape).placement for k in t4}
order = sorted(t4, key=lambda k: -pl[k])
for k in order:
    mark = "   <-- CONVICTS THE CONTROL" if k in bad else ""
    print(f"    {k:12} placement {pl[k]:+.4f}  convicts {convicts(verdicts[k])}{mark}")

print("\nCAN A PLACEMENT FLOOR REMOVE IT WITHOUT REMOVING THE REST?")
report("t=4 alone", t4)
for floor in sorted({round(pl[k], 4) for k in t4}):
    kept = {k for k in t4 if pl[k] >= floor}
    if not kept or kept == t4:
        continue
    report(f"t=4 and placement >= {floor:+.4f}", kept)

#: **THE PLAN'S HEADLINE, BOTH HALVES.** "One class, containing the correct
#: design." Audit 0 means no surviving check convicts the control, so the SET
#: accepts it -- which is the half every configuration measured so far failed.
print("\nDOES THE SET ACCEPT THE CORRECT DESIGN?")


def classes(acc):
    sig = {d: json.dumps([[r["outputs"] for r in designs[d][tp]]
                          for tp in sorted(TESTPOINTS)], sort_keys=True)
           for d in acc}
    seen = {}
    for d in acc:
        seen.setdefault(sig[d], []).append(d)
    return list(seen.values())


for label, kept in (("t=4 alone", t4),
                    ("t=4 + placement >= +0.1429",
                     {k for k in t4 if pl[k] >= 0.1429})):
    v = {k: p for k, p in verdicts.items() if k in kept}
    acc = [d for d in names if not any(p.get(d) is False for p in v.values())]
    takes_control = not (set(v) & ctl)
    print(f"  {label:30} accepts {len(acc)} spec-derived in "
          f"{len(classes(acc))} class(es); accepts the CONTROL: {takes_control}")
    if takes_control:
        print(f"      -> accepted set is {acc} + the correct design, "
              f"{len(classes(acc)) + 1} class(es) total")
