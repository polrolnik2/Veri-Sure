"""consistency.py -- are the before-repair and after-repair figures stable, and is either better?

Reads BEHAVIOUR.json (committed; no simulation needed). Four questions:
  1. SPREAD   how widely designs of each arm scatter, within a corpus and across reps
  2. PAIRED   the 15 jobs' before -> after change: mean, bootstrap CI, sign and exact Wilcoxon tests
  3. NULL     is repair's change bigger than what DRAWING ANOTHER DESIGN does? For each job the
              'resample' changes are (other generated design of that corpus) - (its round 0);
              repair is compared with them by a permutation test
  4. AGREE    do the behaviour metrics move together, and with the shipped-check score?
"""

import itertools
import json
import math
import random
import statistics as st
from pathlib import Path

E = Path(__file__).resolve().parent.parent / "e7"
R = json.loads((E / "BEHAVIOUR.json").read_text())
MODS = ["fpu_exceptions", "i2c_master_bit_ctrl", "i2c_master_byte_ctrl", "or1200_dc_fsm", "or1200_sb"]
SH = dict(zip(MODS, ["fpu", "bit_ctrl", "byte_ctrl", "dc_fsm", "sb"]))
MET = [("g_edge", "edges equal (open loop)"), ("g_tp", "testpoints equal (open loop)"),
       ("cl_order", "order-only testpoints (closed loop)"), ("cl_port", "per-port order-only (closed loop)"),
       ("ship", "shipped checks passed (in-run)")]
rng = random.Random(20261021)


def pp(v):
    return f"{100 * v:+.1f}" if v is not None else "--"


def p1(v):
    return f"{100 * v:.1f}"


def sign_p(d):
    d = [x for x in d if abs(x) > 1e-12]
    n, k = len(d), sum(x > 0 for x in d)
    tail = sum(math.comb(n, i) for i in range(0, min(k, n - k) + 1)) / 2 ** n
    return min(1.0, 2 * tail)


def wilcoxon_p(d):
    """Exact two-sided signed-rank p, zeros dropped, ties by average rank."""
    d = [x for x in d if abs(x) > 1e-12]
    a = sorted(range(len(d)), key=lambda i: abs(d[i]))
    rk = [0.0] * len(d)
    i = 0
    while i < len(a):
        j = i
        while j + 1 < len(a) and abs(abs(d[a[j + 1]]) - abs(d[a[i]])) < 1e-12:
            j += 1
        for k in range(i, j + 1):
            rk[a[k]] = (i + j) / 2 + 1
        i = j + 1
    w = sum(r for r, x in zip(rk, d) if x > 0)
    mid = sum(rk) / 2
    dev = abs(w - mid)
    hits = sum(1 for s in itertools.product((0, 1), repeat=len(d))
               if abs(sum(r for r, b in zip(rk, s) if b) - mid) >= dev - 1e-9)
    return hits / 2 ** len(d)


def boot_ci(d, n=20000):
    m = [st.mean(rng.choice(d) for _ in d) for _ in range(n)]
    m.sort()
    return m[int(0.025 * n)], m[int(0.975 * n)]


def perm_p(a, b, n=20000):
    """Two-sided permutation p for mean(a) - mean(b)."""
    obs = abs(st.mean(a) - st.mean(b))
    pool = a + b
    hits = 0
    for _ in range(n):
        rng.shuffle(pool)
        hits += abs(st.mean(pool[:len(a)]) - st.mean(pool[len(a):])) >= obs - 1e-12
    return hits / n


by = {}
for r in R:
    by.setdefault((r["module"], r["run"]), {})[r["kind"]] = r

print("## 1. Spread: how stable is each arm?\n")
print("Mean, standard deviation and range across designs, per module.\n")
for k, lab in MET[:3]:
    print(f"**{lab}**\n\n| module | generated: mean ± SD (range) | spread among one corpus's samples (mean SD) | "
          f"repaired: mean ± SD (range) | before repair, across reps | after repair, across reps |\n|---|---|---|---|---|---|")
    for m in MODS:
        g = [r[k] for r in R if r["module"] == m and r["arm"] == "generated"]
        f = [r[k] for r in R if r["module"] == m and r["arm"] == "repaired"]
        within = [st.pstdev([r[k] for r in v.values() if r["arm"] == "generated"])
                  for (mm, _), v in by.items() if mm == m]
        b0 = [v["r0"][k] for (mm, _), v in by.items() if mm == m and "r0" in v]
        print(f"| {SH[m]} | {p1(st.mean(g))} ± {p1(st.stdev(g))} ({p1(min(g))}–{p1(max(g))}) | {p1(st.mean(within))} | "
              f"{p1(st.mean(f))} ± {p1(st.stdev(f))} ({p1(min(f))}–{p1(max(f))}) | "
              f"SD {p1(st.stdev(b0)) if len(b0) > 1 else '--'} | SD {p1(st.stdev(f))} |")
    print()

pairs = [(v["r0"], v["final"]) for _, v in sorted(by.items(), key=lambda kv: (MODS.index(kv[0][0]), kv[0][1]))
         if "r0" in v and "final" in v]
print("## 2. Paired change, round 0 -> final (15 jobs)\n")
print("| metric | mean change (pts) | 95% bootstrap CI | median | up / down / same | sign test p | Wilcoxon p | "
      "without luna13 sb: mean, CI, Wilcoxon p |\n|---|---|---|---|---|---|---|---|")
