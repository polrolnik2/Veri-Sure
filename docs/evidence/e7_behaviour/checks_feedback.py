"""checks_feedback.py -- the checks-only feedback rerun, job by job, from `latency.json`.

Each rerun job repairs ONE start under two feedbacks: `cfc` (the shipped checks alone) and `cfm`
(the checks plus the reference model's values and source -- what every editor run before had).
The start is the original job's round-0 design (`r0`), or for byte_ctrl the generation with its
child available (`cfg`). The original job's final (`final`, model feedback, older code) is shown
for reference. Golden-graded columns are scoring only; nothing here reached a run.

  verdict   ChipVerilog
  ship      shipped requirements passed (the editor's own review)
  edge/tp   open-loop agreement with golden: edges, whole testpoints
  cl_order  closed loop: testpoints whose sequence of distinct output states equals golden's
  ref       edge agreement with the run's own reference model on its own stimulus
-> prints markdown; CHECKS-FEEDBACK.json beside it
"""

import json
import os
import statistics as st
from pathlib import Path

EQ = Path(os.environ.get("E7_BEHAVIOUR_WORK", "/tmp/e7_behaviour"))
E = Path("/home/user/Veri-Sure/docs/evidence/e7")
SH = {"i2c_master_bit_ctrl": "bit_ctrl", "i2c_master_byte_ctrl": "byte_ctrl",
      "or1200_dc_fsm": "dc_fsm", "or1200_sb": "sb", "fpu_exceptions": "fpu"}
COLS = ("verdict", "ship", "g_edge", "g_tp", "cl_order", "ref")

R = {(r["module"], r["run"], r["kind"]): r for r in json.loads((EQ / "latency.json").read_text())}
jobs = sorted({(m, run) for (m, run, k) in R if k in ("cfc", "cfm")}, key=lambda j: (SH[j[0]], j[1]))


def pct(v):
    return f"{100 * v:.1f}" if isinstance(v, (int, float)) else "-"


def cell(r, k):
    if r is None:
        return "-"
    return r["verdict"] if k == "verdict" else pct(r.get(k))


out, rows = [], []
out.append("| job | design | " + " | ".join(COLS) + " |")
out.append("|---|---|" + "---|" * len(COLS))
for m, run in jobs:
    start = "cfg" if (m, run, "cfg") in R else "r0"
    for kind, label in ((start, "start"), ("final", "original final"), ("cfm", "**model**"),
                        ("cfc", "**checks**")):
        r = R.get((m, run, kind))
        out.append(f"| {SH[m]} {run} | {label} | " + " | ".join(cell(r, k) for k in COLS) + " |")
    s, c, f = (R.get((m, run, k)) for k in (start, "cfc", "cfm"))
    if c and f and s:
        rows.append({"module": m, "run": run, "start": start,
                     **{f"{a}_{k}": (x.get(k) if k != "verdict" else x["verdict"])
                        for a, x in (("start", s), ("checks", c), ("model", f)) for k in COLS}})
print("\n".join(out))

print("\n**Paired, checks minus model (same start):**\n")
print("| job | ship | edges equal | testpoints equal | closed-loop order | ref agreement | verdicts (checks / model) |")
print("|---|---|---|---|---|---|---|")
for x in rows:
    d = {k: (x[f"checks_{k}"] - x[f"model_{k}"]) if isinstance(x[f"checks_{k}"], (int, float))
         and isinstance(x[f"model_{k}"], (int, float)) else None for k in COLS[1:]}
    print(f"| {SH[x['module']]} {x['run']} | " + " | ".join(
        f"{100 * d[k]:+.1f}" if d[k] is not None else "-" for k in COLS[1:])
        + f" | {x['checks_verdict']} / {x['model_verdict']} |")
for a in ("checks", "model"):
    print(f"\n- {a}: mean edges equal to golden {pct(st.mean(x[f'{a}_g_edge'] for x in rows))}%, "
          f"mean shipped {pct(st.mean(x[f'{a}_ship'] for x in rows))}%, "
          f"ChipVerilog pass {sum(x[f'{a}_verdict'] == 'pass' for x in rows)}/{len(rows)}, "
          f"moved toward golden (edges) in {sum(x[f'{a}_g_edge'] > x['start_g_edge'] for x in rows)}, "
          f"away in {sum(x[f'{a}_g_edge'] < x['start_g_edge'] for x in rows)}")
(E / "CHECKS-FEEDBACK.json").write_text(json.dumps(rows, indent=1) + "\n")
