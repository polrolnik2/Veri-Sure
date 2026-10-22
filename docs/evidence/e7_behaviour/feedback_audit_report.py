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
import os
import re
import statistics as st
from pathlib import Path

E = Path(__file__).resolve().parents[1] / "e7"
SH = {"i2c_master_bit_ctrl": "bit_ctrl", "i2c_master_byte_ctrl": "byte_ctrl",
      "or1200_dc_fsm": "dc_fsm", "or1200_sb": "sb"}
A = json.loads((E / "FEEDBACK-AUDIT.json").read_text())
RUNS = Path(os.environ.get("E7_RUNS", "/home/user/runs-cf"))


def reads(run, mod):
    """Requirement -> the names its shipped check reads (spec outputs and probes)."""
    d = RUNS / run / mod
    return {o["req_uid"]: set(re.findall(r"""["'](\w+)["']""", o.get("source") or ""))
            for o in json.loads((d / "shipped.json").read_text())["oracles"]}


RD = {(j["module"], j["run"]): reads(j["run"], j["module"]) for j in A["jobs"]}


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
            told = c["requirements"]["broken"]
            watched = set().union(*[RD[(j["module"], j["run"])].get(q, set()) for q in told]) if told else set()
            pointed = sum(v for o, v in (c.get("port_broken") or {}).items() if o in watched)
            rows.append({**c, "job": f"{SH[j['module']]} {j['run']}", "golden": golden_class(c),
                         "broken_where_told": pointed,
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



def fisher_two_sided(a, b, c, d):
    """Exact two-sided p for the 2x2 table [[a, b], [c, d]]."""
    from math import comb
    n, r1, c1 = a + b + c + d, a + b, a + c

    def p(x):
        return comb(r1, x) * comb(n - r1, c1 - x) / comb(n, c1)
    obs = p(a)
    return min(1.0, sum(p(x) for x in range(max(0, c1 - (n - r1)), min(r1, c1) + 1) if p(x) <= obs + 1e-12))


rose_b = sum(r["dpass"] > 0 and r["net"] > 0 for r in rows)
rose_w = sum(r["dpass"] > 0 and r["net"] < 0 for r in rows)
fell_b = sum(r["dpass"] < 0 and r["net"] > 0 for r in rows)
fell_w = sum(r["dpass"] < 0 and r["net"] < 0 for r in rows)
print(f"\nRose vs fell, golden better vs worse: Fisher exact p = {fisher_two_sided(rose_b, rose_w, fell_b, fell_w):.2f}")
MAT = 0.0005  # half a tenth of a point of edges equal to golden
print("\nThe same, judging golden by edges equal (a change of at least 0.05 points counts):\n")
print("| feedback | edges better | edges worse | within ±0.05 |")
print("|---|---|---|---|")
for lab, sel in (("rose", lambda r: r["dpass"] > 0), ("unchanged", lambda r: r["dpass"] == 0),
                 ("fell", lambda r: r["dpass"] < 0)):
    x = [r for r in rows if sel(r)]
    print(f"| {lab} ({len(x)}) | {sum(r['dedge'] >= MAT for r in x)} | {sum(r['dedge'] <= -MAT for r in x)} | "
          f"{sum(abs(r['dedge']) < MAT for r in x)} |")
print("\nThe same, golden judged on the run's own stimulus only (what the shipped checks see), by cells:\n")
print("| feedback | golden net better | golden net worse | unchanged |")
print("|---|---|---|---|")
for lab, sel in (("rose", lambda r: r["dpass"] > 0), ("unchanged", lambda r: r["dpass"] == 0),
                 ("fell", lambda r: r["dpass"] < 0)):
    x = [r for r in rows if sel(r)]
    nets = [r["own"]["cells_fixed"] - r["own"]["cells_broken"] for r in x]
    print(f"| {lab} ({len(x)}) | {sum(n > 0 for n in nets)} | {sum(n < 0 for n in nets)} | {sum(n == 0 for n in nets)} |")
ob = sum(r["dpass"] > 0 and r["own"]["cells_fixed"] > r["own"]["cells_broken"] for r in rows)
ow = sum(r["dpass"] > 0 and r["own"]["cells_fixed"] < r["own"]["cells_broken"] for r in rows)
fb = sum(r["dpass"] < 0 and r["own"]["cells_fixed"] > r["own"]["cells_broken"] for r in rows)
fw = sum(r["dpass"] < 0 and r["own"]["cells_fixed"] < r["own"]["cells_broken"] for r in rows)
print(f"\nFisher exact p (own stimulus) = {fisher_two_sided(ob, ow, fb, fw):.2f}")
print("\nBy module (passing rose / fell -> golden net better : worse):\n")
for m in ("bit_ctrl", "byte_ctrl", "dc_fsm", "sb"):
    x = [r for r in rows if r["job"].startswith(m)]
    if x:
        print(f"- {m}: {len(x)} commits; rose -> {sum(r['dpass'] > 0 and r['net'] > 0 for r in x)} : "
              f"{sum(r['dpass'] > 0 and r['net'] < 0 for r in x)}; fell -> {sum(r['dpass'] < 0 and r['net'] > 0 for r in x)} : "
              f"{sum(r['dpass'] < 0 and r['net'] < 0 for r in x)}")

print("\n## 3. When a commit broke behaviour that was right, what was the editor told?\n")
brk = [r for r in rows if r["cells_broken"] > 0]
cells = sum(r["cells_broken"] for r in brk)
told = [r for r in brk if r["told_broken"]]
print(f"- commits that broke cells: {len(brk)} of {len(rows)}; latched {sum(r['latched'] for r in brk)}")
print(f"- told some requirement BROKE: {len(told)}; told nothing broke: {len(brk) - len(told)}")
print(f"- broken cells in commits told nothing broke: {100 * sum(r['cells_broken'] for r in brk if not r['told_broken']) / max(1, cells):.0f}%")
print(f"- broken cells that LATCHED: {100 * sum(r['cells_broken'] for r in brk if r['latched']) / max(1, cells):.0f}%; "
      f"of those, told nothing broke: {100 * sum(r['cells_broken'] for r in brk if r['latched'] and not r['told_broken']) / max(1, sum(r['cells_broken'] for r in brk if r['latched'])):.0f}%")

tb = [r for r in brk if r["told_broken"]]
print(f"- in commits told some requirement BROKE, share of broken cells on an output that a reported "
      f"requirement's check reads: {100 * sum(r['broken_where_told'] for r in tb) / max(1, sum(r['cells_broken'] for r in tb)):.0f}%")
lb = [r for r in brk if r["latched"]]
print(f"- in LATCHED commits, broken cells on an output no reported-broken requirement reads: "
      f"{100 * sum(r['cells_broken'] - r['broken_where_told'] for r in lb) / max(1, sum(r['cells_broken'] for r in lb)):.0f}%")
print(f"- latched commits that broke cells: {len(lb)}; of these told nothing broke: {sum(not r['told_broken'] for r in lb)}")

lat = [r for r in rows if r["latched"]]
rej = [r for r in rows if not r["latched"]]


def pts(x, sign):
    return 100 * sum(r["dedge"] for r in x if (r["dedge"] > 0 if sign > 0 else r["dedge"] < 0))


print(f"\nIn points of edges equal to golden, summed over commits: the gate accepted {pts(lat, 1):+.2f} of gains and "
      f"{pts(lat, -1):+.2f} of losses, and rejected {pts(rej, 1):+.2f} of gains and {pts(rej, -1):+.2f} of losses.")
mx = sorted(r["cells_broken"] / (r["cells_fixed"] + r["cells_broken"]) for r in rows if r["golden"] == "mixed")
ch = [r for r in rows if r["golden"] != "unchanged"]
print(f"Commits that changed any output: {len(ch)}; of these broke something that was right: "
      f"{sum(r['cells_broken'] > 0 for r in ch)}. In mixed commits, breaks are a median "
      f"{100 * st.median(mx):.0f}% of the changed cells (IQR {100 * mx[len(mx) // 4]:.0f}–{100 * mx[3 * len(mx) // 4]:.0f}%).")

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
