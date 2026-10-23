"""random_stim.py MODULE -- golden agreement under a stimulus the pipeline did not write.

Every golden-graded figure elsewhere drives the designs with the pipeline's own stimulus (the
corpora's testpoints, realized against each run's reference model). This drives golden and the
checks-vs-ablation designs with random input sequences instead:
  - each testpoint starts with sim.py's per-testpoint reset; the resets are then held inactive;
  - an input that the pipeline's stimulus holds constant within most testpoints (prescale, enables)
    is drawn once per testpoint;
  - every other input takes a value drawn from the values it takes in the pipeline's stimulus, held
    for a geometric number of edges whose mean is that input's mean run length there;
  - a testpoint lasts 10 median run lengths (300 to 4000 edges), with fewer testpoints when long.
Only the values and each input's rate of change come from the pipeline's stimulus, not the order,
the timing or the combination of inputs. Golden X/Z samples
are don't-care, as in metrics.py. Outputs are compared edge by edge (open loop: the open-drain
lines are not wired back).
Needs sim.py's tb (EQ/work/<module>/tb.v) and r0 designs (EQ/designs).
-> EQ/rand_out/<module>/<design>.json (traces); docs/evidence/e7/RANDOM-STIM.json (scores only)
"""

import json
import os
import random
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, "/home/user/Veri-Sure")
sys.path.insert(0, "/home/user/Veri-Sure/benchmarks")
from run_chipverilog import child_sources, submodules  # noqa: E402
from specflow.ports import is_reset  # noqa: E402

EQ = Path(os.environ.get("E7_BEHAVIOUR_WORK", "/tmp/e7_behaviour"))
E = Path(__file__).resolve().parents[1] / "e7"
DES = Path("/home/user/Veri-Sure/benchmarks/chipverilog/Des")
SEED, EDGES = 20261022, 200000
CF_TAGS = {"cf-gen": "cfg", "cf-checks": "cfc", "abl-child-gen1": "acg1", "abl-child-gen2": "acg2",
           "abl-child-gen3": "acg3", "val-cons": "vc"}
mod = sys.argv[1]
task = next(p.parent for p in DES.rglob("description.txt") if p.parent.name == mod)
kids = [Path(p) for p in child_sources(submodules(task, mod))]
runs = [r for r in ("luna12", "luna13", "luna14") if (EQ / "stim" / r / f"{mod}.json").is_file()]
stims = [json.loads((EQ / "stim" / r / f"{mod}.json").read_text()) for r in runs]
S0 = stims[0]
clock, outs = S0["clock"], S0["outputs"]
ins = [n for n in S0["inputs"] if n != clock]


def designs():
    d = {"golden": [task / f"{mod}.v"]}
    for r in runs:
        for k in (1, 2, 3):
            f = E / r / "ablation" / mod / f"gen{k}" / "rtl_deliverable.sv"
            if f.is_file():
                d[f"{r}.gen{k}"] = [f]
        if (EQ / "designs" / r / mod / "r0.sv").is_file():
            d[f"{r}.r0"] = [EQ / "designs" / r / mod / "r0.sv"]
        for tag, key in CF_TAGS.items():
            f = E / r / f"editor-{tag}" / mod / "rtl_deliverable.sv"
            if f.is_file():
                d[f"{r}.{key}"] = [f]
    return d


