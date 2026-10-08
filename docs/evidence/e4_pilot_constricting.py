# ruff: noqa: F821
"""E4 PILOT 2: author at the GUARANTEED-CONSTRICTING cells.

Pilot 1 ranked by cell mass, closed 96 cells and moved the accepted set by
nothing. This ranks by `constricting(..., both=True)` -- the 23 cells where both
designs are still accepted, so a check that closes one MUST shrink the set.
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, "/home/user/Veri-Sure")
exec(open("docs/evidence/e4b_constriction.py").read().split("# ---- the ladder")[0])
from specflow import variety as V  # noqa: E402
from specflow.model_io import PortSettings, make_port  # noqa: E402
from specflow.refmodel.oracles import RequirementOracle, decide  # noqa: E402

SPEC = Path("benchmarks/chipverilog/Des/i2c/i2c_master_bit_ctrl/"
            "description.txt").read_text()
sound = {c: verdicts[c] for c in verdicts if c not in audit}
resid = V.blind(cells, sound)
acc = V.constrict(cells, sound, designs, OUT).accepted
must = V.constricting(resid, acc, both=True)
print(f"\naccepted {list(acc)};  residue {len(resid)};  MUST-shrink cells {len(must)}")
targets = V.ranked(must)
print(f"  targets by port: {targets}")

port = make_port("api", Path(sys.argv[1]), None, PortSettings())
ASK = ("\n\nReturn ONLY a Python function in a ```python fence:\n"
       "def decide(trace):\n"
       "    # trace is a list of rows; row['inputs'] and row['outputs'] are\n"
       "    # dicts of port name -> int. Return (ok, edge, why) where ok is\n"
       "    # True/False, or None if the scenario never occurred.\n"
       "If the specification does not constrain this port here, return no "
       "fence and say why instead.")

out = {}
for port_name, _n in targets:
    cell = next(c for c in must if c.port == port_name)
    NAMES = {0: "NOP", 1: "START", 2: "STOP", 4: "WRITE", 8: "READ"}
    driven = {k: v for k, v in
              designs[sorted(designs)[0]][cell.testpoint][-1]["inputs"].items()
              if k in ("cmd", "ena", "rst", "nReset", "scl_i", "sda_i", "din")}
    #: name the command instead of its encoding. Three of pilot 1 and 2's four
    #: declines were about the numeric `cmd` value, which the specification
    #: describes by NAME and never gives an encoding for -- so the author was
    #: being asked to decode something the spec does not state. That is a defect
    #: in this brief, not silence in the spec, and it has to be ruled out before
    #: a decline can be read as a specification finding.
    if "cmd" in driven:
        driven["cmd"] = f"{NAMES.get(driven['cmd'], driven['cmd'])} command"
    text = V.brief(cell, requirement=SPEC,
                   activation="the scenario the driven inputs below produce",
                   driven=driven) + ASK
    try:
        reply = port.complete(stage=f"variety3_{port_name}", round_=0, prompt=text)
    except Exception as exc:
        print(f"  {port_name}: CALL FAILED {exc!r}")
        continue
    m = re.search(r"```python\s*(.+?)```", reply, re.DOTALL)
    if not m:
        print(f"  {port_name}: DECLINED -- {reply.strip()[:120]}")
        continue
    out[port_name] = m.group(1).strip()
    print(f"  {port_name}: authored")

added = {}
for name, body in out.items():
    o = RequirementOracle(req_uid=f"C-{name}", tp_uids=list(TESTPOINTS),
                          clause="", source=body)
    per = {}
    for d, rows in designs.items():
        vals = [decide(o, rows[tp]).ok for tp in TESTPOINTS]
        vals = [v for v in vals if v is not None]
        per[d] = False if any(v is False for v in vals) else (True if vals else None)
    conv = {d for d, v in per.items() if v is False}
    hits_acc = sorted(conv & set(acc))
    convicts_control = any(decide(o, control[tp]).ok is False for tp in TESTPOINTS)
    print(f"  {name}: convicts {sorted(conv)}  of the ACCEPTED: {hits_acc or 'NONE'}"
          f"  control: {convicts_control}")
    if not convicts_control:
        added[f"C-{name}"] = per

before = V.constrict(cells, sound, designs, OUT)
after = V.constrict(cells, {**sound, **added}, designs, OUT)
print(f"\n  BEFORE  accepted {len(before.accepted)} classes {before.classes} "
      f"diameter {before.diameter:.3f} blind {100*before.blind:.1f}%")
print(f"  AFTER   accepted {len(after.accepted)} classes {after.classes} "
      f"diameter {after.diameter:.3f} blind {100*after.blind:.1f}%")
json.dump({k: v for k, v in out.items()}, open(sys.argv[2], "w"), indent=2)
