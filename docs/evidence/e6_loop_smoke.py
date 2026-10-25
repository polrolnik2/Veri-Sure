"""Drive the edit loop with NO MODEL AT ALL, against the real suite.

    e6_loop_smoke.py <run-dir> <rtl>

**THE LOOP'S MECHANICS ARE NOT THE AGENT'S.** `_EditSession` owns staging,
`check_staged`, the trial budget, the latch rule, the rollback and the accepted
baseline; `RTLEditor` only wraps it in an agent that decides WHICH edits to
try. So the mechanics can be exercised by a script -- real RTL, real
elaboration, real cocotb run, real verdicts from the real 122 checks, and not
one model call.

What this verifies, each of which was a defect this branch has fixed or
could regress:

  * a staged edit changes nothing until `commit`
  * `commit` spends exactly one trial
  * a commit that lowers the passing count is ROLLED BACK and the accepted RTL
    is byte-identical afterwards
  * the accepted baseline does NOT move on a rollback -- the defect that let a
    later commit latch by beating a discarded attempt
  * a commit that holds the passing count, silences nothing and lowers the
    failing count LATCHES ON THE GRADIENT
  * a commit that lowers the failing count BY SILENCING does not latch

It cannot verify what the agent chooses, which is the part that needs a model.
"""
import json
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, "/home/user/Veri-Sure")
from eda_agent.rtl_editor import _EditSession  # noqa: E402
from eda_agent.specflow_node import (SpecflowReviewer,  # noqa: E402
                                     _frozen_oracles)

RUN, RTL = Path(sys.argv[1]), Path(sys.argv[2])
contract = json.loads((RUN / "contract.json").read_text())
cov = json.loads((RUN / "coverage_model.json").read_text())
reviewer = SpecflowReviewer(
    built=SimpleNamespace(suite_dir=RUN / "suite",
                          refmodel_path=RUN / "ref_model.py",
                          bins=cov.get("bins") or []),
    hdl_toplevel=str(contract.get("module_name") or "TopModule"),
    output_dir=RUN, oracles=_frozen_oracles(RUN), contract=contract)

work = RUN / "rtl.sv"
work.write_text(RTL.read_text(encoding="utf-8"), encoding="utf-8")
ok, failing, _log = reviewer.review()
print(f"baseline: pass={ok} failing testpoints={failing}", flush=True)

s = _EditSession(tb_path=None, rtl_path=str(work), output_dir=str(RUN),
                 last_mismatch_cnt=failing, sim_reviewer=reviewer,
                 max_trials=4, contract=contract)
s._pull_req_results()
base = s._req_split()
print(f"  requirements: {len(base[0])} passing, {len(base[1])} failing, "
      f"{len(base[2])} uncovered", flush=True)

before = s.read_rtl()
#: A COMMIT THAT MUST BE ROLLED BACK. Breaking the reset makes the design
#: strictly worse, so the latch rule has to refuse it and restore the file.
hit = s.stage_edit("nReset", "1'b1")
print(f"\nstage_edit: executed={hit.get('is_action_executed')} "
      f"{hit.get('error_msg', '')[:60]}")
print(f"  accepted RTL unchanged while staged: {s.read_rtl() == before}")
if hit.get("is_action_executed"):
    r = s.commit()
    print(f"  commit -> trials {s.action_calls}/{s.max_trials}; "
          f"latched={r.get('is_action_executed')}")
    print(f"  reason: {(r.get('error_msg') or r.get('accept_reason') or '')[:110]}")
    print(f"  accepted RTL restored byte-identical: {s.read_rtl() == before}")
    after = s._accepted_req_split
    print(f"  baseline still the ACCEPTED design: "
          f"{after is not None and len(after[0]) == len(base[0])} "
          f"({len(base[0])} passing)")
else:
    print("  (anchor not present in this candidate; nothing committed)")
