"""Does a freshly authored REQ-0046 discriminate the filter, or repeat the mistake?

The frozen REQ-0046 was thrown away as ORACLE_INVALID and the surviving REQ-0010
INVERTED -- passing run 10, which deleted the input filter, and convicting the
golden design that has it. So a new check has exactly two things to prove, and
one of them is the one both previous attempts failed:

    on GOLDEN   (filter present)   -> PASS
    on RUN 10   (filter bypassed)  -> FAIL

Either verdict alone is worthless. A check that fails both is the old
"no output may change on any input edge"; one that passes both is vacuous; one
that passes run 10 and fails golden is the inversion again.

GOLDEN IS THE SCORER, NEVER THE AUTHOR'S INPUT. The authoring subagent saw the
requirement, the normalized form and the port list, and no RTL of any kind.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, "/home/user/Veri-Sure")

S = Path("/tmp/claude-0/-home-user-Veri-Sure/12bb865e-7a51-5506-b55a-e5ac7cf72a4a/scratchpad")


def main(check_path: str) -> int:
    from specflow.refmodel.oracles import RequirementOracle
    from specflow.refmodel.rtl_trace import decide_rtl, load_traces

    source = Path(check_path).read_text()
    contract = json.loads((S / "asrt/run10/contract.json").read_text())
    # tp_uids empty: decide against EVERY testpoint, which is what the frozen
    # set does and what makes the two columns comparable.
    orc = [RequirementOracle(req_uid="REQ-0046", clause="majority filter",
                             source=source, tp_uids=[])]

    out = {}
    for tag, d in (("GOLDEN  (filter present)", "asrt/gold10"),
                   ("RUN 10  (filter bypassed)", "asrt/run10")):
        res = decide_rtl(orc, load_traces(S / d / "suite/results"), contract)
        r = res[0] if res else None
        out[tag] = (getattr(r, "ok", None), getattr(r, "detail", "") or "")
        v = {True: "PASS", False: "FAIL", None: "abstain"}[out[tag][0]]
        print(f"{tag:<26} {v:<8} {out[tag][1][:110]}")

    g = out["GOLDEN  (filter present)"][0]
    c = out["RUN 10  (filter bypassed)"][0]
    print()
    if g is True and c is False:
        print("  DISCRIMINATES. Passes the design with the filter, fails the one without.")
        return 0
    if g is False and c is True:
        print("  INVERTED -- the same defect as the surviving REQ-0010.")
    elif g == c:
        print(f"  DOES NOT DISCRIMINATE: both {g!r}. "
              + ("Vacuous." if g is not False else
                 "Convicts the known-good design, like the check that was rejected."))
    else:
        print(f"  INCONCLUSIVE: golden={g!r} run10={c!r} -- an abstention on one side "
              "means the trace never presented the experiment.")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else str(S / "req46/decide.py")))
