"""Dropping checks the design population refutes. Zero model calls.

The unbiased run freezes 37 TRUSTED checks. 14 decide on the population, they
collapse to 9 distinct verdict vectors, half of them convict the known-good
control, and the set accepts 0 of 9 designs -- over-constricted. This asks what
the population alone can say about which checks to drop, reading no reference.

A check convicting EVERY spec-admissible design has convicted the correct one
too, unless the specification is unsatisfiable. That is `variety
.refuted_by_the_population`, and the argument is logical rather than
statistical. The control column is computed LAST and feeds nothing -- it is how
the rule is scored, never how it decides.
"""
import glob
import importlib.util
import json
import os
import sys

sys.path.insert(0, "/home/user/Veri-Sure")
from specflow import variety as V  # noqa: E402
from specflow.refmodel.oracles import RequirementOracle, decide  # noqa: E402

OUT = ['cmd_ack', 'busy', 'al', 'dout', 'scl_o', 'scl_oen', 'sda_o', 'sda_oen']
CMD = {"NOP": 0, "START": 1, "STOP": 2, "WRITE": 4, "READ": 8}


def load(path):
    spec = importlib.util.spec_from_file_location(os.path.basename(path), path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m.Model


def stim(seq, *, clk_cnt=4, sda=1, scl=1, hold=6):
    out = list([{"nReset": 0, "rst": 1, "ena": 0, "cmd": 0, "din": 0,
                 "clk_cnt": clk_cnt, "scl_i": scl, "sda_i": sda}] * 2)
    for name, din in seq:
        for _ in range(hold):
            out.append({"nReset": 1, "rst": 0, "ena": 1, "cmd": CMD[name],
                        "din": din, "clk_cnt": clk_cnt,
                        "scl_i": scl, "sda_i": sda})
    return out


TESTPOINTS = {
    "TP-start":   stim([("START", 0), ("NOP", 0)]),
    "TP-write":   stim([("START", 0), ("WRITE", 1), ("NOP", 0)]),
    "TP-read":    stim([("START", 0), ("READ", 0), ("NOP", 0)]),
    "TP-stop":    stim([("START", 0), ("WRITE", 1), ("STOP", 0)]),
    "TP-arb":     stim([("START", 0), ("WRITE", 1)], sda=0),
    "TP-slow":    stim([("START", 0), ("WRITE", 0)], clk_cnt=9, hold=10),
    "TP-nostart": stim([("WRITE", 1), ("NOP", 0)]),
}


def replay(Model, steps):
    m = Model()
    m.reset()
    rows = []
    for i, inp in enumerate(steps):
        try:
            outs = m.step(dict(inp))
        except Exception:
            return None
        rows.append({"inputs": dict(inp), "outputs": dict(outs), "edge": i})
    return rows


designs = {}
for p in sorted(glob.glob("docs/evidence/*-i2c.ref_model.py")):
    name = os.path.basename(p).split("-")[0]
    try:
        M = load(p)
    except Exception:
        continue
    rows = {tp: r for tp, s in TESTPOINTS.items() if (r := replay(M, s))}
    if len(rows) == len(TESTPOINTS):
        designs[name] = rows

control = None
cp = "benchmarks/controls/i2c_master_bit_ctrl/ref_model.py"
if os.path.exists(cp):
    CM = load(cp)
    cr = {tp: replay(CM, s) for tp, s in TESTPOINTS.items()}
    if all(cr.values()):
        control = cr

cells = V.cells(designs, OUT)
print(f"designs {len(designs)}; control {'yes' if control else 'NO'}; "
      f"cells {len(cells)}")

ARM = sys.argv[1] if len(sys.argv) > 1 else "demoted"
blob = json.load(open(f"docs/evidence/e2u/{ARM}-oracles.json"))
verdicts, convicts_control = {}, set()
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
        #: LAST, AND FEEDING NOTHING. Scoring, not selecting.
        if any(decide(orc, control[tp]).ok is False for tp in TESTPOINTS):
            convicts_control.add(o["req_uid"])

print(f"{ARM}: {len(blob['oracles'])} TRUSTED, {len(verdicts)} decide, "
      f"{len(blob['oracles']) - len(verdicts)} inert on all {len(designs)}\n")


def score(label, keep):
    v = {k: p for k, p in verdicts.items() if k in keep}
    bl = V.blind(cells, v)
    eff = len({json.dumps(sorted(p.items()), default=str) for p in v.values()})
    acc = [d for d in sorted(designs)
           if not any(p.get(d) is False for p in v.values())]
    print(f"  {label:32} decide {len(v):3d}  eff {eff:2d}  "
          f"audit {len(set(v) & convicts_control):2d} = "
          f"{100 * len(set(v) & convicts_control) / max(1, len(v)):4.0f}%  "
          f"blind {len(bl):3d} = {100 * len(bl) / len(cells):4.1f}%  "
          f"accepts {len(acc)}")
    return {"decide": len(v), "effective_size": eff,
            "audit": len(set(v) & convicts_control), "blind": len(bl),
            "accepts": acc}


allk = set(verdicts)
refuted = set(V.refuted_by_the_population(verdicts))
out = {"all": score("ALL deciding", allk),
       "refuted_dropped": score(f"drop population-refuted ({len(refuted)})",
                                allk - refuted)}
#: THE CEILING, FOR SCALE ONLY. Selecting on the control is barred -- it tunes
#: the suite toward the held-out grade -- so this line is what the rule is
#: measured AGAINST and never a configuration to ship.
out["ceiling_reference_picked"] = score("ceiling: reference-picked (BARRED)",
                                        allk - convicts_control)
print(f"\n  refuted: {sorted(refuted)}")
print(f"  of them, convict the control: "
      f"{len(refuted & convicts_control)} of {len(refuted)}  "
      f"-- the rule never reads the control")
json.dump(out, open(f"docs/evidence/e2-refutation-{ARM}.json", "w"), indent=2)
