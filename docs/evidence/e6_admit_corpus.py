"""Does admitting more of the corpus lower BLINDNESS, and what does it cost?

Blindness is the disagreement cells no accepted check separates. The run
accepts ONE body per requirement -- 122 of a 616-body corpus -- so most of what
was authored and paid for never reaches the set. More bodies means more
separators, which should lower blindness; rejections UNION, so it should also
raise audit.

**NOTHING HERE READS THE AUDIT COLUMN.** Admission is by structural
well-formedness only, the same mechanical screen the pipeline already applies.
The point is to measure the trade, not to pick the winner.

Golden is RUN and never read.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, "/home/user/Veri-Sure")
from specflow.probes import declared_probes  # noqa: E402
from specflow.refmodel.oracle_gen import RequirementOracle  # noqa: E402
from specflow.refmodel.oracles import well_formed  # noqa: E402
from specflow.refmodel.rtl_trace import decide_rtl, load_traces  # noqa: E402
from specflow.scorecard import score  # noqa: E402

SRC, GOLD = Path(sys.argv[1]), Path(sys.argv[2])
blob = json.loads((SRC / "oracles.json").read_text())
oracles, corpus = blob["oracles"], (blob.get("corpus") or {})
_n = json.loads((SRC / "normalized.json").read_text())
normalized = _n["normalized"] if isinstance(_n, dict) else _n
requirements = json.loads((SRC / "requirements.json").read_text())["requirements"]
_s = json.loads((SRC / "stimulus.json").read_text())
stim = _s["testpoints"] if isinstance(_s, dict) else _s
by_tp = {s["tp_uid"]: s.get("stimulus_steps") or [] for s in stim}
contract = json.loads((GOLD / "contract.json").read_text())
plan = json.loads((SRC / "testplan.json").read_text())["elements"]
population = [p.read_text() for p in sorted((SRC / "population").glob("*.py"))]
traces = load_traces(GOLD / "suite" / "results")
seen = {n for t in traces.values() for e in (t.get("edges") or [])
        for n, v in (e.get("dut") or {}).items() if v is not None}
absent = tuple(n for n in declared_probes(contract) if n not in seen)
accepted = {x["req_uid"]: x for x in oracles}


def admitted(limit: int | None) -> list[dict]:
    """The accepted set plus up to `limit` extra well-formed bodies each."""
    out = list(oracles)
    if limit == 0:
        return out
    for uid, members in sorted(corpus.items()):
        base = accepted.get(uid)
        if base is None:
            continue
        extra = 0
        for m in members:
            src = m.get("source") or ""
            if not src or src == base["source"]:
                continue
            cand = {**base, "source": src}
            o = RequirementOracle(req_uid=uid, tp_uids=list(base["tp_uids"]),
                                  clause=base.get("clause", ""), source=src)
            if well_formed(o, contract, plan):
                continue
            out.append(cand)
            extra += 1
            if limit is not None and extra >= limit:
                break
    return out


def run(label, keep):
    held = [RequirementOracle(req_uid=x["req_uid"], tp_uids=list(x["tp_uids"]),
                              clause=x.get("clause", ""), source=x["source"])
            for x in keep]
    v: dict = {}
    for r in decide_rtl(held, traces, contract, transactional=True):
        if not r.broken and r.ok is not None:
            v.setdefault(r.req_uid, {})[r.tp_uid] = bool(r.ok)
    c = score(oracles=keep, normalized=normalized, stimulus_by_tp=by_tp,
              contract=contract, population=population,
              requirements=requirements, audit_verdicts=v, audit_absent=absent)
    m = lambda ok: "MET" if ok else "no "  # noqa: E731
    print(f"  {label:22} bodies {len(keep):4}  SPAN {c.span:.4f} {m(c.span > 0.90)}  "
          f"BLIND {c.blindness:.4f} {m(c.blindness < 0.20)}  "
          f"AUDIT {c.control_convicted_by}/{c.control_judges} = {c.audit:.4f}  "
          f"eff_size {c.effective_size}", flush=True)


print(f"corpus: {sum(len(v) for v in corpus.values())} bodies over "
      f"{len(corpus)} requirements; accepted {len(oracles)}\n")
print("target: span > 0.90, blindness < 0.20, audit = 0\n")
for label, lim in (("accepted only", 0), ("+1 body each", 1),
                   ("+2 bodies each", 2), ("all well-formed", None)):
    run(label, admitted(lim))