for k, lab in MET:
    d = [a[k] - b[k] for b, a in pairs]
    dx = [a[k] - b[k] for b, a in pairs if not (b["run"] == "luna13" and b["module"] == "or1200_sb")]
    lo, hi = boot_ci(d)
    lox, hix = boot_ci(dx)
    up, dn = sum(x > 1e-12 for x in d), sum(x < -1e-12 for x in d)
    print(f"| {lab} | {pp(st.mean(d))} | [{pp(lo)}, {pp(hi)}] | {pp(st.median(d))} | {up} / {dn} / {len(d) - up - dn} | "
          f"{sign_p(d):.2f} | {wilcoxon_p(d):.3f} | {pp(st.mean(dx))}, [{pp(lox)}, {pp(hix)}], {wilcoxon_p(dx):.3f} |")

print("\n## 3. Repair against drawing another design\n")
print("Resample change = (another generated design of the same corpus) - (that job's round 0). "
      "Same jobs. The resample changes of one job share its round 0, so the permutation p is approximate.\n")


def versus(skip):
    print("| metric | repair: mean change | resample: mean change | repair: mean size of change | "
          "resample: mean size of change | repair better than resample (share of comparisons) | permutation p (means) |"
          "\n|---|---|---|---|---|---|---|")
    for k, lab in MET:
        rep, res, wins, tot = [], [], 0, 0
        for (m, run), v in by.items():
            if "r0" not in v or "final" not in v or (m, run) in skip:
                continue
            dr = v["final"][k] - v["r0"][k]
            rep.append(dr)
            for kk, g in v.items():
                if g["arm"] == "generated" and kk != "r0":
                    ds = g[k] - v["r0"][k]
                    res.append(ds)
                    tot += 1
                    wins += (dr > ds + 1e-12) + 0.5 * (abs(dr - ds) <= 1e-12)
        print(f"| {lab} | {pp(st.mean(rep))} | {pp(st.mean(res))} | {p1(st.mean(abs(x) for x in rep))} | "
              f"{p1(st.mean(abs(x) for x in res))} | {wins / tot:.2f} ({tot}) | {perm_p(rep, res):.3f} |")


print("**All 15 jobs**\n")
versus(set())
print("\n**Without luna13 sb**\n")
versus({("or1200_sb", "luna13")})

print("\n## 4. Do the metrics move together?\n")
beh = ["g_edge", "g_tp", "cl_order", "cl_port"]
agree = sum(1 for b, a in pairs if len({(a[k] > b[k] + 1e-12) - (a[k] < b[k] - 1e-12) for k in beh} - {0}) <= 1)
print(f"- jobs whose four behaviour metrics do not move in opposite directions: {agree} of {len(pairs)}")
for k in beh:
    ds = [a["ship"] - b["ship"] for b, a in pairs]
    db = [a[k] - b[k] for b, a in pairs]
    ra = sorted(range(len(ds)), key=lambda i: ds[i])
    rb = sorted(range(len(db)), key=lambda i: db[i])
    rka, rkb = [0] * len(ds), [0] * len(db)
    for pos, i in enumerate(ra):
        rka[i] = pos
    for pos, i in enumerate(rb):
        rkb[i] = pos
    ma, mb = st.mean(rka), st.mean(rkb)
    rho = sum((x - ma) * (y - mb) for x, y in zip(rka, rkb)) / math.sqrt(
        sum((x - ma) ** 2 for x in rka) * sum((y - mb) ** 2 for y in rkb))
    print(f"- Spearman(change in shipped checks, change in {k}) = {rho:+.2f}")

print("\n## 5. Is the spread of final scores tighter than the ablation's?\n")
print("Like for like: one design per corpus. The repaired arm (editor finals) against each ablation sample "
      "index (gen1, gen2, gen3), as SD across reps per module; then a pooled Brown-Forsythe test "
      "(|score - its own arm's median| / module SD; arm labels permuted within module).\n")


def bf(k, mods, n=20000):
    groups = []
    for m in mods:
        fin = [r[k] for r in R if r["module"] == m and r["kind"] == "final"]
        abl = [r[k] for r in R if r["module"] == m and r["kind"].startswith("gen")]
        groups.append((fin, abl, st.pstdev(fin + abl) or 1))

    def stat(gs):
        df = [abs(x - st.median(f)) / sd for f, _a, sd in gs for x in f]
        da = [abs(x - st.median(a)) / sd for _f, a, sd in gs for x in a]
        return st.mean(df), st.mean(da)

    of, oa = stat(groups)
    hits = 0
    for _ in range(n):
        gs = []
        for f, a, sd in groups:
            pool = f + a
            rng.shuffle(pool)
            gs.append((pool[:len(f)], pool[len(f):], sd))
        sf, sa = stat(gs)
        hits += abs(sf - sa) >= abs(of - oa) - 1e-12
    return of, oa, hits / n


for k, lab in [MET[4], MET[0], MET[2], MET[1]]:
    print(f"**{lab}** -- SD across reps\n\n| module | repaired | ablation gen1 / gen2 / gen3 | ratio repaired / mean ablation |\n|---|---|---|---|")
    for m in MODS:
        fin = st.stdev([r[k] for r in R if r["module"] == m and r["kind"] == "final"])
        per = [st.stdev([r[k] for r in R if r["module"] == m and r["kind"] == g]) for g in ("gen1", "gen2", "gen3")]
        print(f"| {SH[m]} | {p1(fin)} | {' / '.join(p1(x) for x in per)} | "
              f"{fin / st.mean(per):.2f} |" if st.mean(per) else f"| {SH[m]} | {p1(fin)} | -- | -- |")
    a, b = bf(k, MODS), bf(k, MODS[:4])
    print(f"\nBrown-Forsythe: repaired {a[0]:.2f} vs ablation {a[1]:.2f}, p {a[2]:.3f}; "
          f"without sb {b[0]:.2f} vs {b[1]:.2f}, p {b[2]:.3f}\n")
