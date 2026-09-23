"""The triple for a stored run, with GOLDEN RTL as the audit control.

**NO MODEL CALLS.** Span and blindness come from `score` replaying the stored
design population in Python; audit comes from `decide_rtl` over traces a real
simulation already wrote. Both stages are ones this branch changed, and neither
needs the gateway -- which is what "run only from the stage you changed" buys.

The point is the DENOMINATOR. `full2` recorded `audit = 0.0` over 14 of 111
accepted checks, because its Python control exposes none of the 24 declared
probes and 97 of them abstain on it by construction. Golden RTL is judged on
far more of the set, so the column stops being a rate over the eighth that can
see the control at all.

Golden is RUN and never read.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, "/home/user/Veri-Sure")
from specflow.probes import declared_probes  # noqa: E402
from specflow.refmodel.oracle_gen import RequirementOracle  # noqa: E402
from specflow.refmodel.rtl_trace import decide_rtl, load_traces  # noqa: E402
from specflow.scorecard import score  # noqa: E402

SRC = Path(sys.argv[1] if len(sys.argv) > 1 else
           "/tmp/claude-0/-home-user-Veri-Sure/12bb865e-7a51-5506-b55a-e5ac7cf72a4a/scratchpad/full2/specflow")
GOLD = Path("/tmp/claude-0/-home-user-Veri-Sure/12bb865e-7a51-5506-b55a-e5ac7cf72a4a/scratchpad/recheck_run")

oracles = json.loads((SRC / "oracles.json").read_text())["oracles"]
_n = json.loads((SRC / "normalized.json").read_text())
normalized = _n["normalized"] if isinstance(_n, dict) else _n
requirements = json.loads((SRC / "requirements.json").read_text())["requirements"]
_s = json.loads((SRC / "stimulus.json").read_text())
stimulus = _s["testpoints"] if isinstance(_s, dict) else _s
contract = json.loads((GOLD / "contract.json").read_text())
population = [p.read_text() for p in sorted((SRC / "population").glob("*.py"))]
by_tp = {s["tp_uid"]: s.get("stimulus_steps") or [] for s in stimulus}
print(f"oracles {len(oracles)} | population {len(population)} "
      f"({len({p for p in population})} distinct) | testpoints {len(by_tp)}")

held = [RequirementOracle(req_uid=x["req_uid"], tp_uids=list(x["tp_uids"]),
                          clause=x.get("clause", ""), source=x["source"])
        for x in oracles]
verdicts: dict = {}
for r in decide_rtl(held, load_traces(GOLD / "suite" / "results"), contract,
                    transactional=True):
    if not r.broken and r.ok is not None:
        verdicts.setdefault(r.req_uid, {})[r.tp_uid] = bool(r.ok)
judged = sum(1 for v in verdicts.values() if v)
print(f"GOLDEN decides {judged} of {len(oracles)} check(s)")

# A raw trace keys the design side as `dut`, not `outputs` -- reading the
# wrong key makes EVERY probe look unexposed and fires the non-conformance
# note over all 24. The probe is exposed when some edge carries a non-None
# value for it; `None` is what the width guard and an absent signal both give.
_traces = load_traces(GOLD / "suite" / "results")
_seen = {n for t in _traces.values() for e in (t.get("edges") or [])
         for n, v in (e.get("dut") or {}).items() if v is not None}
absent = tuple(n for n in declared_probes(contract) if n not in _seen)
print(f"golden exposes {len(declared_probes(contract)) - len(absent)} of "
      f"{len(declared_probes(contract))} declared probe(s); absent: {absent}")

card = score(oracles=oracles, normalized=normalized, stimulus_by_tp=by_tp,
             contract=contract, population=population,
             requirements=requirements, audit_verdicts=verdicts,
             audit_absent=absent)
print()
print(f"  SPAN       {card.span:.4f}   ({card.trusted} trusted "
      f"of {card.requirements_behavioural} behavioural)")
print(f"  BLINDNESS  {card.blindness:.4f}   ({card.blind} of {card.cells} cells)")
print(f"  AUDIT      {card.control_convicted_by}/{card.control_judges} "
      f"= {card.audit:.4f}")
print(f"  population {card.population} | effective_size {card.effective_size}")
for n in card.notes:
    print(f"  note: {str(n)[:170]}")
