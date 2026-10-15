# ruff: noqa: F821,E402,E501
import json
import sys
sys.path.insert(0, "/home/user/Veri-Sure")
src = open("docs/evidence/e5_report.py").read().replace('RUN = sys.argv[1]', 'RUN = ""')
exec(src.split("cells = V.cells")[0])
from specflow import variety as V
from specflow.refmodel.oracles import RequirementOracle, decide
cells = V.cells(designs, OUT)
blob = json.load(open("docs/evidence/e5/run2-oracles.json"))
corp = blob.get("corpus") or {}
#: WHICH FROZEN CHECKS CAME FROM A CELL. `_retain` records the arm, so a body
#: still standing at freeze is identifiable by matching its source.
cell_src = {b.get("source") for v in corp.values() for b in v
            if b.get("arm") == "cell"}
frozen = {o["req_uid"]: o for o in blob["oracles"]}
from_cell = {u for u, o in frozen.items() if o.get("source") in cell_src}
print(f"cell bodies retained: {len(cell_src)};  still TRUSTED at freeze: {len(from_cell)}")

verdicts = {}
for u, o in frozen.items():
    orc = RequirementOracle(req_uid=u, tp_uids=list(TESTPOINTS),
                            clause=o.get("clause", ""), source=o["source"])
    per = {}
    for d, rows in designs.items():
        vals = [r.ok for tp in TESTPOINTS
                if (r := decide(orc, rows[tp])).ok is not None]
        per[d] = (False if any(v is False for v in vals)
                  else (True if vals else None))
    if any(v is not None for v in per.values()):
        verdicts[u] = per

without = V.blind(cells, {k: v for k, v in verdicts.items() if k not in from_cell})
with_ = V.blind(cells, verdicts)
print(f"blind WITHOUT the cell checks: {len(without)} of {len(cells)}")
print(f"blind WITH    the cell checks: {len(with_)} of {len(cells)}")
print(f"cells closed BY the cell checks: {len(without) - len(with_)}")
decided = [u for u in from_cell if u in verdicts]
print(f"cell checks that decide on >=1 design: {len(decided)} of {len(from_cell)}")
