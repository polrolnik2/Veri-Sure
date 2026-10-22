"""feedback_audit_report.py -- tables from FEEDBACK-AUDIT.json (feedback_audit.py).

Only commits whose replay is exact (every edit in the batch reproduced) and whose submitted
design was simulated are counted. Golden's view of a commit, from the (edge, output) cells it
changed relative to the accepted design:
  unchanged    no output changed on any edge of the stimulus
  improvement  cells fixed, none broken
  regression   cells broken, none fixed
  mixed        both; net = fixed - broken
The editor's view: passing requirements before -> after, the requirements it was told broke, and
whether the commit latched.
"""

import json
import statistics as st
from pathlib import Path

E = Path(__file__).resolve().parents[1] / "e7"
SH = {"i2c_master_bit_ctrl": "bit_ctrl", "i2c_master_byte_ctrl": "byte_ctrl",
      "or1200_dc_fsm": "dc_fsm", "or1200_sb": "sb"}
A = json.loads((E / "FEEDBACK-AUDIT.json").read_text())


def golden_class(c):
    f, b = c["cells_fixed"], c["cells_broken"]
    return "unchanged" if not f and not b else "improvement" if not b else "regression" if not f else "mixed"


def passing(c):
    a, b = (int(x) for x in c["requirements"]["passing"].split(" -> "))
    return a, b


rows, skipped = [], {"not exact": 0, "no requirements (rejected before simulation)": 0, "did not compile": 0}
for j in A["jobs"]:
    for c in j["commits"]:
        if not c.get("exact"):
            skipped["not exact"] += 1
        elif not c.get("requirements"):
            skipped["no requirements (rejected before simulation)"] += 1
        elif "cells_fixed" not in c:
            skipped["did not compile"] += 1
        else:
            rows.append({**c, "job": f"{SH[j['module']]} {j['run']}", "golden": golden_class(c),
                         "dpass": passing(c)[1] - passing(c)[0], "told_broken": len(c["requirements"]["broken"]),
                         "net": c["cells_fixed"] - c["cells_broken"],
                         "dedge": c["edge_after"] - c["edge_before"], "dtp": c["tp_after"] - c["tp_before"]})
total = sum(len(j["commits"]) for j in A["jobs"])
print(f"{len(rows)} of {total} commits counted; not counted: {skipped}\n")

print("## 1. What golden says each commit did, by whether it latched\n")
print("| golden's view | latched | not latched | mean change in edges equal (latched / not), points |")
print("|---|---|---|---|")
for g in ("improvement", "mixed", "regression", "unchanged"):
    lat = [r for r in rows if r["golden"] == g and r["latched"]]
    rej = [r for r in rows if r["golden"] == g and not r["latched"]]
    m = [f"{100 * st.mean(r['dedge'] for r in x):+.2f}" if x else "-" for x in (lat, rej)]
    print(f"| {g} | {len(lat)} | {len(rej)} | {m[0]} / {m[1]} |")
mixed = [r for r in rows if r["golden"] == "mixed"]
print(f"\nMixed commits: net positive {sum(r['net'] > 0 for r in mixed)}, net negative {sum(r['net'] < 0 for r in mixed)}; "
      f"latched and net negative {sum(r['net'] < 0 and r['latched'] for r in mixed)}.")

print("\n## 2. Did the feedback point the same way as golden?\n")
print("| feedback (passing requirements) | golden net better | golden net worse | golden unchanged |")
print("|---|---|---|---|")
for lab, sel in (("rose", lambda r: r["dpass"] > 0), ("unchanged", lambda r: r["dpass"] == 0),
                 ("fell", lambda r: r["dpass"] < 0)):
    x = [r for r in rows if sel(r)]
    print(f"| {lab} ({len(x)}) | {sum(r['net'] > 0 for r in x)} | {sum(r['net'] < 0 for r in x)} | "
          f"{sum(r['net'] == 0 for r in x)} |")

print("\n## 3. When a commit broke behaviour that was right, what was the editor told?\n")
brk = [r for r in rows if r["cells_broken"] > 0]
cells = sum(r["cells_broken"] for r in brk)
told = [r for r in brk if r["told_broken"]]
print(f"- commits that broke cells: {len(brk)} of {len(rows)}; latched {sum(r['latched'] for r in brk)}")
print(f"- told some requirement BROKE: {len(told)}; told nothing broke: {len(brk) - len(told)}")
print(f"- broken cells in commits told nothing broke: {100 * sum(r['cells_broken'] for r in brk if not r['told_broken']) / max(1, cells):.0f}%")
print(f"- broken cells that LATCHED: {100 * sum(r['cells_broken'] for r in brk if r['latched']) / max(1, cells):.0f}%; "
      f"of those, told nothing broke: {100 * sum(r['cells_broken'] for r in brk if r['latched'] and not r['told_broken']) / max(1, sum(r['cells_broken'] for r in brk if r['latched'])):.0f}%")

print("\n## 4. Per job\n")
print("| job | commits counted | latched | latched improvements / mixed+ / mixed− / regressions / unchanged | "
      "rejected improvements / mixed+ / mixed− / regressions / unchanged |")
print("|---|---|---|---|---|")
for job in dict.fromkeys(r["job"] for r in rows):
    x = [r for r in rows if r["job"] == job]

    def cnt(lat):
        y = [r for r in x if r["latched"] == lat]
        return " / ".join(str(v) for v in (
            sum(r["golden"] == "improvement" for r in y), sum(r["golden"] == "mixed" and r["net"] > 0 for r in y),
            sum(r["golden"] == "mixed" and r["net"] <= 0 for r in y), sum(r["golden"] == "regression" for r in y),
            sum(r["golden"] == "unchanged" for r in y)))
    print(f"| {job} | {len(x)} | {sum(r['latched'] for r in x)} | {cnt(True)} | {cnt(False)} |")

(E / "FEEDBACK-AUDIT-SUMMARY.json").write_text(json.dumps({"counted": len(rows), "total": total, "skipped": skipped,
                                                          "rows": [{k: v for k, v in r.items() if k != "requirements"}
                                                                   for r in rows]}, indent=1) + "\n")
