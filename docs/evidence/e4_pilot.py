# ruff: noqa: F821
# `designs`, `verdicts`, `cells`, `audit`, `control`, `TESTPOINTS` and `OUT` all
# arrive from the `exec()` of the E4b driver's setup block below, so the linter
# cannot see them. Re-deriving them here instead would let the pilot and the
# experiment it extends drift apart, which is the one thing that would make the
# two sets of numbers incomparable.
"""E4 PILOT: author at the blind cells, judged on cells closed.

One call per blind PORT, briefed with a LOCATION and the specification -- never
a design, never the observed values, never a claim that either is right.
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, "/home/user/Veri-Sure")
src = open("docs/evidence/e4b_constriction.py").read().split("# ---- the ladder")[0]
exec(src)                                          # designs, verdicts, cells, audit, control
from specflow import variety as V                  # noqa: E402
from specflow.model_io import PortSettings, make_port  # noqa: E402
from specflow.refmodel.oracles import RequirementOracle, decide  # noqa: E402

SPEC = Path("benchmarks/chipverilog/Des/i2c/i2c_master_bit_ctrl/"
            "description.txt").read_text()
sound = {c for c in verdicts if c not in audit}
resid = V.blind(cells, {c: verdicts[c] for c in sound})
targets = V.ranked(resid)[:3]
print(f"\nE4 PILOT: {len(resid)} blind cells, authoring at the top "
      f"{len(targets)} ports: {[p for p, _ in targets]}")

port = make_port("api", Path(sys.argv[1]), None, PortSettings())

ASK = ("\n\nReturn ONLY a Python function in a ```python fence:\n"
       "def decide(trace):\n"
       "    # trace is a list of rows; row['inputs'] and row['outputs'] are\n"
       "    # dicts of port name -> int. Return (ok, edge, why) where ok is\n"
       "    # True/False, or None if the scenario never occurred.\n"
       "If the specification does not constrain this port here, return no "
       "fence and say why instead.")

authored = {}
for port_name, n in targets:
    cell = next(c for c in resid if c.port == port_name)
    driven = {k: v for k, v in
              designs[sorted(designs)[0]][cell.testpoint][-1]["inputs"].items()
              if k in ("cmd", "ena", "rst", "nReset", "scl_i", "sda_i", "din")}
    text = V.brief(cell, requirement=SPEC, activation=(
        "the scenario the driven inputs below produce"), driven=driven) + ASK
    try:
        reply = port.complete(stage=f"variety_{port_name}", round_=0, prompt=text)
    except Exception as exc:
        print(f"  {port_name}: CALL FAILED {exc!r}")
        continue
    m = re.search(r"```python\s*(.+?)```", reply, re.DOTALL)
    if not m:
        print(f"  {port_name}: DECLINED -- {reply.strip()[:140]}")
        continue
    authored[port_name] = m.group(1).strip()
    print(f"  {port_name}: authored {len(authored[port_name])} chars")

# ---- score: cells closed, polarity-corrected, and the audit ---------------
print(f"\n{'port':10} {'runs':>5} {'closes':>7} {'of':>5} {'convicts control':>17}")
for port_name, body in authored.items():
    oracle = RequirementOracle(req_uid=f"NEW-{port_name}",
                               tp_uids=list(TESTPOINTS), clause="", source=body)
    per, ran = {}, False
    for d, rows in designs.items():
        vals = []
        for tp in TESTPOINTS:
            r = decide(oracle, rows[tp])
            if r.ok is not None:
                vals.append(r.ok)
        ran = ran or bool(vals)
        per[d] = (False if any(v is False for v in vals)
                  else (True if vals else None))
    mine = [c for c in resid if c.port == port_name]
    closed = [c for c in mine if V.separates(c, per)]
    conv = any(decide(oracle, control[tp]).ok is False for tp in TESTPOINTS)
    print(f"{port_name:10} {str(ran):>5} {len(closed):>7} {len(mine):>5} "
          f"{str(conv):>17}")
    authored[port_name] = (body, per, closed, conv)

total = sum(len(v[2]) for v in authored.values() if isinstance(v, tuple))
print(f"\nTOTAL: {total} of {len(resid)} blind cells closed = "
      f"{100*total/len(resid):.1f}%")
print("PRE-REGISTERED: <=15% closes the line; the stimulus round's bar was 5%; "
      "the nearest prior (re-authoring WITH a witness) reached 0.")
json.dump({k: {"source": v[0], "closed": len(v[2]), "convicts_control": v[3]}
           for k, v in authored.items() if isinstance(v, tuple)},
          open(sys.argv[2], "w"), indent=2)
