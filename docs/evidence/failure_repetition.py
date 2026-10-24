"""Repetition, measured UNSCOPED -- because scoped it is structurally impossible.

h3's testplan is a strict partition: all 455 testpoints cover exactly one
requirement each. So two requirements never share evidence, and co-failure
computed over each oracle's OWN testpoints is identically zero for every pair --
a harness artifact wearing the costume of "no shared cause".

Deciding every oracle against every trace is what makes the question askable.
The reference answer is the six convictions that a filtered-bus substitution
clears: if repetition is a usable signal, those six should co-fail with each
other more than with the fourteen that the substitution does not clear.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, "/home/user/Veri-Sure")
from specflow.refmodel.oracles import RequirementOracle, decide   # noqa: E402
from specflow.refmodel.rtl_trace import rows_from, transactional_view  # noqa: E402

RUN = Path("/home/user/runs/h3-i2c/specflow")
RES = Path("/tmp/claude-0/-home-user-Veri-Sure/12bb865e-7a51-5506-b55a-e5ac7cf72a4a"
           "/scratchpad/h3_own2/suite/results")
CLEARED = {"REQ-0028", "REQ-0057", "REQ-0066", "REQ-0086", "REQ-0100", "REQ-0101"}

cache = {}
for f in sorted(RES.glob("*.trace.json")):
    t = json.loads(f.read_text())
    cache[t["tp_uid"]] = transactional_view(rows_from(t, side="dut"))
ALL = sorted(cache)

fails, fired = {}, {}
for spec in json.loads((RUN / "oracles.json").read_text())["oracles"]:
    req = spec["req_uid"]
    o = RequirementOracle(req_uid=req, clause=spec.get("clause", ""),
                          source=spec["source"], tp_uids=ALL)
    f_, d_ = set(), set()
    for tp in ALL:
        r = decide(o, cache[tp])
        if r.broken:
            continue
        if r.ok is not None:
            d_.add(tp)
        if r.ok is False:
            f_.add(tp)
    fails[req], fired[req] = f_, d_

conv = sorted(r for r, f in fails.items() if f)
print(f"oracles: {len(fails)}   convicting somewhere in the suite: {len(conv)}")
print(f"reference group (cleared by the filter substitution): {sorted(CLEARED)}")


def jac(a, b):
    return len(a & b) / len(a | b) if (a | b) else 0.0


def stats(sets, label):
    keys = sorted(sets)
    w = [jac(sets[a], sets[b]) for i, a in enumerate(keys) for b in keys[i + 1:]
         if a in CLEARED and b in CLEARED]
    x = [jac(sets[a], sets[b]) for i, a in enumerate(keys) for b in keys[i + 1:]
         if (a in CLEARED) != (b in CLEARED)]
    o = [jac(sets[a], sets[b]) for i, a in enumerate(keys) for b in keys[i + 1:]
         if a not in CLEARED and b not in CLEARED]
    def m(v):
        return sum(v) / len(v) if v else float("nan")
    print(f"\n{label}")
    print(f"  WITHIN the cleared six : {m(w):.3f}  (n={len(w)})")
    print(f"  ACROSS the boundary    : {m(x):.3f}  (n={len(x)})")
    print(f"  among the other {len(keys) - len(CLEARED & set(keys))}     "
          f": {m(o):.3f}  (n={len(o)})")
    return m(w), m(x)


cf = {r: fails[r] for r in conv}
w1, x1 = stats(cf, "co-FAILURE (testpoints where both convict)")
w2, x2 = stats({r: fired[r] for r in conv}, "co-FIRING (testpoints where both decide anything)")
print("\nrepetition is usable only if WITHIN clearly exceeds ACROSS.")
print(f"  co-failure  separation: {w1 - x1:+.3f}")
print(f"  co-firing   separation: {w2 - x2:+.3f}")


# Raw co-failure confounds two things: failing for the SAME REASON, and merely
# being exercised on the same testpoints. Condition on co-firing to separate
# them -- among the testpoints where BOTH oracles decide something, how often do
# both convict. That is the number a clustering heuristic would actually rest on.
print("\nco-failure CONDITIONED on co-firing  (|both fail| / |both fire|)")
keys = sorted(conv)


def cond(a, b):
    both = fired[a] & fired[b]
    return len(fails[a] & fails[b] & both) / len(both) if both else None


for label, pred in (("WITHIN the cleared six", lambda a, b: a in CLEARED and b in CLEARED),
                    ("ACROSS the boundary", lambda a, b: (a in CLEARED) != (b in CLEARED)),
                    ("among the other 30", lambda a, b: a not in CLEARED and b not in CLEARED)):
    vals = [v for i, a in enumerate(keys) for b in keys[i + 1:]
            if pred(a, b) and (v := cond(a, b)) is not None]
    m = sum(vals) / len(vals) if vals else float("nan")
    print(f"  {label:<24}: {m:.3f}  (n={len(vals)})")
