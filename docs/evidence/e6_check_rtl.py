"""JUDGE A CANDIDATE RTL WITH THE CHECK SET, AND WITH NOTHING ELSE.

    python docs/evidence/e6_check_rtl.py <candidate.v> [--verbose]

Every other instrument in this tree asks whether a check is any good. This asks
the question the checks exist for: **hand the frozen set to somebody writing
the design, and does satisfying it produce the right design?** That is E5's
constriction question with the direction reversed -- not "how many of seven
spec-derived readings does the set accept" but "does a reading written to
SATISFY the set land in the correct class".

The candidate is elaborated and simulated against the rendered suite, and the
frozen oracles are decided over the recorded DUT trace by `decide_rtl`. The
reference model is in the loop only as the thing the runtime advances in
lockstep so a trace gets recorded; NOTHING here reports its comparison, and
the verdicts printed are the CHECK SET's.

**WHAT THIS DELIBERATELY DOES NOT SHOW.** No golden design, no golden verdict,
no reference-model diff. A candidate is judged by the specification's checks or
it is not judged at all -- otherwise the answer to "does the set constrict to
the correct class" is being supplied by the thing the question is about.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, "/home/user/Veri-Sure")

from specflow.refmodel.oracles import RequirementOracle  # noqa: E402
from specflow import probes  # noqa: E402
from specflow.refmodel.rtl_trace import (decide_rtl, load_traces,  # noqa: E402
                                         rows_from)
from specflow.run import run_suite  # noqa: E402

#: The run whose frozen set is being tried. One directory, so a candidate is
#: never judged against a set from a different run than the suite it ran on --
#: the mismatch that scored a run against a contract that was not in force.
RUN = Path("/tmp/claude-0/-home-user-Veri-Sure/"
           "12bb865e-7a51-5506-b55a-e5ac7cf72a4a/scratchpad/full2/specflow")
TOPLEVEL = "i2c_master_bit_ctrl"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("candidate")
    ap.add_argument("--verbose", action="store_true",
                    help="print the body of each failing check")
    ap.add_argument("--run", default=str(RUN))
    args = ap.parse_args(argv)

    run = Path(args.run)
    cand = Path(args.candidate).resolve()
    if not cand.is_file():
        print(f"no such file: {cand}")
        return 2

    #: **THE RUN'S OWN CONTRACT, PROBES INCLUDED.** Not the input contract plus
    #: a reconstruction: `probes.write_contract` writes the interface the run
    #: actually worked to, and reading anything else is how a run came to be
    #: scored against a contract that was not the one in force.
    cpath = run / "contract.json"
    if not cpath.is_file():
        print(f"no {cpath} -- this run predates the contract being written "
              f"down. Re-run the pipeline, or the probes are not declared "
              f"anywhere a design could be held to them.")
        return 2
    contract = json.loads(cpath.read_text())

    blob = json.loads((run / "oracles.json").read_text())
    oracles = [RequirementOracle(**{k: o[k] for k in
               ("req_uid", "clause", "source", "tp_uids") if k in o})
               for o in blob["oracles"]]
    text = {str(r.get("uid")): str(r.get("text") or "")
            for r in json.loads((run / "requirements.json").read_text()
                                )["requirements"]}

    suite = run / "suite"
    #: **A RUN SCORES ITS OWN TRACES OR IT SCORES NOTHING.** `load_traces`
    #: reads every `*.trace.json` in `results/`, and the directory is shared by
    #: every candidate ever put through this suite. A build that dies partway,
    #: or two candidates run back to back, leaves the previous design's traces
    #: to be decided as this one's -- a verdict about a design that is not the
    #: one on the command line, which is the whole class of defect this file
    #: exists to avoid.
    results = suite / "results"
    stale = sorted(results.glob("*.trace.json")) if results.is_dir() else []
    if stale:
        print(f"clearing {len(stale)} trace(s) from a previous candidate")
        for f in results.iterdir():
            if f.is_file():
                f.unlink()
    print(f"elaborating {cand.name} against {len(oracles)} frozen check(s)",
          flush=True)
    outcome = run_suite(rtl_path=cand, hdl_toplevel=TOPLEVEL, suite_dir=suite,
                        refmodel_path=run / "ref_model.py", iteration=0,
                        coverage=False, trace=False)
    if not outcome.build_ok:
        print("BUILD FAILED -- the candidate did not elaborate.\n")
        print(outcome.build_log[-4000:])
        return 1

    traces = load_traces(suite / "results")
    print(f"{len(traces)} testpoint trace(s) recorded", flush=True)

    #: **CONFORMANCE BEFORE CORRECTNESS, AND IT IS ITS OWN VERDICT.** A probe is
    #: a `dir: "probe"` entry in the contract, so a design is REQUIRED to expose
    #: it. A design that does not is not a design the checks abstained on -- it
    #: has not implemented its interface, and measuring its correctness before
    #: saying so reports the gap as 108 quiet abstentions.
    #:
    #: Measured with a module that declares the contract's ports and ties every
    #: output to a constant: 14 pass, 0 FAIL, 108 abstain -- a design that does
    #: nothing at all, passing.
    #: A probe the design does not declare is still a KEY in the recorded row
    #: -- `Env.sample` writes `None` rather than raising, so the testpoint
    #: survives to produce a verdict. So exposure is a non-`None` value
    #: somewhere, never the key being present.
    exposed = {n for tr in traces.values() for row in rows_from(tr)
               for n, v in (row.get("outputs") or {}).items() if v is not None}
    missing = probes.not_exposed(contract, exposed)
    if missing:
        declared = probes.declared_probes(contract)
        print(f"\nNOT CONTRACT-CONFORMANT: {len(missing)} of {len(declared)} "
              f"declared probe(s) are not exposed by this design.\n  "
              + ", ".join(missing))
        print("\nEvery check reading one of them can say nothing about this "
              "design. Expose them as ports and re-run; the numbers below are "
              "over the remainder and are NOT a verdict on the design.")
    results = decide_rtl(oracles, traces, contract)
    by_uid = {r.req_uid: r for r in results}
    src = {o.req_uid: o.source for o in oracles}

    failed = sorted(u for u, r in by_uid.items() if r.ok is False)
    passed = sorted(u for u, r in by_uid.items() if r.ok is True)
    silent = sorted(u for u, r in by_uid.items() if r.ok is None)
    print(f"\nCHECK SET  {len(passed)} pass, {len(failed)} FAIL, "
          f"{len(silent)} abstain (never fired), of {len(oracles)}")
    #: An abstention is NOT a pass and is never folded into one. The check was
    #: not put in the situation it watches for, which says nothing about the
    #: design.
    for u in failed:
        print(f"\n--- FAIL {u} ---\n{text.get(u, '').strip()[:600]}")
        detail = (by_uid[u].detail or "").strip()
        if detail:
            print(f"  detail: {detail[:400]}")
        if args.verbose:
            print("  check:\n" + "\n".join(
                "    " + ln for ln in (src.get(u) or "").splitlines()[:40]))
    if not failed:
        print("\nEVERY CHECK THAT FIRED PASSED.")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
