"""Score a chosen-body map with the run's OWN scorecard. Zero model calls.

    score_map.py <evidence-dir> <variants.json> [name ...]

The control is read by `specflow.scorecard` and by nothing else, which is the
whole reason `audit_control` is a separate parameter from `refmodel_control`.
"""
import json
import sys
from pathlib import Path
sys.path.insert(0, "/home/user/Veri-Sure")
from specflow import scorecard as SC

E = Path(sys.argv[1])
V = json.loads(Path(sys.argv[2]).read_text())
want = sys.argv[3:] or [k for k in V if isinstance(V[k], dict)]

contract = json.loads(Path(
    "benchmarks/baselines/i2c_master_bit_ctrl/arm_a/contract.json").read_text())
pr = json.loads((E/"probes.json").read_text())["probes"]
contract["io"] = list(contract["io"]) + [
    {"name": p["name"], "dir": "probe", "width": p.get("width", 1)} for p in pr]
contract["probes"] = [p["name"] for p in pr]
stim = json.loads((E/"stimulus.json").read_text())
stimulus_by_tp = {s["tp_uid"]: s["stimulus_steps"] for s in stim["testpoints"]}
o = json.loads((E/"oracles.json").read_text())
reqs = json.loads((E/"requirements.json").read_text())["requirements"]
norm = json.loads((E/"normalized.json").read_text())["normalized"]
population = [p.read_text() for p in sorted((E/"population").glob("*.py"))]
meta = {x["req_uid"]: x for x in o["oracles"]}
control = Path("benchmarks/controls/i2c_master_bit_ctrl/ref_model.py").read_text()

for name in want:
    chosen = V[name]
    rows = [{"req_uid": u, "tp_uids": list(meta[u]["tp_uids"]) if u in meta else [],
             "clause": meta[u].get("clause", "") if u in meta else "",
             "source": s} for u, s in chosen.items()]
    c = SC.score(oracles=rows, normalized=norm, stimulus_by_tp=stimulus_by_tp,
                 contract=contract, population=population, requirements=reqs,
                 audit_control=control)
    print(f"\n{name}\n" + SC.render(c))
    print(f"  TARGET: {'MET' if c.meets(span=0.9, blindness=0.1, audit=0.0) else 'NOT MET'}",
          flush=True)
