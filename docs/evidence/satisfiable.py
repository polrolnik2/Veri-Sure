"""Which failing requirements can the DESIGN fix, and which are unsatisfiable?

The debug loop's stop condition depends on telling those apart, and no gate in
the pipeline can: a check that convicts the candidate looks identical to one
that convicts everything. So decide the SAME frozen set over the SAME stimulus
against the GOLDEN design and split on that.

  DISCRIMINATING  golden passes, candidate fails -> a real defect. The loop's
                  job, and the only class an edit can discharge.
  CONVICTS GOLDEN the check FAILS the known-good design too. No edit to the
                  candidate can satisfy it, because the reference does not
                  satisfy it either. Either the requirement is written wrong or
                  the harness cannot express it -- either way the loop must STOP
                  rather than burn trials chasing it. THIS is the proof.
  GOLDEN SILENT   golden ABSTAINED: the check never fired against the reference.
                  THAT IS NOT A VERDICT. It is an evidence gap in the golden
                  run, and it says nothing whatever about whether the
                  requirement is satisfiable -- the reference was simply never
                  put in the situation the check watches for. Counting it as
                  unsatisfiable would let a stimulus gap license abandoning a
                  requirement the design may well be violating. UNKNOWN, and it
                  must be reported as its own class rather than folded into
                  either neighbour.
  INVERTED        candidate passes, golden fails. Rarer and worse: the check
                  rewards the defect.

GOLDEN IS A DIAGNOSTIC HERE, NEVER A GATE. It is read after the fact to classify
requirements; the editor never sees it and no verdict shown to the agent is
computed against it.
"""
from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

sys.path.insert(0, "/home/user/Veri-Sure")

from specflow.refmodel.oracles import RequirementOracle       # noqa: E402
from specflow.refmodel.rtl_trace import decide_rtl, load_traces  # noqa: E402


def decide(run: Path) -> dict[str, bool | None]:
    contract = json.loads((run / "contract.json").read_text())
    oracles = [RequirementOracle(**{k: o[k] for k in
               ("req_uid", "clause", "source", "tp_uids") if k in o})
               for o in json.loads(
                   (run / "specflow/oracles.json").read_text())["oracles"]]
    traces = load_traces(run / "suite/results")
    return {r.req_uid: r.ok for r in decide_rtl(oracles, traces, contract)}


def main(cand_dir: str, gold_dir: str) -> int:
    cand, gold = decide(Path(cand_dir)), decide(Path(gold_dir))
    text = {}
    for n in json.loads((Path(gold_dir) / "specflow/requirements.json"
                         ).read_text()).get("requirements", []):
        text[str(n.get("uid"))] = str(n.get("text") or "")

    rows = []
    for u in sorted(set(cand) | set(gold)):
        c, g = cand.get(u), gold.get(u)
        if c is False and g is False:
            cls = "CONVICTS-GOLDEN"
        elif c is False and g is True:
            cls = "DISCRIMINATING"
        elif c is False and g is None:
            cls = "GOLDEN-SILENT"
        elif c is True and g is False:
            cls = "INVERTED"
        else:
            cls = ""
        if cls:
            rows.append((u, cls, c, g, text.get(u, "")[:64]))

    by = collections.Counter(r[1] for r in rows)
    print(f"{'req':<11}{'class':<17}{'cand':<7}{'gold':<7}requirement")
    for u, cls, c, g, t in rows:
        print(f"{u:<11}{cls:<17}{str(c):<7}{str(g):<7}{t}")
    print()
    for k, n in by.most_common():
        print(f"  {n:>3}  {k}")

    # ONLY a failure against golden proves anything. An abstention is the golden
    # run declining to answer, and folding it in here would let a stimulus gap
    # license abandoning a requirement the design may well be violating.
    unsat = [u for u, cls, *_ in rows if cls == "CONVICTS-GOLDEN"]
    unknown = [u for u, cls, *_ in rows if cls == "GOLDEN-SILENT"]
    print(f"\nPROVEN UNSATISFIABLE (golden fails them too): {len(unsat)}  {unsat}")
    print(f"REACHABLE BY THE LOOP (golden passes them)  : "
          f"{sum(1 for r in rows if r[1] == 'DISCRIMINATING')}")
    print(f"UNKNOWN -- golden never exercised them, so no verdict either way: "
          f"{len(unknown)}  {unknown}")
    json.dump({"rows": rows, "unsatisfiable": unsat, "unknown": unknown},
              open(Path(cand_dir) / "satisfiable.json", "w"), indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
