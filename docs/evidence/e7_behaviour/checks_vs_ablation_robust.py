"""checks_vs_ablation_robust.py -- does CHECKS-VS-ABLATION.md's verdict survive other metrics and assumptions?

The verdict: repairing a design against the shipped checks (`cfc`) does no better than generating
another one (the job's ablation, as in checks_vs_ablation.py). Each assumption behind it is varied
in turn:

  METRIC     every metric the harness records (metrics.py, latency.py): golden-graded on the union
             of the module's stimulus or the run's own, open or closed loop, exact or order-only,
             whole edges or per port, formal; and the golden-free ones
  STIMULUS   the pipeline's own testpoints vs random input sequences it did not write (random_stim.py)
  CODES      byte_ctrl with the header's command codes applied to every design (byte_ctrl_codes_pool.py)
  BASELINE   the ablation pool (a random fresh sample) vs the arm's own start (paired)
  AGGREGATE  mean over jobs, each module weighted equally, median, win rate against single samples
  OUTLIERS   leave one job out
  TEST       exact rank test. If repair were just one more fresh sample, the checks final's
             position among its job's n+1 designs would be uniform. Its wins (samples beaten, ties
             half) are summed over jobs and the null distribution is convolved exactly
  SELECTOR   which fresh sample to keep without golden: most shipped checks passed, most agreement
             with the run's reference model, or most agreement with the other samples (consensus)
  GUARD      repair, but keep the start when the final agrees less with the fresh samples than the
             start does (golden-free)
  COST       the editor's tokens against one generation's (counts only), and the best of k samples

Reads latency.json, RANDOM-STIM.json, BYTE-CTRL-CODES-POOL.json; ABLATION.json for generation tokens; the editor's usage.jsonl counts under
E7_RUNS when present. Writes docs/evidence/e7/CHECKS-VS-ABLATION-ROBUST.json.
"""

import itertools
import json
import os
import random
import statistics as st
from pathlib import Path

EQ = Path(os.environ.get("E7_BEHAVIOUR_WORK", "/tmp/e7_behaviour"))
RUNS = Path(os.environ.get("E7_RUNS", "/home/user/runs-cf"))
E = Path(__file__).resolve().parents[1] / "e7"
SH = {"i2c_master_bit_ctrl": "bit_ctrl", "i2c_master_byte_ctrl": "byte_ctrl",
      "or1200_dc_fsm": "dc_fsm", "or1200_sb": "sb"}
ABL = {"i2c_master_byte_ctrl": ("cfg", "acg1", "acg2", "acg3")}
ABL_DEFAULT = ("gen1", "gen2", "gen3", "r0")
START = {"i2c_master_byte_ctrl": "cfg"}
TOL = 1e-12
rng = random.Random(20261022)


def boot_ci(d, n=20000):
    m = sorted(st.mean(rng.choice(d) for _ in d) for _ in range(n))
    return m[int(0.025 * n)], m[int(0.975 * n)]


#: (key, label, golden-graded?)
MET = [
    ("g_edge", "edges equal to golden (all stimulus)", True),
    ("own_edge", "edges equal, run's own stimulus only", True),
    ("g_cell", "output-port traces equal", True),
    ("g_tp", "whole testpoints equal", True),
    ("g_order", "order-only testpoints, open loop", True),
    ("ol_port", "per-port order only, open loop", True),
    ("cl_exact", "whole testpoints equal, closed loop", True),
    ("cl_order", "order-only testpoints, closed loop", True),
    ("cl_port", "per-port order only, closed loop", True),
    ("golden_class", "equal to golden on every stimulus (0/1)", True),
    ("cl_golden_class", "equal to golden up to latency, closed loop (0/1)", True),
    ("formal", "ChipVerilog pass (0/1)", True),
    ("r_edge", "edges equal to golden, random stimulus", True),
    ("r_cell", "output-port traces equal, random stimulus", True),
    ("r_tp", "whole testpoints equal, random stimulus", True),
    ("ship", "shipped checks passed (the editor's objective)", False),
    ("ref", "edges equal to the run's reference model", False),
    ("peer", "edges equal to the fresh samples (consensus)", False),
]
SEL = [("ship", "most shipped checks"), ("ref", "most agreement with the reference model"),
       ("peer", "most agreement with the other samples")]

