"""E4b: as blindness falls, does the accepted set get smaller AND tighter?

Ten spec-derived designs survive in docs/evidence, plus the known-good control
for audit. Zero model calls -- replays and set arithmetic only.
"""
import glob
import importlib.util
import itertools
import json
import os
import sys
sys.path.insert(0, "/home/user/Veri-Sure")
from specflow import variety as V
from specflow.refmodel.oracles import RequirementOracle, decide

OUT = ['cmd_ack', 'busy', 'al', 'dout', 'scl_o', 'scl_oen', 'sda_o', 'sda_oen']
CMD = {"NOP": 0, "START": 1, "STOP": 2, "WRITE": 4, "READ": 8}


def load(path):
    spec = importlib.util.spec_from_file_location(os.path.basename(path), path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m.Model


def stim(seq, *, clk_cnt=4, sda=1, scl=1, hold=6):
    """One testpoint: a command sequence, each held for `hold` edges."""
    rows = [{"nReset": 0, "rst": 1, "ena": 0, "cmd": 0, "din": 0,
             "clk_cnt": clk_cnt, "scl_i": scl, "sda_i": sda}] * 2
    out = list(rows)
    for name, din in seq:
        for _ in range(hold):
            out.append({"nReset": 1, "rst": 0, "ena": 1, "cmd": CMD[name],
                        "din": din, "clk_cnt": clk_cnt,
                        "scl_i": scl, "sda_i": sda})
    return out


TESTPOINTS = {
    "TP-start":   stim([("START", 0), ("NOP", 0)]),
    "TP-write":   stim([("START", 0), ("WRITE", 1), ("NOP", 0)]),
    "TP-read":    stim([("START", 0), ("READ", 0), ("NOP", 0)]),
    "TP-stop":    stim([("START", 0), ("WRITE", 1), ("STOP", 0)]),
    "TP-arb":     stim([("START", 0), ("WRITE", 1)], sda=0),
    "TP-slow":    stim([("START", 0), ("WRITE", 0)], clk_cnt=9, hold=10),
    "TP-nostart": stim([("WRITE", 1), ("NOP", 0)]),
}


def replay(Model, steps):
    m = Model()
    m.reset()
    rows = []
    for i, inp in enumerate(steps):
        try:
            outs = m.step(dict(inp))
        except Exception:
            return None
        rows.append({"inputs": dict(inp), "outputs": dict(outs), "edge": i})
    return rows


# ---- designs -------------------------------------------------------------
designs = {}
for p in sorted(glob.glob("docs/evidence/*-i2c.ref_model.py")):
    name = os.path.basename(p).split("-")[0]
    try:
        M = load(p)
    except Exception as e:
        print(f"  skip {name}: {e}")
        continue
    rows = {tp: replay(M, s) for tp, s in TESTPOINTS.items()}
    rows = {tp: r for tp, r in rows.items() if r}
    if len(rows) == len(TESTPOINTS):
        designs[name] = rows
    else:
        print(f"  skip {name}: ran {len(rows)}/{len(TESTPOINTS)} testpoints")

control = None
cp = "benchmarks/controls/i2c_master_bit_ctrl/ref_model.py"
if os.path.exists(cp):
    try:
        CM = load(cp)
        cr = {tp: replay(CM, s) for tp, s in TESTPOINTS.items()}
        if all(cr.values()):
            control = cr
    except Exception as e:
        print("  control unavailable:", e)

print(f"designs: {len(designs)} -> {sorted(designs)}")
print(f"control: {'yes' if control else 'NO -- audit column unavailable'}")

# ---- checks --------------------------------------------------------------
checks = {}
for art in ("affected23", "reauthor43"):
    b = json.load(open(f"docs/evidence/{art}-oracles.json"))
    for o in b["oracles"]:
        checks[f"{art}:{o['req_uid']}"] = RequirementOracle(
            req_uid=o["req_uid"], tp_uids=list(TESTPOINTS),
            clause=o.get("clause", ""), source=o["source"])

verdicts = {}
for cid, oracle in checks.items():
    per = {}
    for d, rows in designs.items():
        vals = []
        for tp in TESTPOINTS:
            r = decide(oracle, rows[tp])
            if r.ok is not None:
                vals.append(r.ok)
        per[d] = (False if any(v is False for v in vals)
                  else (True if vals else None))
    if any(v is not None for v in per.values()):
        verdicts[cid] = per
print(f"checks: {len(checks)} loaded, {len(verdicts)} decide on >=1 design")

# ---- audit ---------------------------------------------------------------
audit = set()
if control:
    for cid, oracle in checks.items():
        for tp in TESTPOINTS:
            r = decide(oracle, control[tp])
            if r.ok is False:
                audit.add(cid)
                break
print(f"checks convicting the control (audit): {len(audit)} of {len(verdicts)}")

# ---- cells ---------------------------------------------------------------
cells = V.cells(designs, OUT)
print(f"disagreement cells: {len(cells)} over {len(designs)} designs")
if not cells:
    sys.exit("no disagreement -- these designs are behaviourally identical here")


def classes(accepted):
    """Trace-equivalence classes among the accepted designs."""
    sig = {d: json.dumps([[r["outputs"] for r in designs[d][tp]]
                          for tp in sorted(TESTPOINTS)], sort_keys=True)
           for d in accepted}
    return len({sig[d] for d in accepted})


def diameter(accepted):
    """Max pairwise disagreement fraction -- how far from equivalence."""
    if len(accepted) < 2:
        return 0.0
    worst = 0.0
    for a, b in itertools.combinations(sorted(accepted), 2):
        diff = tot = 0
        for tp in TESTPOINTS:
            for ra, rb in zip(designs[a][tp], designs[b][tp]):
                for p in OUT:
                    tot += 1
                    if ra["outputs"].get(p) != rb["outputs"].get(p):
                        diff += 1
        worst = max(worst, diff / max(tot, 1))
    return worst


def accepted_by(chosen):
    return {d for d in designs
            if not any(verdicts[c].get(d) is False for c in chosen)}


# ---- the ladder: add checks greedily by blind cells closed ---------------
print(f"\n{'checks':>6} {'blind%':>7} {'audit':>6} {'accept':>7} "
      f"{'classes':>8} {'diameter':>9}")
chosen, rows_out = [], []
remaining = set(verdicts)
while True:
    b = V.blind(cells, {c: verdicts[c] for c in chosen})
    acc = accepted_by(chosen)
    rows_out.append((len(chosen), 100 * len(b) / len(cells),
                     len(set(chosen) & audit), len(acc),
                     classes(acc) if acc else 0, diameter(acc)))
    print(f"{len(chosen):>6} {100*len(b)/len(cells):>6.1f}% "
          f"{len(set(chosen)&audit):>6} {len(acc):>7} "
          f"{classes(acc) if acc else 0:>8} {diameter(acc):>8.3f}")
    if not b or not remaining:
        break
    best = max(remaining,
               key=lambda c: sum(1 for x in b if V.separates(x, verdicts[c])))
    gain = sum(1 for x in b if V.separates(x, verdicts[best]))
    if gain == 0:
        print(f"  (no remaining check closes any of {len(b)} blind cells; "
              f"{len(remaining)} unused)")
        break
    chosen.append(best)
    remaining.discard(best)

# ---- the same ladder at CONTROLLED AUDIT = 0 -----------------------------
#
# The uncontrolled ladder above reaches one class and diameter 0.000 -- and its
# FIRST check convicts the control, so the surviving class excludes the
# known-good design. That is over-constriction, not success. This arm answers
# the question the plan actually asked: at audit 0, does reducing blindness
# still constrict?
sound = {c for c in verdicts if c not in audit}
print(f"\nCONTROLLED AUDIT = 0: {len(sound)} of {len(verdicts)} checks spare "
      f"the control")
print(f"{'checks':>6} {'blind%':>7} {'accept':>7} {'classes':>8} "
      f"{'diameter':>9}")
chosen = []
remaining = set(sound)
while True:
    b = V.blind(cells, {c: verdicts[c] for c in chosen})
    acc = accepted_by(chosen)
    print(f"{len(chosen):>6} {100*len(b)/len(cells):>6.1f}% {len(acc):>7} "
          f"{classes(acc) if acc else 0:>8} {diameter(acc):>8.3f}")
    if not b or not remaining:
        break
    best = max(remaining,
               key=lambda c: sum(1 for x in b if V.separates(x, verdicts[c])))
    if sum(1 for x in b if V.separates(x, verdicts[best])) == 0:
        print(f"  (no SOUND check closes any of {len(b)} remaining blind "
              f"cells; {len(remaining)} unused)")
        break
    chosen.append(best)
    remaining.discard(best)

# ---- where the residue sits, and whether the stall is an artifact ---------
import random  # noqa: E402

sound = {c for c in verdicts if c not in audit}
resid = V.blind(cells, {c: verdicts[c] for c in sound})
print(f"\nRESIDUE AT AUDIT 0: {len(resid)} of {len(cells)} cells = "
      f"{100*len(resid)/len(cells):.1f}%")
print("  blind cells by port -- the authoring targets:")
for port_name, n in V.ranked(resid):
    tot = sum(1 for c in cells if c.port == port_name)
    print(f"    {port_name:9} {n:4} of {tot:4} blind ({100*n/tot:5.1f}%)")

# Greedy could be the binding constraint rather than the supply of sound
# checks. 200 random orderings say whether it is.
best = 1.0
for _ in range(200):
    chosen = []
    for c in random.sample(sorted(sound), len(sound)):
        b = V.blind(cells, {k: verdicts[k] for k in chosen})
        if any(V.separates(x, verdicts[c]) for x in b):
            chosen.append(c)
    best = min(best, len(V.blind(cells, {k: verdicts[k] for k in chosen}))
               / len(cells))
print(f"\n  best reachable by ANY of 200 orderings: {100*best:.1f}% "
      f"-- ordering is not the binding constraint")

allb = V.blind(cells, {c: verdicts[c] for c in verdicts})
print(f"\n  all {len(verdicts)} checks incl. the {len(audit)} convicting the "
      f"control: {100*len(allb)/len(cells):.1f}% blind")
print(f"  so the {len(audit)} UNSOUND checks are worth "
      f"{100*(len(resid)-len(allb))/len(cells):.1f} points of blindness")
