"""latency.py -- how much of the disagreement with golden is latency?

From `closed_loop.py`'s traces (each design driven by the stimulus reacting to ITS OWN outputs):
  cl_exact   testpoints whose output trace equals golden's edge for edge
  cl_order   testpoints whose SEQUENCE OF DISTINCT OUTPUT STATES equals golden's -- latency and
             durations ignored, the order of what the design does kept
  cl_port    (testpoint, output port) whose sequence of distinct values equals golden's -- also
             ignores the relative timing BETWEEN ports
  cl_class   behaviour modulo latency: a hash of every testpoint's distinct-state sequence
cl_order - cl_exact is the share of testpoints that differ from golden ONLY in timing.
Also, from `sim.py`'s open-loop traces: ol_port (per-port order-only under the fixed inputs).
-> latency.json (one row per design), merged with metrics.json's rows.
"""

import hashlib
import json
import os
from pathlib import Path

EQ = Path(os.environ.get("E7_BEHAVIOUR_WORK", "/tmp/e7_behaviour"))
MODS = ["fpu_exceptions", "i2c_master_bit_ctrl", "i2c_master_byte_ctrl", "or1200_dc_fsm", "or1200_sb"]


def dedup(rows):
    out = []
    for r in rows:
        if not out or out[-1] != r:
            out.append(r)
    return out


def port_seq(rows, k):
    return dedup([r[k] for r in rows])


base = {(r["module"], r["run"], r["kind"]): r for r in json.loads((EQ / "metrics.json").read_text())}
rows = []
for mod in MODS:
    G = json.loads((EQ / "cl_out" / mod / "golden.json").read_text())
    OG = json.loads((EQ / "out" / mod / "golden.json").read_text())
    runs = sorted(G)
    tps = [(r, tp) for r in runs for tp in sorted(G[r])]
    gcls = hashlib.sha256(json.dumps([dedup(G[r][tp]) for r, tp in tps]).encode()).hexdigest()[:12]
    for f in sorted((EQ / "cl_out" / mod).glob("*.json")):
        if f.stem == "golden":
            continue
        X = json.loads(f.read_text())
        if "compile_error" in X:
            continue
        ol = json.loads((EQ / "out" / mod / f.name).read_text())
        run, kind = f.stem.split(".")
        ex = od = pc = pt = opc = opt = 0
        for r, tp in tps:
            a, g = X[r][tp], G[r][tp]
            ex += a == g
            od += dedup(a) == dedup(g)
            n = len(g[0]) if g else 0
            for k in range(n):
                pc += bool(a) and port_seq(a, k) == port_seq(g, k)
                pt += 1
            oa, og = ol[r][tp], OG[r][tp]
            for k in range(len(og[0]) if og else 0):
                opc += port_seq(oa, k) == port_seq(og, k)
                opt += 1
        cls = hashlib.sha256(json.dumps([dedup(X[r][tp]) for r, tp in tps]).encode()).hexdigest()[:12]
        rows.append({**base[(mod, run, kind)], "cl_exact": ex / len(tps), "cl_order": od / len(tps),
                     "cl_port": pc / pt if pt else None, "ol_port": opc / opt if opt else None,
                     "cl_class": cls, "cl_golden_class": cls == gcls})
(EQ / "latency.json").write_text(json.dumps(rows, indent=1))
print(len(rows), "designs")