def stimulus():
    rng = random.Random(f"{SEED}-{mod}")
    vals, const, runl = {n: [] for n in ins}, {n: 0 for n in ins}, {n: [] for n in ins}
    ntp = 0
    for s in stims:
        idx = {n: s["inputs"].index(n) for n in ins}
        for tp in s["tps"].values():
            rows = tp["rows"]
            if not rows:
                continue
            ntp += 1
            for n in ins:
                col = [int(r[idx[n]] or 0) for r in rows]
                vals[n] += col
                const[n] += len(set(col)) == 1
                runl[n].append(len(col) / (1 + sum(a != b for a, b in zip(col, col[1:]))))
    config = {n for n in ins if not is_reset(n) and const[n] >= 0.9 * ntp and len(set(vals[n])) > 1}
    hold = {n: sum(runl[n]) / len(runl[n]) for n in ins}
    free = sorted(hold[n] for n in ins if not is_reset(n) and n not in config)
    rows = int(min(4000, max(300, 10 * free[len(free) // 2])))
    tps = max(50, min(200, EDGES // rows))
    lines = []
    for _ in range(tps):
        lines.append("0")
        cur = {n: rng.choice(vals[n]) for n in ins}
        for n in ins:
            if is_reset(n):
                # inactive: the value the stimulus holds most often
                cur[n] = max(set(vals[n]), key=vals[n].count)
        for _ in range(rows):
            for n in ins:
                if not is_reset(n) and n not in config and rng.random() < 1 / hold[n]:
                    cur[n] = rng.choice(vals[n])
            lines.append("1 " + " ".join(format(cur[n], "x") for n in ins))
    p = EQ / "rand_stim" / f"{mod}.txt"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(lines) + "\n")
    return p, {"config_inputs": sorted(config), "tps": tps, "rows": rows,
               "hold": {n: round(hold[n], 1) for n in ins if not is_reset(n) and n not in config}}


def defines(files):
    return {m for f in files for m in re.findall(r"^\s*module\s+(\w+)", Path(f).read_text(), re.M)}


def sim(name, files, stim, work):
    libs = [k for k in kids if k.stem not in defines(files)]
    vvp = work / f"rand.{name}.vvp"
    c = subprocess.run(["iverilog", "-g2012", "-s", "tb", "-o", str(vvp), f"-I{task}", f"-I{task.parent}",
                        str(work / "tb.v"), *map(str, files), *map(str, libs)], capture_output=True, text=True)
    if c.returncode:
        return None
    o = work / f"rand.{name}.out"
    subprocess.run(["vvp", "-n", str(vvp), f"+in={stim}", f"+out={o}"], capture_output=True, text=True,
                   timeout=3600)
    tps, cur = [], None
    for line in o.read_text().splitlines():
        if line == "#":
            cur = []
            tps.append(cur)
        else:
            cur.append(line.split())
    o.unlink()
    vvp.unlink(missing_ok=True)
    return tps


def score(x, g):
    def eq(v, gv):
        return any(ch in gv for ch in "xXzZ") or v == gv
    e = et = t = c = ct = act = 0
    for a, b in zip(x, g):
        e += sum(all(eq(v, gv) for v, gv in zip(ra, rb)) for ra, rb in zip(a, b))
        et += max(len(a), len(b))
        t += len(a) == len(b) and all(all(eq(v, gv) for v, gv in zip(ra, rb)) for ra, rb in zip(a, b))
        for k in range(len(outs)):
            c += len(a) == len(b) and all(eq(ra[k], rb[k]) for ra, rb in zip(a, b))
            ct += 1
        act += sum(rb != pb for pb, rb in zip(b, b[1:]))
    return {"r_edge": e / et, "r_tp": t / len(g), "r_cell": c / ct}


def main():
    work = EQ / "work" / mod
    stim, shape = stimulus()
    out = EQ / "rand_out" / mod
    out.mkdir(parents=True, exist_ok=True)
    traces = {}
    for name, files in designs().items():
        tr = sim(name, files, stim, work)
        if tr is None:
            print(f"{mod} {name}: COMPILE ERROR", flush=True)
            continue
        (out / f"{name}.json").write_text(json.dumps(tr))
        traces[name] = tr
    G = traces.pop("golden")
    act = sum(sum(r != p for p, r in zip(tp, tp[1:])) for tp in G) / sum(len(tp) for tp in G)
    f = E / "RANDOM-STIM.json"
    res = json.loads(f.read_text()) if f.is_file() else {}
    res[mod] = {**shape, "seed": SEED, "golden_output_changes_per_edge": act,
                "designs": {n: score(x, G) for n, x in sorted(traces.items())}}
    f.write_text(json.dumps(res, indent=1, sort_keys=True) + "\n")
    print(f"{mod}: {len(traces)} designs, {shape['tps']} x {shape['rows']} edges; config inputs "
          f"{shape['config_inputs']}; golden outputs change on {100 * act:.1f}% of edges")


main()
