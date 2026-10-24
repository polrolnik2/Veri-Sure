"""Does applying this branch's DESIGN-FREE rules move the triple toward target?

Four configurations of the same corpus, scored the same way, with GOLDEN RTL as
the audit control. The rules are screens over the check SOURCE and over a
witness trace -- no design population, no control, no golden -- so applying them
is not gating on the grade.

    baseline          every accepted check
    -unbounded        minus `throughout`/`stable`/`never` over `until=TO_END`
    -phase            minus checks whose verdict depends on a probe's SCHEDULE
                      where the requirement states no timing
    -both

A control may REJECT an oracle. It may never REPAIR one, and nothing here reads
the audit column to decide what to keep.

Golden is RUN and never read.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, "/home/user/Veri-Sure")
from specflow.probes import declared_probes  # noqa: E402
from specflow.refmodel.oracle_gen import RequirementOracle  # noqa: E402
from specflow.refmodel.rtl_trace import (decide_rtl, load_traces,  # noqa: E402
                                         rows_from)
from specflow.refmodel.temporal import (phase_sensitive,  # noqa: E402
                                        unbounded_invariant)
from specflow.scorecard import score  # noqa: E402

SRC = Path(sys.argv[1])
GOLD = Path(sys.argv[2])
SUB = Path(sys.argv[3])          # in-family traces, the phase screen's substrate

oracles = json.loads((SRC / "oracles.json").read_text())["oracles"]
_n = json.loads((SRC / "normalized.json").read_text())
normalized = _n["normalized"] if isinstance(_n, dict) else _n
requirements = json.loads((SRC / "requirements.json").read_text())["requirements"]
text_of = {r["uid"]: str(r.get("text") or "") for r in requirements}
_s = json.loads((SRC / "stimulus.json").read_text())
stim = _s["testpoints"] if isinstance(_s, dict) else _s
by_tp = {s["tp_uid"]: s.get("stimulus_steps") or [] for s in stim}
contract = json.loads((GOLD / "contract.json").read_text())
population = [p.read_text() for p in sorted((SRC / "population").glob("*.py"))]
PROBES = tuple(declared_probes(contract))

subs = {}
for f in sorted((SUB / "suite" / "results").glob("TP-*.trace.json")):
    j = json.loads(f.read_text())
    subs[j["tp_uid"]] = rows_from(j)

unbounded, phasey = set(), set()
for x in oracles:
    uid = x["req_uid"]
    if unbounded_invariant(x["source"]):
        unbounded.add(uid)
        continue
    ns: dict = {}
    try:
        exec(compile(x["source"], "<o>", "exec"), ns)
    except Exception:  # noqa: BLE001
        continue
    for tp in x["tp_uids"]:
        tr = subs.get(tp)
        if tr and phase_sensitive(ns["decide"], tr, PROBES, text_of.get(uid, "")):
            phasey.add(uid)
            break
print(f"corpus {len(oracles)} checks | unbounded {len(unbounded)} | "
      f"phase-sensitive {len(phasey)} | overlap {len(unbounded & phasey)}")

traces = load_traces(GOLD / "suite" / "results")
seen = {n for t in traces.values() for e in (t.get("edges") or [])
        for n, v in (e.get("dut") or {}).items() if v is not None}
absent = tuple(n for n in PROBES if n not in seen)


def run(label, drop):
    keep = [x for x in oracles if x["req_uid"] not in drop]
    held = [RequirementOracle(req_uid=x["req_uid"], tp_uids=list(x["tp_uids"]),
                              clause=x.get("clause", ""), source=x["source"])
            for x in keep]
    verdicts: dict = {}
    for r in decide_rtl(held, traces, contract, transactional=True):
        if not r.broken and r.ok is not None:
            verdicts.setdefault(r.req_uid, {})[r.tp_uid] = bool(r.ok)
    card = score(oracles=keep, normalized=normalized, stimulus_by_tp=by_tp,
                 contract=contract, population=population,
                 requirements=requirements, audit_verdicts=verdicts,
                 audit_absent=absent)
    print(f"  {label:12} checks {len(keep):4}  SPAN {card.span:.4f}  "
          f"BLIND {card.blindness:.4f}  AUDIT {card.control_convicted_by:3}/"
          f"{card.control_judges:<3} = {card.audit:.4f}", flush=True)


print(f"\n{'config':14} {'':4}  {'span':6} {'':6}  {'blindness':9} {'audit':>12}")
run("baseline", set())
run("-unbounded", unbounded)
run("-phase", phasey)
run("-both", unbounded | phasey)
