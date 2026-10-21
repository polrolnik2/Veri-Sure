"""latency_report.py -- the tables of LATENCY.md from latency.json."""

import json
import os
import statistics as st
from collections import Counter, defaultdict
from pathlib import Path

EQ = Path(os.environ.get("E7_BEHAVIOUR_WORK", "/tmp/e7_behaviour"))
R = json.loads((EQ / "latency.json").read_text())
MODS = ["fpu_exceptions", "i2c_master_bit_ctrl", "i2c_master_byte_ctrl", "or1200_dc_fsm", "or1200_sb"]
SH = dict(zip(MODS, ["fpu", "bit_ctrl", "byte_ctrl", "dc_fsm", "sb"]))


def pct(v):
    return "--" if v is None else f"{100 * v:.1f}%"


def rank(v):
    o = sorted(range(len(v)), key=lambda i: v[i])
    rk = [0.0] * len(v)
    i = 0
    while i < len(o):
        j = i
        while j + 1 < len(o) and v[o[j + 1]] == v[o[i]]:
            j += 1
        for k in range(i, j + 1):
            rk[o[k]] = (i + j) / 2
        i = j + 1
    return rk


def spearman(a, b):
    ra, rb = rank(a), rank(b)
    ma, mb = st.mean(ra), st.mean(rb)
    num = sum((x - ma) * (y - mb) for x, y in zip(ra, rb))
    den = (sum((x - ma) ** 2 for x in ra) * sum((y - mb) ** 2 for y in rb)) ** 0.5
    return num / den if den else None


print("## A. Closed-loop harness against the formal verdict\n")
print("| formal verdict | designs | cycle-exact on every testpoint | order-only on every testpoint |\n|---|---|---|---|")
for v in ("pass", "function_fail", "equivalence_error"):
    g = [r for r in R if r["verdict"] == v]
    print(f"| {v} | {len(g)} | {sum(r['cl_exact'] == 1 for r in g)} | {sum(r['cl_order'] == 1 for r in g)} |")

print("\n## B. How much is latency? Share of testpoints equal to golden\n")
print("| module | arm | n | open-loop, cycle-exact | closed-loop, cycle-exact | closed-loop, order-only | **latency only** | per-port order-only |")
print("|---|---|---|---|---|---|---|---|")
for m in MODS + [None]:
    for arm in ("generated", "repaired"):
        g = [r for r in R if (m is None or r["module"] == m) and r["arm"] == arm]
        f = {k: st.mean(r[k] for r in g) for k in ("g_tp", "cl_exact", "cl_order", "cl_port")}
        print(f"| {SH.get(m, '**all**')} | {arm} | {len(g)} | {pct(f['g_tp'])} | {pct(f['cl_exact'])} | "
              f"{pct(f['cl_order'])} | **{pct(f['cl_order'] - f['cl_exact'])}** | {pct(f['cl_port'])} |")

print("\n## C. Designs equal to golden on ALL the stimulus\n")
print("| module | designs | formal pass | cycle-exact (closed loop) | equal up to latency | best order-only share |\n|---|---|---|---|---|---|")
for m in MODS:
    g = [r for r in R if r["module"] == m]
    print(f"| {SH[m]} | {len(g)} | {sum(r['verdict'] == 'pass' for r in g)} | {sum(r['cl_exact'] == 1 for r in g)} | "
          f"{sum(r['cl_order'] == 1 for r in g)} | {pct(max(r['cl_order'] for r in g))} |")

print("\n## D. Distinct behaviours with latency factored out\n")
print("| module | arm | designs | distinct (cycle-exact) | distinct (modulo latency) | modulo latency, not golden |\n|---|---|---|---|---|---|")
for m in MODS:
    for arm in ("generated", "repaired", None):
        g = [r for r in R if r["module"] == m and (arm is None or r["arm"] == arm)]
        print(f"| {SH[m]} | {arm or 'both'} | {len(g)} | {len({r['class'] for r in g})} | {len({r['cl_class'] for r in g})} | "
              f"{len({r['cl_class'] for r in g if not r['cl_golden_class']})} |")

print("\n## E. Before and after repair, latency-independent (closed-loop order-only)\n")
by = defaultdict(dict)
for r in R:
    by[(r["module"], r["run"])][r["kind"]] = r
pairs = [(v["r0"], v["final"]) for k, v in sorted(by.items(), key=lambda kv: (MODS.index(kv[0][0]), kv[0][1])) if "r0" in v and "final" in v]
print("| corpus | order-only testpoints | per-port order-only | cycle-exact (closed loop) | shipped checks |\n|---|---|---|---|---|")
for b, a in pairs:
    print(f"| {b['run']} {SH[b['module']]} | {pct(b['cl_order'])} -> {pct(a['cl_order'])} | {pct(b['cl_port'])} -> {pct(a['cl_port'])} | "
          f"{pct(b['cl_exact'])} -> {pct(a['cl_exact'])} | {pct(b['ship'])} -> {pct(a['ship'])} |")
ex = [(b, a) for b, a in pairs if not (b["run"] == "luna13" and b["module"] == "or1200_sb")]
for k in ("cl_order", "cl_port", "cl_exact", "ship"):
    up = sum(a[k] > b[k] + 1e-12 for b, a in pairs)
    dn = sum(a[k] < b[k] - 1e-12 for b, a in pairs)
    print(f"- {k}: mean {pct(st.mean(b[k] for b, a in pairs))} -> {pct(st.mean(a[k] for b, a in pairs))} "
          f"(without luna13 sb {pct(st.mean(b[k] for b, a in ex))} -> {pct(st.mean(a[k] for b, a in ex))}); "
          f"up {up}, down {dn}, same {len(pairs) - up - dn} of {len(pairs)}")

print("\n## F. Do golden-free metrics track LATENCY-INDEPENDENT behaviour? (Spearman, within module)\n")
print("| module | n | shipped checks vs cycle-exact | shipped checks vs order-only | ref model vs order-only | peers vs order-only |\n|---|---|---|---|---|---|")
for m in MODS:
    g = [r for r in R if r["module"] == m and r["peer"] is not None]
    cells = [spearman([r["ship"] for r in g], [r["cl_exact"] for r in g])] + [
        spearman([r[k] for r in g], [r["cl_order"] for r in g]) for k in ("ship", "ref", "peer")]
    print(f"| {SH[m]} | {len(g)} | " + " | ".join("--" if c is None else f"{c:+.2f}" for c in cells) + " |")
print("\nSelection, scored on closed-loop order-only testpoints:\n")
print("| selection | mean order-only share | picks the golden-best |\n|---|---|---|")
sel, hit = defaultdict(list), Counter()
for v in by.values():
    P = [r for r in v.values() if r["arm"] == "generated"]
    best = max(r["cl_order"] for r in P)
    sel["random (mean of pool)"].append(st.mean(r["cl_order"] for r in P))
    for k, lab in (("ship", "by shipped checks"), ("ref", "by agreement with ref model"), ("peer", "by agreement with peers")):
        top = max(r[k] for r in P)
        pick = [r for r in P if r[k] == top]
        sel[lab].append(st.mean(r["cl_order"] for r in pick))
        hit[lab] += any(r["cl_order"] == best for r in pick)
    sel["golden-chosen best (NOT available in a run)"].append(best)
    if "final" in v:
        sel["repaired (editor final)"].append(v["final"]["cl_order"])
for lab, v in sel.items():
    print(f"| {lab} | {pct(st.mean(v))} | {hit[lab] if lab in hit else '--'} |")
