"""Are the 23 surviving failures STRUCTURAL or incidental? Zero model calls.

The discriminator is golden-free: replay each failing check against the seven
independently written spec-derived designs. A check some design passes is
positively satisfiable, so failing it is a real defect in this candidate.

**"NO DESIGN PASSES" IS NOT "UNSATISFIABLE", AND AN EARLIER VERSION OF THIS
FILE SAID IT WAS.** Refutation by a seven-member population is evidence of
over-strictness, not proof: `e6_commensurable.py` finds REQ-0072 and REQ-0118,
which the candidate RTL PASSES and no spec-derived design does. A real design
satisfied checks the whole population failed.

Nor does `audit = 0` rescue them. Every one of these checks reads a probe, the
control exposes none of the 24 declared probes, and so it ABSTAINS on all of
them -- audit was computed over the ~13 checks it could be judged on and says
nothing about these in either direction.
"""
import json
import sys
from pathlib import Path
sys.path.insert(0, "/home/user/Veri-Sure")
from specflow import oracles_stage as OS
from specflow import variety as V
from specflow.refmodel.compose import choose_base
from specflow.refmodel.oracle_gen import RequirementOracle

FAIL = sys.argv[1:] or []
E = Path("docs/evidence/e5run-full2")
R = Path("/tmp/claude-0/-home-user-Veri-Sure/12bb865e-7a51-5506-b55a-e5ac7cf72a4a/scratchpad/recheck_run")
contract = json.loads((R / "contract.json").read_text())
stim = json.loads((R / "stimulus.json").read_text())
sbt = {s["tp_uid"]: s["stimulus_steps"] for s in stim["testpoints"]}
o = json.loads((R / "oracles.json").read_text())
reqs = {r["uid"]: r for r in json.loads((R / "requirements.json").read_text())["requirements"]}
norm = {n["req_uid"]: n for n in json.loads((R / "normalized.json").read_text())["normalized"]}
population = [p.read_text() for p in sorted((E / "population").glob("*.py"))]
base = choose_base(contract)

held = {x["req_uid"]: RequirementOracle(
    req_uid=x["req_uid"], tp_uids=list(x["tp_uids"]), clause=x.get("clause", ""),
    source=x["source"]) for x in o["oracles"] if x["req_uid"] in FAIL}
print(f"{len(held)} of {len(FAIL)} failing checks found in the frozen set; "
      f"replaying against {len(population)} spec-derived designs", flush=True)
verdicts, by_tp, _ = OS._population_tables(held, population, contract, sbt,
                                           base=base, transactional=True)
refuted = set(V.refuted_by_the_population(verdicts))
print(f"\n{'uid':<10} {'kind':<12} {'designs pass/fail/abstain':<26} verdict")
struct, incid, silent = [], [], []
for uid in FAIL:
    per = verdicts.get(uid) or {}
    p = sum(1 for v in per.values() if v is True)
    f = sum(1 for v in per.values() if v is False)
    a = len(population) - p - f
    kind = str(reqs.get(uid, {}).get("unit_kind") or "?")
    if kind != "behavioural":
        tag, bucket = "NOT BEHAVIOURAL -- no module obligation", struct
    elif uid in refuted:
        tag, bucket = "refuted: no design in THIS population passes it", struct
    elif p == 0 and f == 0:
        tag, bucket = "never decides on the population", silent
    else:
        tag, bucket = f"incidental: {p} design(s) PASS it", incid
    bucket.append(uid)
    print(f"{uid:<10} {kind:<12} {f'{p} pass / {f} fail / {a} abstain':<26} {tag}")
print(f"\nNO POSITIVE EVIDENCE OF SATISFIABILITY {len(struct)}: {', '.join(struct)}")
print(f"INCIDENTAL {len(incid)}: {', '.join(incid)}")
print(f"UNDECIDED  {len(silent)}: {', '.join(silent)}")
