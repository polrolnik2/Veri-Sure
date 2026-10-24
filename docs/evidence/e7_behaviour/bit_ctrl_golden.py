"""bit_ctrl_golden.py -- how much of bit_ctrl's low score is golden's, and does it change any verdict?

docs/evidence/e7/qualitative/i2c_master_bit_ctrl.md found two quirks of the reference (golden)
bit controller that every generated design reads differently:
  gB  golden never resets `dout`, and the harness runs testpoints back to back, so golden's `dout`
      at the start of a testpoint is whatever the previous one left. The spec's reset list does not
      name `dout`; all 20 designs and all 4 ref models reset it. gB = the reference with `dout`
      reset to 0 on nReset and rst.
  gC  golden resets the raw capture registers cSCL/cSDA to 00, all designs to 11 ("filtered
      SCL/SDA are initialized high"); with clk_cnt < 4 that makes a filter glitch after every
      reset. gC = gB with cSCL/cSDA reset to 11.
Both are built here from the reference by patching those lines only, and simulated on the same
harness as golden. Then every bit_ctrl verdict in the e7 evidence is rescored against all three:
the start and its peers, the audited commits of both arms (LATCH-OFFLINE), the commits the spec
judge decided offline (ARBITRATION-OFFLINE) and live (ARBITER-LIVE).
-> docs/evidence/e7/BIT-CTRL-GOLDEN.json, tables on stdout.
"""

import glob
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
_src = (HERE / "feedback_audit.py").read_text().split("\nout = {")[0]
FA = {"__file__": str(HERE / "feedback_audit.py"), "__name__": "feedback_audit"}
exec(compile(_src, str(HERE / "feedback_audit.py"), "exec"), FA)  # replay + simulator, no main
EQ = Path(os.environ.get("E7_BEHAVIOUR_WORK", "/tmp/e7_behaviour"))
RUNS = Path(os.environ.get("E7_RUNS", "/home/user/runs-cf"))
E = HERE.parent / "e7"
MOD = "i2c_master_bit_ctrl"
REF = (FA["DES"] / "i2c" / MOD / f"{MOD}.v").read_text()


sys.path.insert(0, str(HERE))
from golden_variants import bit_ctrl_corrected  # noqa: E402

gB, gC = bit_ctrl_corrected(REF)

contract = json.loads((EQ / "corpora" / "luna12" / MOD / "contract.json").read_text())
sim = FA["simulator"](MOD)
G = {"golden": json.loads((EQ / "out" / MOD / "golden.json").read_text()),
     "gB": sim(gB, contract), "gC": sim(gC, contract)}
outs = json.loads((EQ / "stim" / "luna12" / f"{MOD}.json").read_text())["outputs"]


def per_port(X, Y):
    """Cells where X and Y differ, per output (Y's X/Z values are don't-care)."""
    d = dict.fromkeys(outs, 0)
    for r in Y:
        for tp, y in Y[r].items():
            for i, row in enumerate(y):
                for k, v in enumerate(row):
                    if not FA["dc"](v) and i < len(X[r][tp]) and X[r][tp][i][k] != v:
                        d[outs[k]] += 1
    return {k: v for k, v in d.items() if v}


out = {"golden_vs_gB": per_port(G["gB"], G["golden"]), "gB_vs_gC": per_port(G["gC"], G["gB"])}
print("## The corrected goldens\n")
print(f"- golden vs gB, cells that differ per output: {out['golden_vs_gB']}  (only dout should)")
print(f"- gB vs gC: {out['gB_vs_gC']}")


def score(rtl):
    T = sim(rtl, contract)
    res = {}
    for name, g in G.items():
        c = FA["compare"](T, T, g)
        res[name] = (c["edge_after"], c["tp_after"])
    return res


print("\n## Designs, share of edges / testpoints equal to each golden (all runs' stimulus)\n")
print("| design | golden | gB | gC |\n|---|---|---|---|")
out["designs"] = {}
for name, path in [("luna12 start", E / "luna12" / "editor" / MOD / "rtl_generated.sv"),
                   *[(f"luna12 peer gen{k}", E / "luna12" / "ablation" / MOD / f"gen{k}" / "rtl.sv")
                     for k in (1, 2, 3)]]:  # unwrapped: the simulator wraps it itself
    s = score(path.read_text())
    out["designs"][name] = s
    print(f"| {name} | " + " | ".join(f"{100 * e:.1f}% / {100 * t:.1f}%" for e, t in s.values()) + " |")


def net(before, after):
    A, B = sim(before, contract), sim(after, contract)
    if A is None or B is None:
        return None
    return {n: (lambda c: c["cells_fixed"] - c["cells_broken"])(FA["compare"](A, B, g)) for n, g in G.items()}


