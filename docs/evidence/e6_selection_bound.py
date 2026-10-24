"""What is the BEST selection can do -- and it is a bound, not a rule.

Selection can only REMOVE checks, and removal moves the three columns in fixed
directions: span can only fall, blindness can only rise (a removed check is a
separation lost), audit can fall (a removed check can be one that convicted).
So the frontier is found by removing EXACTLY the checks that convict the
control and nothing else.

**THIS IS A DIAGNOSTIC AND MUST NEVER BE SHIPPED.** Choosing a ruleset by its
audit column is gating on the grade, which this project bars: it tunes the set
against a held-out answer and the resulting audit figure means nothing. It is
computed here to answer one question -- IS the target reachable by selection at
all -- and the answer is worth having whichever way it falls.

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

SRC, GOLD = Path(sys.argv[1]), Path(sys.argv[2])
oracles = json.loads((SRC / "oracles.json").read_text())["oracles"]
_n = json.loads((SRC / "normalized.json").read_text())
normalized = _n["normalized"] if isinstance(_n, dict) else _n
requirements = json.loads((SRC / "requirements.json").read_text())["requirements"]
_s = json.loads((SRC / "stimulus.json").read_text())
stim = _s["testpoints"] if isinstance(_s, dict) else _s
by_tp = {s["tp_uid"]: s.get("stimulus_steps") or [] for s in stim}
contract = json.loads((GOLD / "contract.json").read_text())
population = [p.read_text() for p in sorted((SRC / "population").glob("*.py"))]
traces = load_traces(GOLD / "suite" / "results")
seen = {n for t in traces.values() for e in (t.get("edges") or [])
        for n, v in (e.get("dut") or {}).items() if v is not None}
absent = tuple(n for n in declared_probes(contract) if n not in seen)


def verdicts_for(keep):
    held = [RequirementOracle(req_uid=x["req_uid"], tp_uids=list(x["tp_uids"]),
                              clause=x.get("clause", ""), source=x["source"])
            for x in keep]
    out: dict = {}
    for r in decide_rtl(held, traces, contract, transactional=True):
        if not r.broken and r.ok is not None:
            out.setdefault(r.req_uid, {})[r.tp_uid] = bool(r.ok)
    return out


def run(label, keep):
    v = verdicts_for(keep)
    card = score(oracles=keep, normalized=normalized, stimulus_by_tp=by_tp,
                 contract=contract, population=population,
                 requirements=requirements, audit_verdicts=v, audit_absent=absent)
    tgt = ("MET" if card.span > 0.90 else "no",
           "MET" if card.blindness < 0.20 else "no",
           "MET" if card.audit == 0 else "no")
    print(f"  {label:26} checks {len(keep):4}  SPAN {card.span:.4f} {tgt[0]:3}  "
          f"BLIND {card.blindness:.4f} {tgt[1]:3}  "
          f"AUDIT {card.control_convicted_by}/{card.control_judges} "
          f"= {card.audit:.4f} {tgt[2]}", flush=True)
    return card


base = verdicts_for(oracles)
convicting = {u for u, per in base.items() if any(v is False for v in per.values())}
print(f"checks convicting golden: {len(convicting)} -> {sorted(convicting)}\n")
print("target: span > 0.90, blindness < 0.20, audit = 0\n")
run("baseline", oracles)
run("minus the convicting", [x for x in oracles if x["req_uid"] not in convicting])
