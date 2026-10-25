"""Re-score with the STAGED testpoints' real traces overriding the collided ids."""
import json, sys, collections
from pathlib import Path
sys.path.insert(0, "/home/user/Veri-Sure")
from specflow.refmodel.oracles import RequirementOracle
from specflow.refmodel.rtl_trace import decide_rtl, load_traces

S = Path("/tmp/claude-0/-home-user-Veri-Sure/12bb865e-7a51-5506-b55a-e5ac7cf72a4a/scratchpad"); A = S/"asrt"
art = json.load(open(A/"full43/run/specflow/oracles.json"))
contract = json.load(open(A/"full43/run/contract.json"))
base = json.load(open(A/"verdicts110.json"))["golden"]
added = {tp for ids in art["stimulus_added"].values() for tp in ids}

tr = load_traces(S/"rtl_golden2/suite/results")
staged = load_traces(A/"staged_golden/suite/results")
missing = sorted(added - set(staged))
print(f"staged ids: {len(added)}   real traces recovered: {len(staged)}"
      f"   still missing: {missing or 'none'}")
if missing:
    print("  those keep c1's colliding trace and are reported as UNRELIABLE below")
tr.update(staged)                                    # staged wins on a collision

oracles = [RequirementOracle(**{k: o[k] for k in ("req_uid","clause","source","tp_uids") if k in o})
           for o in art["oracles"]]
now = {x.req_uid: x for x in decide_rtl(oracles, tr, contract)}

prev = json.load(open(A/"full43/score.json"))
touched = {u for u, ids in art["stimulus_added"].items()}
rows, tally, changed = [], collections.Counter(), []
for u in sorted(now):
    was, got = base.get(u, {}).get("ok"), now[u].ok
    k = ("CONVERGED" if was is False and got is True else
         "went SILENT" if was is False and got is None else
         "unchanged" if was is False and got is False else f"{was}->{got}")
    tally[k] += 1
    old = (prev.get(u, {}).get("outcome") or "").split("  ")[0].strip()
    if old and not k.startswith(old.split()[0]):
        changed.append((u, old, k))
    rows.append((u, k, u in touched))

print(f"\n{'req':<10}{'outcome':<14}staged?")
for u, k, t in rows:
    print(f"{u:<10}{k:<14}{'YES' if t else ''}")
print()
for k, n in tally.most_common():
    print(f"  {n:>3}  {k}")
print(f"\nCHANGED by using the real staged traces: {len(changed)}")
for u, old, new in changed:
    print(f"  {u}: {old} -> {new}")