RS = json.loads((E / "RANDOM-STIM.json").read_text()) if (E / "RANDOM-STIM.json").is_file() else {}
R = {}
for r in json.loads((EQ / "latency.json").read_text()):
    r = dict(r)
    r.update(RS.get(r["module"], {}).get("designs", {}).get(f"{r['run']}.{r['kind']}", {}))
    r["formal"] = float(r["verdict"] == "pass")
    for k in ("golden_class", "cl_golden_class"):
        r[k] = float(bool(r[k]))
    R[(r["module"], r["run"], r["kind"])] = r
JOBS = sorted({(m, run) for (m, run, k) in R if k == "cfc"}, key=lambda j: (SH[j[0]], j[1]))
JOBS = [j for j in JOBS if all((j[0], j[1], k) in R for k in ABL.get(j[0], ABL_DEFAULT))]


def pool(m, run):
    return [R[(m, run, k)] for k in ABL.get(m, ABL_DEFAULT)]


def pt(v, sign=False):
    if v is None:
        return "-"
    return f"{100 * v:+.1f}" if sign else f"{100 * v:.1f}"


def wins(x, others):
    return sum((x > o + TOL) + 0.5 * (abs(x - o) <= TOL) for o in others)


def rank_p(jobs, k):
    """Exact two-sided p for the summed wins of cfc, under 'cfc is one more fresh sample'."""
    dist, obs = {0.0: 1.0}, 0.0
    for m, run in jobs:
        vals = [a[k] for a in pool(m, run)] + [R[(m, run, "cfc")][k]]
        obs += wins(vals[-1], vals[:-1])
        alt = [wins(v, vals[:i] + vals[i + 1:]) for i, v in enumerate(vals)]
        new = {}
        for s, p in dist.items():
            for w in alt:
                new[s + w] = new.get(s + w, 0.0) + p / len(alt)
        dist = new
    mu = sum(s * p for s, p in dist.items())
    return obs, mu, sum(p for s, p in dist.items() if abs(s - mu) >= abs(obs - mu) - 1e-9)


def mod_mean(per_job):
    by = {}
    for (m, _), v in per_job:
        by.setdefault(m, []).append(v)
    return st.mean(st.mean(v) for v in by.values())


out = {"jobs": [list(j) for j in JOBS], "metrics": {}, "selection": {}, "best_of_k": {}, "guard": {}, "cost": {}}

print(f"## 1. Every metric, {len(JOBS)} jobs\n")
print("Checks final minus the fresh-sample mean (`vs pool`), and minus its own start (`vs start`), in points. "
      "`wins` is the share of single fresh samples the final beats (ties half). `p` is the exact rank test.\n")
print("| metric | vs pool: mean | 95% bootstrap CI | module-weighted | median | jobs better / worse | "
      "leave-one-out range | vs start: mean | better / worse | wins | rank p |")
print("|---|---|---|---|---|---|---|---|---|---|---|")
for k, lab, _g in MET:
    rows = []
    for j in JOBS:
        c, a, s = (R[(*j, "cfc")].get(k), [x.get(k) for x in pool(*j)],
                   R[(*j, START.get(j[0], "r0"))].get(k))
        if c is None or any(v is None for v in a + [s]):
            continue
        others = [x.get(k) for kk, x in zip(ABL.get(j[0], ABL_DEFAULT), pool(*j)) if kk != START.get(j[0], "r0")]
        rows.append((j, c - st.mean(a), c - s, wins(c, a) / len(a), c - st.mean(others)))
    if not rows:
        continue
    jobs = [r[0] for r in rows]
    dp, ds, wr = [r[1] for r in rows], [r[2] for r in rows], [r[3] for r in rows]
    loo = [st.mean(dp[:i] + dp[i + 1:]) for i in range(len(dp))]
    obs, mu, p = rank_p(jobs, k)
    res = {"vs_pool_mean": st.mean(dp), "vs_pool_module_weighted": mod_mean(list(zip(jobs, dp))),
           "vs_pool_median": st.median(dp), "better": sum(d > TOL for d in dp), "worse": sum(d < -TOL for d in dp),
           "loo": [min(loo), max(loo)], "vs_start_mean": st.mean(ds), "start_better": sum(d > TOL for d in ds),
           "start_worse": sum(d < -TOL for d in ds), "win_rate": st.mean(wr), "rank_wins": obs, "rank_null": mu,
           "rank_p": p, "n": len(rows), "vs_others_mean": st.mean(r[4] for r in rows),
           "vs_pool_ci": boot_ci(dp), "vs_start_ci": boot_ci(ds)}
    out["metrics"][k] = res
    print(f"| {lab} | {pt(res['vs_pool_mean'], 1)} | [{pt(res['vs_pool_ci'][0], 1)}, {pt(res['vs_pool_ci'][1], 1)}] | "
          f"{pt(res['vs_pool_module_weighted'], 1)} | "
          f"{pt(res['vs_pool_median'], 1)} | {res['better']} / {res['worse']} | "
          f"{pt(min(loo), 1)} to {pt(max(loo), 1)} | {pt(res['vs_start_mean'], 1)} | "
          f"{res['start_better']} / {res['start_worse']} | {res['win_rate']:.2f} | {p:.2f} |")


