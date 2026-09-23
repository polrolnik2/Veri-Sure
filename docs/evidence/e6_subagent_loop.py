"""Drive the edit session from OUTSIDE, so an agent with no gateway can steer it.

    e6_subagent_loop.py brief <run-dir>              -> current state, for an editor
    e6_subagent_loop.py apply <run-dir> <edit.json>  -> stage, commit, report

**THE SESSION IS THE LOOP; THE AGENT ONLY CHOOSES.** `_EditSession` owns
staging, `check_staged`, the trial budget, the latch rule, the rollback and the
accepted baseline, and none of it calls a model. `RTLEditor` wraps it in an
agentscope agent bound to the gateway, and that binding is the only thing a
budget outage stops. Splitting the two lets any editor drive the real loop --
real elaboration, a real cocotb run, real verdicts from the real frozen set.

Each invocation rebuilds the session from `rtl.sv` on disk and reviews it, so
the baseline is always the ACCEPTED design and no state has to survive between
processes. The trial count lives in `trials.json` beside it.

`edit.json` is `{"old_text": ..., "new_text": ...}` or
`{"block_id": ..., "new_code": ...}`.
"""
import json
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, "/home/user/Veri-Sure")
from eda_agent.rtl_editor import _EditSession  # noqa: E402
from eda_agent.specflow_node import (SpecflowReviewer,  # noqa: E402
                                     _frozen_oracles)

MODE, RUN = sys.argv[1], Path(sys.argv[2])
contract = json.loads((RUN / "contract.json").read_text())
cov = json.loads((RUN / "coverage_model.json").read_text())
reviewer = SpecflowReviewer(
    built=SimpleNamespace(suite_dir=RUN / "suite",
                          refmodel_path=RUN / "ref_model.py",
                          bins=cov.get("bins") or []),
    hdl_toplevel=str(contract.get("module_name") or "TopModule"),
    output_dir=RUN, oracles=_frozen_oracles(RUN), contract=contract)

tally = RUN / "trials.json"
spent = json.loads(tally.read_text())["spent"] if tally.is_file() else 0
_ok, failing, _log = reviewer.review()
s = _EditSession(tb_path=None, rtl_path=str(RUN / "rtl.sv"),
                 output_dir=str(RUN), last_mismatch_cnt=failing,
                 sim_reviewer=reviewer, max_trials=1, contract=contract)
s._pull_req_results()
ok0, bad0, dark0 = s._req_split()

if MODE == "brief":
    fails = s.list_failing_requirements()
    print(json.dumps({
        "trials_spent": spent,
        "failing_testpoints": failing,
        "passing": len(ok0), "failing": len(bad0), "uncovered": len(dark0),
        "failing_requirements": fails.get("requirements", fails),
        "suspect_blocks": s.list_suspect_blocks(),
    }, indent=1, default=str)[:14000])
elif MODE == "apply":
    edit = json.loads(Path(sys.argv[3]).read_text())
    if "block_id" in edit:
        st = s.stage_replace(edit["block_id"], edit["new_code"])
    else:
        st = s.stage_edit(edit["old_text"], edit["new_text"])
    if not st.get("is_action_executed"):
        print(json.dumps({"staged": False, "why": st.get("error_msg")}, indent=1))
        raise SystemExit(0)
    chk = s.check_staged()
    r = s.commit()
    tally.write_text(json.dumps({"spent": spent + 1}))
    print(json.dumps({
        "staged": True,
        "check_staged": {k: chk.get(k) for k in
                         ("syntax_ok", "multidriven", "warnings") if k in chk},
        "latched": bool(r.get("is_action_executed")),
        "reason": (r.get("accept_reason") or r.get("error_msg") or "")[:400],
        "failing_testpoints": f"{failing} -> {r.get('sim_mismatch_cnt')}",
        "passing": f"{len(ok0)} -> ?",
        "trials_spent": spent + 1,
    }, indent=1, default=str))
else:
    raise SystemExit(f"unknown mode {MODE!r}")
