"""The phase question as an ABSTENTION, not as a choice of reading.

    e6_phase_abstain.py <corpus-dir> <golden-suite-dir>

`TRIPLE.md`'s phase rule advances the control's `sta_condition` and
`sto_condition` one edge and re-decides. It works -- audit 9/42 -> 1/40 on
`full2` -- and it has a defect that is worth stating plainly: **it picks a
reading.** The specification writes "sto_condition = sSDA & ~dSDA & sSCL", an
equation and not a schedule, so a design may offer the condition combinationally
or register it. Advancing the probe asserts that the registered reading is the
right one. Nothing in the specification says so.

The symmetric rule asserts neither:

    a check whose verdict on a testpoint FLIPS when one probe it reads is taken
    one edge earlier is asserting a schedule the requirement never stated. On
    that testpoint it is not evidence about the design, so it abstains.

`temporal.phase_sensitive` is that test and already ships: one probe at a time
(delaying every probe together preserves relative timing and finds nothing -- 20
checks flagged that way and none of the five the diagnosis named), licensed away
where the requirement does state a timing (`licenses_a_cycle_count`, the rule
`correspondence` already applies to cycle counts), and an abstention is never
counted as a flip.

This measures what that rule costs, beside what the choosing rule costs, so the
difference between "abstain" and "pick the later reading" is a number rather than
an argument.

Golden is RUN and never read.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, "/home/user/Veri-Sure")
from specflow.probes import declared_probes  # noqa: E402
from specflow.refmodel.oracle_gen import RequirementOracle  # noqa: E402
from specflow.refmodel.oracles import decide as decide_one  # noqa: E402
from specflow.refmodel.oracles import ports_read, transactional_view  # noqa: E402
from specflow.refmodel.rtl_trace import load_traces, rows_from  # noqa: E402
from specflow.refmodel.temporal import phase_sensitive  # noqa: E402
from specflow.scorecard import score  # noqa: E402

SRC, GOLD = Path(sys.argv[1]), Path(sys.argv[2])
blob = json.loads((SRC / "oracles.json").read_text())
oracles = blob["oracles"]
_n = json.loads((SRC / "normalized.json").read_text())
normalized = _n["normalized"] if isinstance(_n, dict) else _n
requirements = json.loads((SRC / "requirements.json").read_text())["requirements"]
text_of = {r["uid"]: str(r.get("text") or "") for r in requirements}
_s = json.loads((SRC / "stimulus.json").read_text())
stim = _s["testpoints"] if isinstance(_s, dict) else _s
by_tp = {s["tp_uid"]: s.get("stimulus_steps") or [] for s in stim}
contract = json.loads((GOLD / "contract.json").read_text())
population = [p.read_text() for p in sorted((SRC / "population").glob("*.py"))]
traces = load_traces(GOLD / "suite" / "results")
seen = {n for t in traces.values() for e in (t.get("edges") or [])
        for n, v in (e.get("dut") or {}).items() if v is not None}
probes = list(declared_probes(contract))
absent = tuple(n for n in probes if n not in seen)

held = [RequirementOracle(req_uid=x["req_uid"], tp_uids=list(x["tp_uids"]),
                          clause=x.get("clause", ""), source=x["source"])
        for x in oracles]

verdicts: dict = {}
flagged: dict = {}
for o in held:
    reads = ports_read(o, contract)
    #: Only the probes this check READS can move its verdict, and asking about
    #: the others costs a replay each for nothing. `phase_sensitive` replays the
    #: check once per probe.
    mine = [p for p in probes if p in reads]
    for tp, t in traces.items():
        rows = transactional_view(rows_from(t, side="dut"))
        try:
            r = decide_one(o, rows)
        except Exception:  # noqa: BLE001
            continue
        if r.broken or r.ok is None:
            continue
        #: **ASKED ONLY OF A CONVICTION, AND THE SCOPE IS THE REASON.** This
        #: driver computes the AUDIT column, where only convictions count. A
        #: PASS whose phase-sensitivity would flip it is equally not evidence,
        #: and it matters for BLINDNESS -- but blindness here comes from
        #: `score`'s own population replay, which this does not touch, so
        #: flagging passes would cost 50x the replays and change no number
        #: reported below. Stated rather than left as an optimisation, because
        #: "the rule was applied to convictions only" is a limit on the result.
        if mine and r.ok is False:
            hit = phase_sensitive(lambda rw, _o=o: decide_one(_o, rw), rows,
                                  mine, text_of.get(o.req_uid, ""))
            if hit:
                flagged.setdefault(o.req_uid, set()).update(hit)
                continue          # abstains on this testpoint
        verdicts.setdefault(o.req_uid, {})[tp] = bool(r.ok)

print(f"checks whose CONVICTION depends on a probe's SCHEDULE somewhere: "
      f"{len(flagged)} of {len(oracles)}")
for u in sorted(flagged):
    print(f"  {u}  on {sorted(flagged[u])}")

card = score(oracles=oracles, normalized=normalized, stimulus_by_tp=by_tp,
             contract=contract, population=population,
             requirements=requirements, audit_verdicts=verdicts,
             audit_absent=absent)
print("\nphase-sensitive testpoints ABSTAIN:")
print(f"  SPAN {card.span:.4f}  BLIND {card.blindness:.4f}  "
      f"AUDIT {card.control_convicted_by}/{card.control_judges} "
      f"= {card.audit:.4f}")
kind_of = {r["uid"]: str(r.get("unit_kind") or "?") for r in requirements}
left = sorted(u for u, d in verdicts.items() if not all(d.values()))
print(f"\nremaining convictions, enumerated directly: {len(left)}")
for u in left:
    where = sorted(t for t, ok in verdicts[u].items() if not ok)
    print(f"  {u} [{kind_of.get(u, '?')}] on {len(where)} testpoint(s): "
          f"{' '.join(where[:4])}{' ...' if len(where) > 4 else ''}")
