"""The gate that ALREADY SHIPS, applied to a frozen set that predates it.

    e6_unbounded_rule.py <corpus-dir> <golden-suite-dir>

**THIS IS NOT A NEW RULE.** `well_formed` refuses an invariant asserted over a
window opened `until=TO_END` -- `temporal.unbounded_invariant` finds it, and the
objection is already worded in-tree: "everything after the first activation is
inside it ... and the first such gap convicts, whatever the design did." The
refusal is blocking today. `full2` was frozen BEFORE it landed, so its set still
carries three bodies the current pipeline would not accept, and every audit
figure taken from that set counts convictions today's oracle stage would never
have shipped.

So this measures a REGENERATION, not a proposal:

    a body `well_formed` refuses is dropped, and its requirement is RE-SERVED
    from its own corpus of superseded bodies -- the earliest one (lowest round,
    then corpus order) that `well_formed` accepts. If none exists, the
    requirement has no check and loses its span.

Applied to every match, including matches that convict nothing -- on `full2`,
3 of 122 bodies match and one of the three (`REQ-0046`) convicts the control not
at all. Selecting by the audit column is gating on the grade and is barred; the
gate selects by the shape, and this reports what that costs.

## Why re-serving matters, and what it exposes about the repair loop

Refusing a check without re-serving costs span by construction, which is the
objection to every gate this branch has added. The corpus makes the refusal
cheap where an alternative exists -- and looking at the alternatives says
something about the loop that produced them:

    REQ-0034   round 0 generate  bounded     round 2 repair  UNBOUNDED  -> accepted UNBOUNDED
               round 0 resample  bounded
               round 1 repair    bounded
    REQ-0128   round 0 generate  bounded     round 0 resample UNBOUNDED -> accepted UNBOUNDED
               round 1 repair    bounded
    REQ-0046   every body UNBOUNDED                                     -> no alternative

**THE REPAIR LOOP INTRODUCED THE SHAPE THE GATE NOW REFUSES.** REQ-0034's
round-1 repair is bounded and its round-2 repair is not, and the liveness note
driving that round reads "the state this check waits for WAS REACHED on its own
stimulus and the check did not decide ... make the window open on
`sta_condition`". Pressure to make a check DECIDE produced a window that can
only convict. That is the vacuity/over-strictness trade arriving one repair
round at a time, and no gate downstream of the loop can see it.

Golden is RUN and never read.
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, "/home/user/Veri-Sure")
from specflow.probes import declared_probes  # noqa: E402
from specflow.refmodel.oracle_gen import RequirementOracle  # noqa: E402
from specflow.refmodel.oracles import well_formed  # noqa: E402
from specflow.refmodel.rtl_trace import decide_rtl, load_traces  # noqa: E402
from specflow.refmodel.temporal import (licenses_a_cycle_count,  # noqa: E402
                                        unbounded_invariant)
from specflow.scorecard import score  # noqa: E402

SRC, GOLD = Path(sys.argv[1]), Path(sys.argv[2])
blob = json.loads((SRC / "oracles.json").read_text())
oracles, corpus = blob["oracles"], (blob.get("corpus") or {})
_n = json.loads((SRC / "normalized.json").read_text())
normalized = _n["normalized"] if isinstance(_n, dict) else _n
requirements = json.loads((SRC / "requirements.json").read_text())["requirements"]
text_of = {r["uid"]: str(r.get("text") or "") for r in requirements}
_s = json.loads((SRC / "stimulus.json").read_text())
stim = _s["testpoints"] if isinstance(_s, dict) else _s
by_tp = {s["tp_uid"]: s.get("stimulus_steps") or [] for s in stim}
_t = json.loads((SRC / "testplan.json").read_text())
testplan = (_t if isinstance(_t, list) else
            _t.get("elements") or _t.get("testpoints") or [])
contract = json.loads((GOLD / "contract.json").read_text())
population = [p.read_text() for p in sorted((SRC / "population").glob("*.py"))]
traces = load_traces(GOLD / "suite" / "results")
seen = {n for t in traces.values() for e in (t.get("edges") or [])
        for n, v in (e.get("dut") or {}).items() if v is not None}
absent = tuple(n for n in declared_probes(contract) if n not in seen)

SEQ = re.compile(r"\b(after|then|subsequently|following|in response to|once|"
                 r"thereafter|next)\b", re.I)


def licensed_to_follow(uid: str) -> bool:
    t = text_of.get(uid, "")
    return bool(SEQ.search(t)) or licenses_a_cycle_count(t)


def demote(x: dict) -> dict:
    """`TRIPLE.md`'s licence rule, unchanged -- applied to every candidate body
    so the third rule is measured on top of the first two rather than instead."""
    if licensed_to_follow(x["req_uid"]):
        return x
    out = re.sub(r"after_activation\s*=\s*True", "after_activation=False",
                 x["source"])
    out = re.sub(r"^(\s*follows\s*=\s*)True", r"\1False", out, flags=re.M)
    return {**x, "source": out} if out != x["source"] else x


def usable(uid: str, source: str, tp_uids: list) -> bool:
    """`well_formed` accepts it. That is the whole test, and deliberately.

    The `TO_END`-invariant refusal lives INSIDE `well_formed`, so asking the
    shape separately would be this driver re-implementing the gate it is
    measuring -- and a driver's copy of a gate is what drifts from it.
    """
    o = RequirementOracle(req_uid=uid, tp_uids=list(tp_uids), clause="",
                          source=source)
    return well_formed(o, contract, testplan) is None


def reserve(x: dict) -> dict | None:
    """The earliest usable corpus body for this requirement, or None."""
    bodies = sorted(enumerate(corpus.get(x["req_uid"]) or []),
                    key=lambda p: (int(p[1].get("round") or 0), p[0]))
    for _, b in bodies:
        if usable(x["req_uid"], b["source"], x["tp_uids"]):
            return {**x, "source": b["source"]}
    return None


def advance(tr, probes):
    """`TRIPLE.md`'s phase rule, unchanged."""
    out = {}
    for tp, t in tr.items():
        edges = [dict(e) for e in (t.get("edges") or [])]
        duts = [dict(e.get("dut") or {}) for e in edges]
        for i, e in enumerate(edges):
            d = dict(duts[i])
            nxt = duts[i + 1] if i + 1 < len(duts) else {}
            for n in probes:
                if n in d:
                    d[n] = nxt.get(n)
            e["dut"] = d
        out[tp] = {**t, "edges": edges}
    return out


