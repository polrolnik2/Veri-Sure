"""Score re-authored checks against the HELD-OUT golden RTL.

Run AFTER the stage has frozen. Nothing here ever ran during authoring: the
golden verdict is the grade, and §4 is explicit that the control may not gate.

CONVERGENCE IS NOT "STOPS FAILING". A check that goes False -> None has stopped
convicting the golden design by ceasing to decide anything at all, which is #93's
failure mode -- un-exercising a requirement reading as progress. Those are
counted and named separately, never folded into the win column.
"""
import json, sys, collections
from pathlib import Path
sys.path.insert(0, "/home/user/Veri-Sure")
from specflow.refmodel.oracles import RequirementOracle
from specflow.refmodel.rtl_trace import decide_rtl, load_traces

S = Path("/tmp/claude-0/-home-user-Veri-Sure/12bb865e-7a51-5506-b55a-e5ac7cf72a4a/scratchpad")
name = sys.argv[1] if len(sys.argv) > 1 else "pilot"
EXP = S / "asrt" / name

art = json.load(open(EXP / "run/specflow/oracles.json"))
contract = json.load(open(EXP / "run/contract.json"))
base = json.load(open(S / "asrt/verdicts110.json"))["golden"]
tr = load_traces(S / "rtl_golden2/suite/results")

oracles, unseen = [], collections.Counter()
for o in art["oracles"]:
    kw = {k: o[k] for k in ("req_uid", "clause", "source", "tp_uids") if k in o}
    for tp in kw.get("tp_uids") or []:
        if tp not in tr:
            unseen[kw["req_uid"]] += 1
    oracles.append(RequirementOracle(**kw))

if unseen:
    print(f"NOTE: {sum(unseen.values())} tp_uid(s) across {len(unseen)} requirement(s) "
          f"have no golden trace -- staged testpoints minted during this run. "
          f"They abstain; `_worst` keeps a verdict from a testpoint that HAS a "
          f"trace, so this cannot manufacture a pass, only fail to reward one.")

now = {x.req_uid: x for x in decide_rtl(oracles, tr, contract)}
disp = art.get("dispositions") or {}

rows, tally = [], collections.Counter()
for u in sorted(now):
    was = base.get(u, {}).get("ok")
    got = now[u].ok
    if was is False and got is True:
        k = "CONVERGED   golden now passes it"
    elif was is False and got is None:
        k = "went SILENT  stopped deciding (not a win)"
    elif was is False and got is False:
        k = "unchanged    golden still convicted"
    elif was is True and got is False:
        k = "REGRESSED    was fine, now convicts golden"
    else:
        k = f"other        {was} -> {got}"
    tally[k] += 1
    rows.append((u, was, got, disp.get(u, "?"), k, (now[u].detail or "")[:60]))

print(f"\n{'req':<10}{'was':>7}{'now':>7}  {'disposition':<16}{'outcome':<42}detail")
for u, w, g, d, k, det in rows:
    print(f"{u:<10}{str(w):>7}{str(g):>7}  {d:<16}{k:<42}{det}")
print()
for k, n in tally.most_common():
    print(f"  {n:>3}  {k}")

n = len(rows)
conv = tally["CONVERGED   golden now passes it"]
silent = tally["went SILENT  stopped deciding (not a win)"]
print(f"\nof {n} re-authored: {conv} converged, {silent} went silent, "
      f"{tally['unchanged    golden still convicted']} unchanged")
(EXP / "score.json").write_text(json.dumps(
    {u: {"was": w, "now": g, "disposition": d, "outcome": k, "detail": det}
     for u, w, g, d, k, det in rows}, indent=1))
print(f"wrote {EXP/'score.json'}")
