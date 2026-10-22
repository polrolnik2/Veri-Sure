"""checks_vs_ablation.py -- the checks-only repaired finals against generation-only designs.

The question is not "checks vs model feedback" but "is repairing against the shipped checks better
than just generating again?". For each rerun job the ABLATION is every generation-only design of
that corpus in the same environment:
  sb, dc_fsm, bit_ctrl   gen1..gen3 (ABLATION.json) and r0 (the original job's round-0 design,
                         which is also the checks arm's start)
  byte_ctrl              cfg (the real-child start) and acg1..acg3 (generation-only samples made
                         with the real child; the gen1..3 of ABLATION.json had a stand-in child
                         and are not comparable)
The treatment is `cfc`, the checks-only final. Golden-graded columns are scoring only.

Reported per job and pooled:
  - the ablation's range and mean, the checks final, and its rank among them (by edges equal);
  - selection without golden: repair (cfc) vs the ablation sample passing the most shipped checks
    (ties: mean of the tied) vs a random ablation sample (the mean);
  - spread: across a module's runs, the SD of one design per corpus -- cfc vs each ablation index.
Reads latency.json (metrics.py + latency.py); writes docs/evidence/e7/CHECKS-VS-ABLATION.json.
"""

import json
import os
import statistics as st
from pathlib import Path

EQ = Path(os.environ.get("E7_BEHAVIOUR_WORK", "/tmp/e7_behaviour"))
E = Path(__file__).resolve().parents[1] / "e7"
SH = {"i2c_master_bit_ctrl": "bit_ctrl", "i2c_master_byte_ctrl": "byte_ctrl",
      "or1200_dc_fsm": "dc_fsm", "or1200_sb": "sb"}
ABL = {"i2c_master_byte_ctrl": ("cfg", "acg1", "acg2", "acg3")}
ABL_DEFAULT = ("gen1", "gen2", "gen3", "r0")
KEYS = ("g_edge", "g_tp", "cl_order", "cl_port", "ship", "ref")

R = {(r["module"], r["run"], r["kind"]): r for r in json.loads((EQ / "latency.json").read_text())}
jobs = sorted({(m, run) for (m, run, k) in R if k == "cfc"}, key=lambda j: (SH[j[0]], j[1]))


def pct(v):
    return f"{100 * v:.1f}" if isinstance(v, (int, float)) else "-"


out = {"jobs": [], "modules": {}}
print("| job | ablation n | metric | ablation min–max (mean) | checks final | rank of checks (1 = best of n+1) |")
print("|---|---|---|---|---|---|")
for m, run in jobs:
    abl = [R[(m, run, k)] for k in ABL.get(m, ABL_DEFAULT) if (m, run, k) in R]
    c = R[(m, run, "cfc")]
    if not abl:
        continue
    job = {"module": m, "run": run, "n_ablation": len(abl), "checks": {}, "ablation": {}}
    for k in KEYS:
        vals = [a[k] for a in abl if isinstance(a.get(k), (int, float))]
        if not vals or not isinstance(c.get(k), (int, float)):
            continue
        rank = 1 + sum(v > c[k] + 1e-12 for v in vals)
        job["checks"][k], job["ablation"][k] = c[k], {"min": min(vals), "max": max(vals), "mean": st.mean(vals)}
        job.setdefault("rank", {})[k] = rank
        if k in ("g_edge", "g_tp", "cl_order", "ship", "ref"):
            print(f"| {SH[m]} {run} | {len(abl)} | {k} | {pct(min(vals))}–{pct(max(vals))} ({pct(st.mean(vals))}) "
                  f"| {pct(c[k])} | {rank} of {len(vals) + 1} |")
    best_ship = max(a["ship"] for a in abl)
    picked = [a for a in abl if abs(a["ship"] - best_ship) < 1e-12]
    job["selection"] = {"checks_repaired": c["g_edge"], "best_by_checks": st.mean(a["g_edge"] for a in picked),
                        "random": st.mean(a["g_edge"] for a in abl), "best_by_golden": max(a["g_edge"] for a in abl)}
    job["verdicts"] = {"checks": c["verdict"], "ablation": [a["verdict"] for a in abl]}
    job["classes"] = {"checks": c["class"], "ablation": [a["class"] for a in abl],
                      "checks_golden": c["golden_class"], "ablation_golden": sum(a["golden_class"] for a in abl)}
    out["jobs"].append(job)

print("\n**Selection without golden (edges equal to golden, %):**\n")
print("| job | repair against the checks | best ablation sample by shipped checks | random ablation sample | best ablation sample by golden (oracle) |")
print("|---|---|---|---|---|")
for j in out["jobs"]:
    s = j["selection"]
    print(f"| {SH[j['module']]} {j['run']} | {pct(s['checks_repaired'])} | {pct(s['best_by_checks'])} | {pct(s['random'])} | {pct(s['best_by_golden'])} |")

print("\n**Per module:**\n")
print("| module | jobs | metric | ablation mean | checks mean | jobs checks > ablation mean | checks above ablation max / below min |")
print("|---|---|---|---|---|---|---|")
for m in sorted({j["module"] for j in out["jobs"]}, key=lambda x: SH[x]):
    js = [j for j in out["jobs"] if j["module"] == m]
    mod = {}
    for k in ("g_edge", "g_tp", "cl_order", "ship", "ref"):
        a = st.mean(j["ablation"][k]["mean"] for j in js)
        c = st.mean(j["checks"][k] for j in js)
        above = sum(j["checks"][k] > j["ablation"][k]["mean"] + 1e-12 for j in js)
        top = sum(j["checks"][k] > j["ablation"][k]["max"] + 1e-12 for j in js)
        bot = sum(j["checks"][k] < j["ablation"][k]["min"] - 1e-12 for j in js)
        mod[k] = {"ablation_mean": a, "checks_mean": c, "above_mean": above, "above_max": top, "below_min": bot}
        print(f"| {SH[m]} | {len(js)} | {k} | {pct(a)} | {pct(c)} | {above} of {len(js)} | {top} / {bot} |")
    if len(js) >= 3:
        idx = ABL.get(m, ABL_DEFAULT)
        spread = {"checks": st.pstdev([j["checks"]["g_edge"] for j in js])}
        for k in idx:
            v = [R[(m, j["run"], k)]["g_edge"] for j in js if (m, j["run"], k) in R]
            if len(v) == len(js):
                spread[k] = st.pstdev(v)
        mod["spread_g_edge"] = spread
        print(f"| {SH[m]} | | spread of edges equal across runs (SD, points) | "
              + ", ".join(f"{k} {100 * v:.1f}" for k, v in spread.items() if k != "checks")
              + f" | {100 * spread['checks']:.1f} | | |")
    out["modules"][m] = mod

(E / "CHECKS-VS-ABLATION.json").write_text(json.dumps(out, indent=1) + "\n")