def run(label, tr, keep):
    held = [RequirementOracle(req_uid=x["req_uid"], tp_uids=list(x["tp_uids"]),
                              clause=x.get("clause", ""), source=x["source"])
            for x in keep]
    v: dict = {}
    for r in decide_rtl(held, tr, contract, transactional=True,
                        stimulus_by_tp=by_tp):
        if not r.broken and r.ok is not None:
            v.setdefault(r.req_uid, {})[r.tp_uid] = bool(r.ok)
    c = score(oracles=keep, normalized=normalized, stimulus_by_tp=by_tp,
              contract=contract, population=population,
              requirements=requirements, audit_verdicts=v, audit_absent=absent)
    m = "MET" if c.span > 0.90 else "no "
    b = "MET" if c.blindness < 0.20 else "no "
    a = "MET" if c.audit == 0 else "no "
    print(f"  {label:38} SPAN {c.span:.4f} {m}  BLIND {c.blindness:.4f} {b}  "
          f"AUDIT {c.control_convicted_by}/{c.control_judges} "
          f"= {c.audit:.4f} {a}", flush=True)
    return c, v


matched = [x for x in oracles
           if not usable(x["req_uid"], x["source"], x["tp_uids"])]
shape = [x["req_uid"] for x in matched if unbounded_invariant(x["source"])]
print(f"frozen bodies today's `well_formed` REFUSES: {len(matched)} of "
      f"{len(oracles)}  ({len(shape)} for the unbounded-invariant shape)")
for x in matched:
    alt = reserve(x)
    n = len(corpus.get(x["req_uid"]) or [])
    print(f"  {x['req_uid']}  {n} corpus body(ies)  -> "
          + ("re-served" if alt else "NO USABLE ALTERNATIVE, loses its check"))

refused = {x["req_uid"] for x in matched}
served: list[dict] = []
lost: list[str] = []
for x in oracles:
    if x["req_uid"] not in refused:
        served.append(x)
        continue
    alt = reserve(x)
    if alt is None:
        lost.append(x["req_uid"])
    else:
        served.append(alt)
print(f"\ncheck set: {len(oracles)} -> {len(served)}  "
      f"(lost: {' '.join(lost) or 'none'})\n")
print("target: span > 0.90, blindness < 0.20, audit = 0\n")

EQ = ("sta_condition", "sto_condition")
adv = advance(traces, EQ)
run("baseline (as frozen)", traces, oracles)
run("phase + licence", adv, [demote(x) for x in oracles])
_c, verdicts = run("phase + licence + unbounded refusal", adv,
                   [demote(x) for x in served])

kind_of = {r["uid"]: str(r.get("unit_kind") or "?") for r in requirements}
left = sorted(u for u, d in verdicts.items() if not all(d.values()))
print(f"\nremaining convictions, enumerated directly: {len(left)}")
for u in left:
    where = sorted(t for t, ok in verdicts[u].items() if not ok)
    print(f"  {u} [{kind_of.get(u, '?')}] on {len(where)} testpoint(s): "
          f"{' '.join(where[:4])}{' ...' if len(where) > 4 else ''}")
