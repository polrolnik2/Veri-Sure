"""Do the two instruments agree? RTL verdict vs population verdict, all 122.

If `decide_rtl` over a compiled-Verilog trace and `decide` over a Python
spec-derived replay were incommensurable, the cross-tab would be scattered --
in particular there would be many checks the RTL PASSES that no admissible
design passes, which is impossible if both are measuring the same property.
"""
import json
import sys
from pathlib import Path
sys.path.insert(0, "/home/user/Veri-Sure")
from specflow import oracles_stage as OS
from specflow import variety as V
from specflow.refmodel.compose import choose_base
from specflow.refmodel.oracle_gen import RequirementOracle
from specflow.refmodel.rtl_trace import decide_rtl, load_traces

E = Path("docs/evidence/e5run-full2")
R = Path("/tmp/claude-0/-home-user-Veri-Sure/12bb865e-7a51-5506-b55a-e5ac7cf72a4a/scratchpad/recheck_run")
contract = json.loads((R / "contract.json").read_text())
stim = json.loads((R / "stimulus.json").read_text())
sbt = {s["tp_uid"]: s["stimulus_steps"] for s in stim["testpoints"]}
o = json.loads((R / "oracles.json").read_text())
population = [p.read_text() for p in sorted((E / "population").glob("*.py"))]
held = {x["req_uid"]: RequirementOracle(
    req_uid=x["req_uid"], tp_uids=list(x["tp_uids"]), clause=x.get("clause", ""),
    source=x["source"]) for x in o["oracles"]}

traces = load_traces(R / "suite" / "results")
rtl = {r.req_uid: (None if r.broken else r.ok)
       for r in decide_rtl(list(held.values()), traces, contract,
                           transactional=True)}
print(f"RTL: {sum(1 for v in rtl.values() if v is True)} pass, "
      f"{sum(1 for v in rtl.values() if v is False)} FAIL, "
      f"{sum(1 for v in rtl.values() if v is None)} abstain", flush=True)

verdicts, _t, _o = OS._population_tables(held, population, contract, sbt,
                                         base=choose_base(contract),
                                         transactional=True)
refuted = set(V.refuted_by_the_population(verdicts))
cells = {}
for uid in held:
    per = verdicts.get(uid) or {}
    somepass = any(v is True for v in per.values())
    pop = "some design passes" if somepass else (
        "NO design passes" if per else "population undecided")
    r = {True: "RTL pass", False: "RTL FAIL", None: "RTL abstain"}[rtl.get(uid)]
    cells.setdefault((r, pop), []).append(uid)
print(f"\n{'':<13}{'some design passes':>22}{'NO design passes':>20}{'undecided':>12}")
for r in ("RTL pass", "RTL FAIL", "RTL abstain"):
    row = [len(cells.get((r, p), [])) for p in
           ("some design passes", "NO design passes", "population undecided")]
    print(f"{r:<13}{row[0]:>22}{row[1]:>20}{row[2]:>12}")
bad = cells.get(("RTL pass", "NO design passes"), [])
print(f"\nRTL passes but NO spec-derived design does: {len(bad)}")
if bad:
    print("  " + ", ".join(sorted(bad)[:20]))