def pick(cands, key):
    best = max(c[key] for c in cands)
    return [c for c in cands if abs(c[key] - best) <= TOL]


def guard(j):
    c, s = R[(*j, "cfc")], R[(*j, START.get(j[0], "r0"))]
    return c if c["peer"] >= s["peer"] - TOL else s


SCORE = ["g_edge", "own_edge", "g_tp", "cl_order", "cl_port", "golden_class", "formal", "r_edge"]
print("\n## 2. Which design to keep, without golden\n")
print("Mean over jobs of the kept design's score (%). Selectors pick among the fresh samples (ties: mean of "
      "the tied). The guard repairs, then keeps the start if the final agrees less with the fresh samples.\n")
print("| metric | repair | repair + consensus guard | random sample | " + " | ".join(f"by {lab}" for _, lab in SEL)
      + " | oracle |")
print("|---|" + "---|" * (5 + len(SEL)))
for k in SCORE:
    lab = next(lab for kk, lab, _ in MET if kk == k)
    col = {"repair": [], "guard": [], "random": [], "oracle": [], **{s: [] for s, _ in SEL}}
    for j in JOBS:
        a = pool(*j)
        if any(x.get(k) is None for x in a + [R[(*j, "cfc")]]):
            continue
        col["repair"].append(R[(*j, "cfc")][k])
        col["guard"].append(guard(j)[k])
        col["random"].append(st.mean(x[k] for x in a))
        col["oracle"].append(max(x[k] for x in a))
        for s, _ in SEL:
            col[s].append(st.mean(x[k] for x in pick(a, s)))
    out["selection"][k] = {c: st.mean(v) for c, v in col.items()}
    o = out["selection"][k]
    print(f"| {lab} | {pt(o['repair'])} | {pt(o['guard'])} | {pt(o['random'])} | "
          + " | ".join(pt(o[s]) for s, _ in SEL) + f" | {pt(o['oracle'])} |")
worst = min(JOBS, key=lambda j: R[(*j, "cfc")]["g_edge"] - st.mean(x["g_edge"] for x in pool(*j)))
rest = [j for j in JOBS if j != worst]
sel = {"repair": [R[(*j, "cfc")]["g_edge"] for j in rest], "guard": [guard(j)["g_edge"] for j in rest],
       "start": [R[(*j, START.get(j[0], "r0"))]["g_edge"] for j in rest],
       "random": [st.mean(x["g_edge"] for x in pool(*j)) for j in rest],
       "oracle": [max(x["g_edge"] for x in pool(*j)) for j in rest],
       **{s: [st.mean(x["g_edge"] for x in pick(pool(*j), s)) for j in rest] for s, _ in SEL}}
out["selection_without_worst"] = {"job": list(worst), **{k: st.mean(v) for k, v in sel.items()}}
out["start_mean"] = {k: st.mean(R[(*j, START.get(j[0], "r0"))][k] for j in JOBS) for k in SCORE}
print(f"\nWithout {SH[worst[0]]} {worst[1]} (repair's largest loss), edges equal to golden: "
      + ", ".join(f"{k} {pt(st.mean(v))}" for k, v in sel.items())
      + f". The starts themselves average {pt(out['start_mean']['g_edge'])} on all jobs.")
fired = [f"{SH[j[0]]} {j[1]}" for j in JOBS if guard(j) is not R[(*j, "cfc")]]
out["guard"] = {"kept_start": fired}
print(f"\nThe guard kept the start on: {', '.join(fired) or 'none'}.")

print("\n## 3. Best of k fresh samples (edges equal to golden, %)\n")
print("Expected score when k samples are drawn from the job's pool and one is kept by the selector "
      "(every k-subset equally likely). k = 1 is a random sample.\n")
