"""WHY A SET IS BLIND: it is not reach, it is teeth.

A check separates a pair of designs at a testpoint only when its verdicts there
DIFFER. Passing all seven separates nothing. Convicting all seven separates
nothing. Only a MIXED verdict does any work, so this counts them.

Run after a blindness figure that does not make sense, and before reaching for
more checks. On the run this was written for it settled the question in one
table: blindness 55.1% with NOT ONE blind cell at a testpoint no check reached
-- every testpoint carrying a cell had a median of 39 checks deciding on it --
and 86.1% of all (check, testpoint) decisions passing all seven designs.

    python docs/evidence/e4d_why_the_set_is_blind.py

Reads `docs/evidence/e5u` for the upstream and a completed oracle stage beside
it; zero model calls. The contract is rebuilt from the run's own probe table,
because the architect's file declares none and replaying against it makes every
probe-reading check abstain.
"""
import collections
import json
import sys
from pathlib import Path
sys.path.insert(0, "/home/user/Veri-Sure")

from specflow import oracles_stage as OS  # noqa: E402
from specflow.refmodel.compose import choose_base  # noqa: E402
from specflow.refmodel.oracle_gen import RequirementOracle  # noqa: E402

D = Path("/tmp/claude-0/-home-user-Veri-Sure/12bb865e-7a51-5506-b55a-e5ac7cf72a4a/scratchpad")
E = Path("docs/evidence/e5u")
contract = json.loads(Path(
    "benchmarks/baselines/i2c_master_bit_ctrl/arm_a/contract.json").read_text())
pr = json.loads((E/"probes.json").read_text())["probes"]
contract["io"] = list(contract["io"]) + [
    {"name": p["name"], "dir": "probe", "width": p.get("width",1)} for p in pr]
contract["probes"] = [p["name"] for p in pr]
stim = json.loads((E/"stimulus.json").read_text())
stimulus_by_tp = {s["tp_uid"]: s["stimulus_steps"] for s in stim["testpoints"]}
o = json.loads((D/"o1"/"specflow"/"oracles.json").read_text())
population = [p.read_text() for p in sorted((D/"o1"/"specflow"/"population").glob("*.py"))]
base = choose_base(contract)
held = {x["req_uid"]: RequirementOracle(
    req_uid=x["req_uid"], tp_uids=list(x["tp_uids"]), clause=x.get("clause",""),
    source=x["source"]) for x in o["oracles"]}
_v, by_tp, _o = OS._population_tables(held, population, contract,
                                      stimulus_by_tp, base=base, transactional=True)
hist = collections.Counter()
mixed_pairs = collections.Counter()
for uid, table in by_tp.items():
    for tp, col in table.items():
        n_false = sum(1 for v in col.values() if v is False)
        hist[(len(col), n_false)] += 1
        if 0 < n_false < len(col):
            mixed_pairs[uid] += 1
tot = sum(hist.values())
print(f"{tot} (check, testpoint) decisions over {len(held)} checks\n")
print(f"{'decided':>8}{'convicted':>11}{'count':>9}{'share':>8}")
for (d, f), n in sorted(hist.items(), key=lambda kv: -kv[1])[:12]:
    tag = "  <- MIXED, this is the only kind that separates" if 0 < f < d else ""
    print(f"{d:>8}{f:>11}{n:>9}{100*n/tot:>7.1f}%{tag}")
mixed = sum(n for (d, f), n in hist.items() if 0 < f < d)
print(f"\nMIXED decisions: {mixed} of {tot} = {100*mixed/tot:.1f}%")
print(f"checks that are EVER mixed: {len(mixed_pairs)} of {len(held)}")
top = mixed_pairs.most_common(5)
print("most discriminating checks:", [(u, n) for u, n in top])
