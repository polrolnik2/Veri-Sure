"""The triple with today's two corrections applied AS RULES, not as patches.

**NEITHER CORRECTION READS THE AUDIT COLUMN.** Choosing what to change by
whether it convicts the control is gating on the grade, which this project
bars. Both rules below are derived from the requirement's own words and applied
UNIFORMLY to every check that matches, including the ones that convict nothing.

  1. PHASE. The specification writes an equation and not a schedule, so a
     design may offer a condition combinationally or register it. Applied by
     reading the control's `sta_condition`/`sto_condition` one edge early --
     the two probes whose equation the specification states.

  2. `|->` NOT `|=>`. `after_activation=True` claims the effect FOLLOWS the
     trigger. Flipped to False on every check whose requirement text carries no
     sequence word and licenses no cycle count -- `correspondence`'s existing
     licence test, applied to the flag.

Golden is RUN and never read.
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, "/home/user/Veri-Sure")
from specflow.probes import declared_probes  # noqa: E402
from specflow.refmodel.oracle_gen import RequirementOracle  # noqa: E402
from specflow.refmodel.rtl_trace import decide_rtl, load_traces  # noqa: E402
from specflow.refmodel.temporal import licenses_a_cycle_count  # noqa: E402
from specflow.scorecard import score  # noqa: E402

SRC, GOLD = Path(sys.argv[1]), Path(sys.argv[2])
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
traces = load_traces(GOLD / "suite" / "results")
seen = {n for t in traces.values() for e in (t.get("edges") or [])
        for n, v in (e.get("dut") or {}).items() if v is not None}
absent = tuple(n for n in declared_probes(contract) if n not in seen)

SEQ = re.compile(r"\b(after|then|subsequently|following|in response to|once|"
                 r"thereafter|next)\b", re.I)


def licensed_to_follow(uid: str) -> bool:
    t = text_of.get(uid, "")
    return bool(SEQ.search(t)) or licenses_a_cycle_count(t)


def corrected(x: dict) -> dict:
    """`|=>` demoted to `|->` where the requirement's words do not license it."""
    if licensed_to_follow(x["req_uid"]):
        return x
    src = x["source"]
    out = re.sub(r"after_activation\s*=\s*True", "after_activation=False", src)
    out = re.sub(r"^(\s*follows\s*=\s*)True", r"\1False", out, flags=re.M)
    return {**x, "source": out} if out != src else x


def advance(tr, probes):
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
    #: **`stimulus_by_tp` ARMS `decide_rtl`'s OWN REFUSAL, AND OMITTING IT COST
    #: THIS FILE A HEADLINE.** The guard has been in `rtl_trace` all along and
    #: is opt-in: without it, scoring one run's oracles against another run's
    #: traces "succeeds, folds cleanly, and produces a conviction rate about a
    #: scenario the oracles were never written for". Eighteen drivers under
    #: `docs/evidence/` called `decide_rtl` and not one passed it, which is how
    #: `audit 1/35 = 0.0286` was published against a suite whose provenance was
    #: never checked. The honest figure on a digest-verified control is 6/43.
    for r in decide_rtl(held, tr, contract, transactional=True,
                        stimulus_by_tp=by_tp):
        if not r.broken and r.ok is not None:
            v.setdefault(r.req_uid, {})[r.tp_uid] = bool(r.ok)
    c = score(oracles=keep, normalized=normalized, stimulus_by_tp=by_tp,
              contract=contract, population=population,
              requirements=requirements, audit_verdicts=v, audit_absent=absent)
    m = lambda ok: "MET" if ok else "no "  # noqa: E731
    print(f"  {label:34} SPAN {c.span:.4f} {m(c.span > 0.90)}  "
          f"BLIND {c.blindness:.4f} {m(c.blindness < 0.20)}  "
          f"AUDIT {c.control_convicted_by}/{c.control_judges} "
          f"= {c.audit:.4f} {m(c.audit == 0)}", flush=True)
    return c, v


fixed = [corrected(x) for x in oracles]
changed = sum(1 for a, b in zip(oracles, fixed) if a["source"] != b["source"])
print(f"checks whose `|=>` was demoted to `|->` by the licence rule: {changed}"
      f" of {len(oracles)}\n")
print("target: span > 0.90, blindness < 0.20, audit = 0\n")
EQ = ("sta_condition", "sto_condition")
run("baseline", traces, oracles)
run("phase only", advance(traces, EQ), oracles)
run("licence rule only", traces, fixed)
_card, verdicts = run("both", advance(traces, EQ), fixed)

#: **THE SCORECARD'S COUNT AND THE ENUMERATION DISAGREE, DELIBERATELY.**
#: `score` counts only `unit_kind == "behavioural"` requirements, so a
#: `scaffolding` check that convicts the control is a conviction the audit
#: column does not report. Both are right about what they measure, and
#: "n convictions left" is the wrong sentence unless it says which n.
kind_of = {r["uid"]: str(r.get("unit_kind") or "?") for r in requirements}
left = sorted(u for u, d in verdicts.items() if not all(d.values()))
print(f"\nremaining convictions, enumerated directly: {len(left)}")
for u in left:
    where = sorted(t for t, ok in verdicts[u].items() if not ok)
    print(f"  {u} [{kind_of.get(u, '?')}] on {len(where)} testpoint(s): "
          f"{' '.join(where[:4])}{' ...' if len(where) > 4 else ''}")