def start_of(run):
    return (E / run / "editor" / MOD / "rtl_generated.sv").read_text()


def commits_of(run, log, traj):
    text = Path(log).read_text(errors="replace")
    return FA["replay"](start_of(run), [json.loads(x) for x in open(traj)], FA["log_records"](text, "input"),
                        FA["log_records"](text, "output"))[0]


# ---------------------------------------------------------------- audited commits, both arms
print("\n## Audited commits (LATCH-OFFLINE): golden's verdict against gB's and gC's\n")
out["audited"] = []
for arm, f in (("cf-checks", "LATCH-OFFLINE.json"), ("cf-model", "LATCH-OFFLINE-cf-model.json")):
    rows = [r for r in json.loads((E / f).read_text())["rows"] if r["job"].startswith("bit_ctrl")]
    for job in sorted({r["job"] for r in rows}):
        run = job.split()[1]
        log = sorted(glob.glob(str(RUNS / run / "results" / MOD / f"{arm}*" / "editor.log")))[0]
        cs = commits_of(run, log, RUNS / run / f"editor-{arm}" / MOD / "debug_trajectory.jsonl")
        for r in (r for r in rows if r["job"] == job):
            c = cs[r["commit"] - 1]
            n = net(c["before"], c["submitted"])
            if n:
                out["audited"].append({"arm": arm, "job": job, "commit": r["commit"], "dcons": r["dcons"],
                                       "latched": r["latched"], **n})


def sign(v):
    return (v > 0) - (v < 0)


A = out["audited"]
flips = [a for a in A if sign(a["golden"]) != sign(a["gC"])]
print(f"- {len(A)} commits; golden's direction differs from gB's on {sum(sign(a['golden']) != sign(a['gB']) for a in A)}, "
      f"from gC's on {len(flips)}")
for name in ("golden", "gB", "gC"):
    acc = [a for a in A if a["dcons"] > 1e-12]
    rej = [a for a in A if not a["dcons"] > 1e-12]
    print(f"- judged by {name}: CONSENSUS-ONLY keeps {sum(a[name] > 0 for a in acc)} better / "
          f"{sum(a[name] < 0 for a in acc)} worse, refuses {sum(a[name] > 0 for a in rej)} better / "
          f"{sum(a[name] < 0 for a in rej)} worse")
out["audited_direction_flips"] = len(flips)

# ---------------------------------------------------------------- commits the judge decided
print("\n## Commits the spec judge decided\n")
print("| commit | judge (variant 3) | golden net | gB net | gC net |\n|---|---|---|---|---|")
out["judged"] = []
v3 = {r["source"]: r for r in json.loads((E / "ARBITRATION-OFFLINE-v3.json").read_text())["commits"]}
for src, r in v3.items():
    if r["mod"] != MOD:
        continue
    arm, _, run, _, k = src.split()
    log = sorted(glob.glob(str(RUNS / run / "results" / MOD / f"{arm}*" / "editor.log")))[0]
    c = commits_of(run, log, RUNS / run / f"editor-{arm}" / MOD / "debug_trajectory.jsonl")[int(k) - 1]
    n = net(c["before"], c["submitted"])
    out["judged"].append({"source": src, "score": r["score"], **n})
    print(f"| offline {src} | {r['score']:+.2f} | {n['golden']:+d} | {n['gB']:+d} | {n['gC']:+d} |")
for tag in ("smokem6-cons-fv-arb", "smokem6-cons-fv"):
    log = RUNS / "luna12" / "results" / MOD / tag / "editor.log"
    if not log.is_file():
        continue
    text = log.read_text(errors="replace")
    res = [FA["result_json"](x).get("arbitration") for t, x in FA["log_records"](text, "output") if t == "commit"]
    for i, c in enumerate(commits_of("luna12", log, RUNS / "luna12" / f"editor-{tag}" / MOD / "debug_trajectory.jsonl")):
        n = net(c["before"], c["submitted"])
        a = res[i] if i < len(res) else None
        out["judged"].append({"source": f"live {tag} commit {i + 1}", "score": a and a.get("score"),
                              "latched": c["latched"], **(n or {})})
        if n:
            s = "—" if not a else f"{a['score']:+.2f}"
            print(f"| live {tag} commit {i + 1} ({'kept' if c['latched'] else 'refused'}) | {s} | "
                  f"{n['golden']:+d} | {n['gB']:+d} | {n['gC']:+d} |")

(E / "BIT-CTRL-GOLDEN.json").write_text(json.dumps(out, indent=1) + "\n")
