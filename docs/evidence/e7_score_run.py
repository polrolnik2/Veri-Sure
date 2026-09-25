"""Score what a run SHIPPED against golden, with the pipeline's rules and no others.

    e7_score_run.py <corpus-or-specflow-dir> <golden-suite-dir> [--pool] [--json OUT]

`e6_cover.py` re-derived the shipped set itself and applied two corrections the
pipeline does not -- the licence demotion and a one-edge advance of golden's
`sta_condition`/`sto_condition`. Both were measured as rules, and both are
honest, but a figure computed with them is a figure about a driver, not about
the pipeline. This reads the set the run wrote to `shipped.json` (or, with
`--pool`, the whole admitted pool from `oracles.json`) and decides it on golden's
recording with `decide_rtl` exactly as `SpecflowReviewer` does, stimulus
provenance armed. Nothing is selected, demoted, advanced or re-derived here.

`<golden-suite-dir>` is what `e6_replay_corpus.py` writes: `contract.json` plus
`suite/results/*.trace.json` from golden run through a suite regenerated from
this corpus's own stimulus.

Golden is RUN and never read.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, "/home/user/Veri-Sure")
from specflow.oracles_stage import admitted_pool  # noqa: E402
from specflow.probes import declared_probes  # noqa: E402
from specflow.refmodel.oracle_gen import RequirementOracle  # noqa: E402
from specflow.refmodel.rtl_trace import decide_rtl, load_traces  # noqa: E402
from specflow.scorecard import render, score  # noqa: E402


def _load(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


class _Set:
    def __init__(self, trusted, corpus_map):
        self.trusted, self.corpus = trusted, corpus_map


class _Body:
    def __init__(self, uid, source, arm="", round_=0):
        self.req_uid, self.source, self.arm, self.round_ = uid, source, arm, round_
        self.answered, self.frozen = "", False


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) < 2:
        print(__doc__.strip().splitlines()[2])
        return 2
    src, gold = Path(args[0]), Path(args[1])
    if (src / "specflow").is_dir():
        src = src / "specflow"
    reqs = _load(src / "requirements.json")
    reqs = reqs["requirements"] if isinstance(reqs, dict) else reqs
    _n = _load(src / "normalized.json")
    normalized = _n["normalized"] if isinstance(_n, dict) else _n
    _s = _load(src / "stimulus.json")
    stim = _s["testpoints"] if isinstance(_s, dict) else _s
    by_tp = {s["tp_uid"]: s.get("stimulus_steps") or [] for s in stim}
    contract = _load(gold / "contract.json")
    _t = _load(src / "testplan.json")
    plan = _t if isinstance(_t, list) else (_t.get("elements") or [])
    population = [p.read_text() for p in sorted((src / "population").glob("*.py"))]
    blob = _load(src / "oracles.json")

    if "--pool" in sys.argv or not (src / "shipped.json").is_file():
        what = "the admitted POOL (oracles.json + corpus)"
        trusted = [RequirementOracle(req_uid=x["req_uid"], tp_uids=list(x["tp_uids"]),
                                     clause=x.get("clause", ""), source=x["source"])
                   for x in blob.get("oracles") or []]
        cmap = {uid: [_Body(uid, m.get("source") or "", m.get("arm", ""),
                            int(m.get("round") or 0)) for m in members]
                for uid, members in (blob.get("corpus") or {}).items()}
        bodies = [{"req_uid": o.req_uid, "tp_uids": list(o.tp_uids),
                   "clause": o.clause, "source": o.source}
                  for o in admitted_pool(_Set(trusted, cmap), contract, plan)]
        if "--pool" not in sys.argv:
            what += " -- NO shipped.json, so this is not a shipped set"
    else:
        what = "the SHIPPED set (shipped.json)"
        bodies = _load(src / "shipped.json")["oracles"]

    traces = load_traces(gold / "suite" / "results")
    seen = {n for t in traces.values() for e in (t.get("edges") or [])
            for n, v in (e.get("dut") or {}).items() if v is not None}
    absent = tuple(n for n in declared_probes(contract) if n not in seen)
    held = [RequirementOracle(req_uid=b["req_uid"], tp_uids=list(b["tp_uids"]),
                              clause=b.get("clause", ""), source=b["source"])
            for b in bodies]
    v: dict = {}
    for r in decide_rtl(held, traces, contract, transactional=True,
                        stimulus_by_tp=by_tp):
        if r.broken or r.ok is None:
            continue
        per = v.setdefault(r.req_uid, {})
        per[r.tp_uid] = per.get(r.tp_uid, True) and bool(r.ok)
    card = score(oracles=bodies, normalized=normalized, stimulus_by_tp=by_tp,
                 contract=contract, population=population, requirements=reqs,
                 audit_verdicts=v, audit_absent=absent)
    print(f"{src}\nscoring {what}: {len(bodies)} bodies over "
          f"{len({b['req_uid'] for b in bodies})} requirement(s); "
          f"{len(traces)} golden trace(s)\n")
    print(render(card))
    kind = {r["uid"]: str(r.get("unit_kind") or "?") for r in reqs}
    left = sorted(u for u, d in v.items() if not all(d.values()))
    print(f"\nconvicting golden: {len(left)}  "
          + " ".join(f"{u}[{kind.get(u, '?')[:5]}]" for u in left))
    met = (card.span is not None and card.span > 0.90,
           card.blindness is not None and card.blindness < 0.10,
           card.audit == 0)
    print(f"target span>0.90 {'MET' if met[0] else 'no'}  "
          f"blindness<0.10 {'MET' if met[1] else 'no'}  "
          f"audit=0 {'MET' if met[2] else 'no'}")
    out = sys.argv[sys.argv.index("--json") + 1] if "--json" in sys.argv else None
    if out:
        Path(out).write_text(json.dumps({
            "scored": what, "bodies": len(bodies), "span": card.span,
            "blindness": card.blindness, "audit": card.audit,
            "audit_convicted": card.control_convicted_by,
            "audit_judges": card.control_judges,
            "effective_size": card.effective_size,
            "convicting": left}, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
