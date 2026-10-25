import json
import statistics as st
from collections import Counter, defaultdict
import os
from pathlib import Path

#: Working tree (stimulus, traces, metrics): large and regenerable, so outside the repo.
EQ = Path(os.environ.get("E7_BEHAVIOUR_WORK", "/tmp/e7_behaviour"))
R = json.loads((EQ / "metrics.json").read_text())
MODS = [
    "fpu_exceptions",
    "i2c_master_bit_ctrl",
    "i2c_master_byte_ctrl",
    "or1200_dc_fsm",
    "or1200_sb",
]
SH = {
    "fpu_exceptions": "fpu",
    "i2c_master_bit_ctrl": "bit_ctrl",
    "i2c_master_byte_ctrl": "byte_ctrl",
    "or1200_dc_fsm": "dc_fsm",
    "or1200_sb": "sb",
}
def pct(v):
    return "--" if v is None else f"{100 * v:.1f}%"
print("## 1. Harness against the formal verdict\n")
print(
    "| formal verdict | trace = golden on all stimulus | trace differs |\n|---|---|---|"
)
x = Counter((r["verdict"], r["golden_class"]) for r in R)
for v in ("pass", "function_fail", "equivalence_error"):
    print(f"| {v} | {x[(v, True)]} | {x[(v, False)]} |")


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
    if len(a) < 3:
        return None
    ra, rb = rank(a), rank(b)
    ma, mb = st.mean(ra), st.mean(rb)
    num = sum((x - ma) * (y - mb) for x, y in zip(ra, rb))
    den = (sum((x - ma) ** 2 for x in ra) * sum((y - mb) ** 2 for y in rb)) ** 0.5
    return num / den if den else None


print("\n## 2. Distinct behaviours NOT equivalent to golden (on the stimulus)\n")
print(
    "| corpus | generated designs | distinct behaviours | not golden | repaired: golden? | repaired same as a generated one? |\n|---|---|---|---|---|---|"
)
by = defaultdict(list)
for r in R:
    by[(r["module"], r["run"])].append(r)
for m in MODS:
    for run in ("luna12", "luna13", "luna14", "luna15"):
        g = [r for r in by.get((m, run), []) if r["arm"] == "generated"]
        f = [r for r in by.get((m, run), []) if r["arm"] == "repaired"]
        if not g:
            continue
        cg = {r["class"] for r in g}
        ng = {r["class"] for r in g if not r["golden_class"]}
        fr = f[0] if f else None
        print(
            f"| {run} {SH[m]} | {len(g)} | {len(cg)} | {len(ng)} | {'yes' if fr and fr['golden_class'] else 'no'} | {'yes' if fr and fr['class'] in cg else 'no'} |"
        )
print(
    "\n| module | arm | designs | distinct behaviours | not golden | golden-equivalent designs |\n|---|---|---|---|---|---|"
)
for m in MODS:
    for arm in ("generated", "repaired"):
        g = [r for r in R if r["module"] == m and r["arm"] == arm]
        print(
            f"| {SH[m]} | {arm} | {len(g)} | {len({r['class'] for r in g})} | {len({r['class'] for r in g if not r['golden_class']})} | {sum(r['golden_class'] for r in g)} |"
        )
    a = [r for r in R if r["module"] == m]
    print(
        f"| {SH[m]} | both | {len(a)} | {len({r['class'] for r in a})} | {len({r['class'] for r in a if not r['golden_class']})} | {sum(r['golden_class'] for r in a)} |"
    )

print("\n## 3. Partial equivalence to golden (union stimulus, golden-graded)\n")
print(
    "| module | arm | n | edges equal | testpoints equal | port traces equal | order-only equal |\n|---|---|---|---|---|---|---|"
)
for m in MODS + [None]:
    for arm in ("generated", "repaired"):
        g = [r for r in R if (m is None or r["module"] == m) and r["arm"] == arm]
        print(
            f"| {SH.get(m, '**all**')} | {arm} | {len(g)} | "
            + " | ".join(
                pct(st.mean(r[f"g_{k}"] for r in g))
                for k in ("edge", "tp", "cell", "order")
            )
            + " |"
        )
print("\n### Before and after repair, same job (editor round 0 -> final)\n")
print(
    "| corpus | edges | testpoints | port traces | order-only | shipped checks |\n|---|---|---|---|---|---|"
)
pairs = []
for (m, run), rs in sorted(by.items(), key=lambda kv: (MODS.index(kv[0][0]), kv[0][1])):
    b = next((r for r in rs if r["kind"] == "r0"), None)
    a = next((r for r in rs if r["kind"] == "final"), None)
    if not (a and b):
        continue
    pairs.append((b, a))
    def f(k):
        return f"{pct(b[k])} -> {pct(a[k])}"
    print(
        f"| {run} {SH[m]} | {f('g_edge')} | {f('g_tp')} | {f('g_cell')} | {f('g_order')} | {f('ship')} |"
    )
for k in ("g_edge", "g_tp", "g_cell", "g_order", "ship"):
    up = sum(a[k] > b[k] + 1e-12 for b, a in pairs)
    dn = sum(a[k] < b[k] - 1e-12 for b, a in pairs)
    print(
        f"{k}: mean {pct(st.mean(b[k] for b, a in pairs))} -> {pct(st.mean(a[k] for b, a in pairs))}; up {up}, down {dn}, same {len(pairs) - up - dn} of {len(pairs)}"
    )

print(
    "\n## 4. Do golden-free metrics track golden? (Spearman vs edges-equal, within module)\n"
)
print(
    "| module | n | shipped checks | agreement with run's ref model | agreement with peer designs |\n|---|---|---|---|---|"
)
rhos = defaultdict(list)
for m in MODS:
    g = [r for r in R if r["module"] == m and r["peer"] is not None]
    cells = []
    for k in ("ship", "ref", "peer"):
        rho = spearman([r[k] for r in g], [r["g_edge"] for r in g])
        rhos[k].append(rho)
        cells.append("--" if rho is None else f"{rho:+.2f}")
    print(f"| {SH[m]} | {len(g)} | " + " | ".join(cells) + " |")

print("\n## 5. Picking one generated design per corpus without golden\n")
print(
    "Pool: the corpus's generated designs (3 samples + the editor's round 0). Score: golden edges-equal, union stimulus.\n"
)
sel = defaultdict(list)
hit = Counter()
for (m, run), rs in by.items():
    P = [r for r in rs if r["arm"] == "generated"]
    fin = next((r for r in rs if r["kind"] == "final"), None)
    best = max(r["g_edge"] for r in P)
    sel["random (mean of pool)"].append(st.mean(r["g_edge"] for r in P))
    for k, lab in (
        ("ship", "by shipped checks"),
        ("ref", "by agreement with ref model"),
        ("peer", "by agreement with peers"),
    ):
        top = max(r[k] for r in P)
        pick = [r for r in P if r[k] == top]
        sel[lab].append(st.mean(r["g_edge"] for r in pick))
        hit[lab] += any(r["g_edge"] == best for r in pick)
    sel["golden-chosen best (NOT available in a run)"].append(best)
    if fin:
        sel["repaired (editor final)"].append(fin["g_edge"])
print(
    "| selection | corpora | mean edges equal to golden | picks the golden-best |\n|---|---|---|---|"
)
for lab, v in sel.items():
    print(
        f"| {lab} | {len(v)} | {pct(st.mean(v))} | {hit[lab] if lab in hit else '--'} |"
    )
