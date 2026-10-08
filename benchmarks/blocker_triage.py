"""Which of a run's gate errors does the machinery actually reach?

`refmodel_gate.json` says a build is blocked and by how much. It does not say
whether anything in the pipeline is capable of acting on each blocker, and that
is the question that decides what to build next -- a blocker three instruments
already reach is not the same finding as one nothing touches.

Answers it per requirement, from the artifacts on disk. Pure replay: the model,
the oracles and the stimulus are all recorded, so this costs no model call and
can be run against any completed run, including ones that predate the fixes it
tests for.

    python3 benchmarks/blocker_triage.py <run>/specflow [--contract path]

What each mechanism means here, and what it does NOT mean:

    20 truncation   `verdict.truncated` -- the oracle failed by reaching the end
                    of the trace, so the finding is the stimulus's. RE-ROUTED,
                    not removed: NOT_EXERCISED blocks too.
    21 idle-match   `judged_before_the_scenario` -- decided before anything it
                    reads had moved. An ADVISORY the author may decline.
    22 self-split   `disagrees_with_itself` -- holds on most of its own
                    testpoints. Also an advisory, also declinable.
    must_fail       the never-triggered fix. Reaching a VACUOUS verdict does not
                    mean clearing it: re-scoring w-i2c's eleven left three still
                    convicted.
    add_stimulus    the route can now attach a minted testpoint to the
                    requirement it was minted for. Whether the generated
                    scenario reaches the clause is a separate question this
                    cannot answer offline.
    correspondence  an off-target rejection is QUOTABLE, so it seeds the next
                    repair round. Same lever as vacuity -- more draws -- rather
                    than a class with nothing behind it.

So "reached" is an upper bound on what the machinery can do, and the residue is
the honest lower bound on what it cannot.
"""
from __future__ import annotations

import argparse
import collections
import glob
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from specflow.refmodel import liveness as L
from specflow.refmodel import trust, verdict
from specflow.refmodel.oracles import RequirementOracle

#: Reaching a verdict class is not clearing it. Each of these carries a repair
#: route; none of them is a guarantee, and the notes say which is which.
BY_VERDICT = {
    "VACUOUS": ("must_fail", "re-scored; reaching it is not clearing it"),
    "ORACLE_INVALID": ("correspondence", "off-target is quotable; it seeds a repair round"),
    "NOT_EXERCISED": ("add_stimulus", "the route can now attach what it mints"),
}


def _latest_turn(run: Path) -> dict:
    turns = sorted(glob.glob(str(run / "judge/r*/trust.json")),
                   key=lambda p: int(re.search(r"/r(\d+)/", p).group(1)))
    if not turns:
        raise SystemExit(f"no turn artifacts under {run}/judge/r*/trust.json")
    return json.load(open(turns[-1]))


def _gate_requirements(run: Path) -> list[str]:
    """The requirements the GATE errors on, read from the gate itself.

    Not from a plan or a summary: `docs/convergence-plan.md` carries two
    different blocker counts in two sections, and the one quoted for a week was
    the stale one. UNOBSERVABLE is advisory and does not appear here.
    """
    gate = json.load(open(run / "refmodel_gate.json"))
    out: list[str] = []
    for issue in gate.get("issues") or []:
        if issue.get("severity") != "error":
            continue
        m = re.search(r"REQ-\d{4}",
                      f"{issue.get('path', '')} {issue.get('message', '')}")
        if m:
            out.append(m.group(0))
    return sorted(set(out))


def triage(run: Path, contract: dict) -> list[tuple[str, str, str, str]]:
    stim = json.load(open(run / "stimulus.json"))
    by_tp = {t["tp_uid"]: t.get("stimulus_steps") or []
             for t in stim["testpoints"] if t.get("stimulus_steps")}
    book = json.load(open(run / "oracles.json"))
    disp = book.get("dispositions") or {}
    oracles = {o["req_uid"]: RequirementOracle(**o) for o in book.get("oracles") or []}
    model = (run / "ref_model.py").read_text()
    by_req = _latest_turn(run)["mechanical_verdicts"]["by_requirement"]

    rows = []
    for uid in _gate_requirements(run):
        v = by_req.get(uid, disp.get(uid, "?"))
        if v in BY_VERDICT:
            rows.append((uid, v, *BY_VERDICT[v]))
            continue
        oracle = oracles.get(uid)
        if v != "VIOLATES" or oracle is None:
            rows.append((uid, v, "", "no oracle on disk" if oracle is None else ""))
            continue

        held = trust._decide_over(  # noqa: SLF001
            oracle, model, contract, by_tp, base="step", transactional=True)
        detail = held.detail or ""
        if verdict.truncated(detail):
            rows.append((uid, v, "20 truncation", "re-routed to NOT_EXERCISED"))
        elif L.judged_before_the_scenario(oracle, held.rows, contract,
                                          at_edge=held.edge):
            rows.append((uid, v, "21 idle-match", "advisory, declinable"))
        elif L.disagrees_with_itself(oracle, model, contract, by_tp, base="step"):
            rows.append((uid, v, "22 self-split", "advisory, declinable"))
        else:
            rows.append((uid, v, "", detail[:70] or "(no detail)"))
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run", type=Path, help="a run's specflow/ directory")
    ap.add_argument("--contract", type=Path, default=None,
                    help="contract.json (default: <run>/../contract.json)")
    args = ap.parse_args()

    run = args.run
    contract_path = args.contract or (run.parent / "contract.json")
    if not contract_path.is_file():
        contract_path = run / "contract.json"
    contract = json.load(open(contract_path))

    rows = triage(run, contract)
    print(f"{'req':10} {'verdict':15} {'reached by':15} note")
    print("-" * 100)
    for uid, v, reached, note in rows:
        print(f"{uid:10} {v:15} {reached or '— NOTHING':15} {note[:56]}")

    residue = [r for r in rows if not r[2]]
    print(f"\n{len(rows)} gate errors; {len(rows) - len(residue)} reached by a "
          f"mechanism, {len(residue)} reached by nothing.")
    if residue:
        print("\nTHE RESIDUE -- nothing in the pipeline acts on these:")
        for uid, v, _r, note in residue:
            print(f"  {uid} [{v}]  {note}")
    print(f"\nby mechanism: "
          f"{dict(collections.Counter(r[2] or 'NOTHING' for r in rows))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