N = len(ABL_DEFAULT)
print("| selector | " + " | ".join(f"k = {k}" for k in range(1, N + 1)) + " | repair |")
print("|---|" + "---|" * (N + 1))
for s, lab in SEL + [("g_edge", "golden (oracle)")]:
    row = []
    for kk in range(1, N + 1):
        vals = []
        for j in JOBS:
            a = pool(*j)
            vals.append(st.mean(st.mean(x["g_edge"] for x in pick(list(sub), s))
                                for sub in itertools.combinations(a, kk)))
        row.append(st.mean(vals))
    out["best_of_k"][s] = row
    print(f"| by {lab} | " + " | ".join(pt(v) for v in row) + f" | {pt(out['selection']['g_edge']['repair'])} |")

f = E / "BYTE-CTRL-CODES-POOL.json"
if f.is_file():
    C = {(r["run"], r["kind"]): r for r in json.loads(f.read_text())}
    print("\n## 4. byte_ctrl with the header's command codes in every design\n")
    print("| run | metric | as generated: pool min–max (mean) / checks final | codes fixed: pool min–max (mean) / "
          "checks final |")
    print("|---|---|---|---|")
    out["codes"] = {}
    for run in sorted({r for r, _ in C}):
        for k in ("g_edge", "own_edge", "g_tp"):
            a0 = [R[("i2c_master_byte_ctrl", run, kk)][k] for kk in ABL["i2c_master_byte_ctrl"]]
            a1 = [C[(run, kk)][k] for kk in ABL["i2c_master_byte_ctrl"]]
            c0, c1 = R[("i2c_master_byte_ctrl", run, "cfc")][k], C[(run, "cfc")][k]
            out["codes"].setdefault(run, {})[k] = {"pool": a1, "checks": c1, "pool_as_generated": a0,
                                                   "checks_as_generated": c0}
            print(f"| {run} | {k} | {pt(min(a0))}–{pt(max(a0))} ({pt(st.mean(a0))}) / {pt(c0)} | "
                  f"{pt(min(a1))}–{pt(max(a1))} ({pt(st.mean(a1))}) / {pt(c1)} |")

print("\n## 5. Cost\n")
gen = {}
for a in json.loads((E / "ABLATION.json").read_text()):
    u = a.get("usage") or {}
    if a["module"] not in ABL:
        gen.setdefault(a["module"], []).append((u.get("input", 0) - u.get("cached", 0), u.get("output", 0)))
#: byte_ctrl's like-for-like generations are the real-child ones (ABLATION.json's had a stand-in child)
for f in sorted(RUNS.glob("luna1*/editor-abl-child-gen*/i2c_master_byte_ctrl/usage.jsonl")):
    us = [json.loads(line) for line in f.read_text().splitlines()]
    gen.setdefault("i2c_master_byte_ctrl", []).append((sum(u["input"] - u["cached"] for u in us),
                                                       sum(u["output"] for u in us)))
print("Tokens, uncached input / output (thousands). A fresh sample is one generation; the editor's figure "
      "is its own calls (`usage.jsonl`), on top of the generation it starts from.\n")
print("| job | one generation (mean of the ablation) | the checks arm's editor | editor / generation (output) |")
print("|---|---|---|---|")
for m, run in JOBS:
    gi, go = (st.mean(x[i] for x in gen[m]) for i in (0, 1))
    f = RUNS / run / "editor-cf-checks" / m / "usage.jsonl"
    if not f.is_file():
        print(f"| {SH[m]} {run} | {gi / 1e3:.0f} / {go / 1e3:.0f} | not available | |")
        continue
    ei = eo = 0
    for line in f.read_text().splitlines():
        u = json.loads(line)
        ei += u.get("input", 0) - u.get("cached", 0)
        eo += u.get("output", 0)
    out["cost"][f"{m} {run}"] = {"gen_uncached_in": gi, "gen_out": go, "editor_uncached_in": ei, "editor_out": eo}
    print(f"| {SH[m]} {run} | {gi / 1e3:.0f} / {go / 1e3:.0f} | {ei / 1e3:.0f} / {eo / 1e3:.0f} | {eo / go:.0f}× |")

(E / "CHECKS-VS-ABLATION-ROBUST.json").write_text(json.dumps(out, indent=1) + "\n")
