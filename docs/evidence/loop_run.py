"""Assemble a run directory the RTL editor can be pointed at, and run it once.

No model calls. Proves the whole chain mechanically before any agent is asked
to spend a trial on it:

  the repaired 90 frozen as `specflow/oracles.json`
    -> render the suite over c1-i2c's stimulus
    -> run the CANDIDATE RTL
    -> `SpecflowReviewer.review()` decides the frozen set on the recording
    -> `req_results`, `list_failing_requirements()`, `explain(uid)`

Usage: loop_run.py <out_dir> <rtl.v> [n_testpoints] [stimulus_hold]
"""
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, "/home/user/Veri-Sure")
sys.path.insert(0, "/home/user/Veri-Sure/docs/evidence")

RUN = Path("/home/user/runs/c1-i2c")
OUT = Path(sys.argv[1])
RTL = Path(sys.argv[2])
LIMIT = int(sys.argv[3]) if len(sys.argv) > 3 else 0
#: Stimulus step duration. The earlier golden recording this suite's over-
#: strictness was measured against was rendered with `hold=60` (rtl_probe.py's
#: default); the pipeline renders the stimulus as written. That is not a detail:
#: a hold scales how long each step is driven, so it decides whether a command
#: completes inside the window its check opens -- and the same 90 checks convict
#: golden a DIFFERENT NUMBER OF TIMES under the two renderings. 0 = as written.
HOLD = int(sys.argv[4]) if len(sys.argv) > 4 else 0

from repair5 import repaired_suite  # noqa: E402

if OUT.exists():
    shutil.rmtree(OUT)
(OUT / "specflow").mkdir(parents=True)

contract = json.loads((RUN / "contract.json").read_text())
for p in contract.get("io") or []:
    if p.get("name") in ("scl_i", "sda_i"):
        p["idle_value"] = 1
(OUT / "contract.json").write_text(json.dumps(contract, indent=1))

mix = repaired_suite()
(OUT / "specflow" / "oracles.json").write_text(json.dumps(
    {"oracles": [mix[u] for u in sorted(mix)]}, indent=1))
for name in ("requirements.json", "normalized.json", "testplan.json",
             "stimulus.json", "coverage_model.json"):
    shutil.copy(RUN / "specflow" / name, OUT / "specflow" / name)

tp = json.loads((RUN / "specflow/testplan.json").read_text())
tp = tp.get("elements") or tp.get("testplan") or tp
cov = json.loads((RUN / "specflow/coverage_model.json").read_text())
stim = json.loads((RUN / "specflow/stimulus.json").read_text())
by_tp = {t["tp_uid"]: t["stimulus_steps"] for t in stim["testpoints"]}
if HOLD > 1:
    by_tp = {k: [dict(s, hold=HOLD) if "inputs" in s else s for s in v]
             for k, v in by_tp.items()}

# The testpoints the suite actually names, so a limit never drops one an
# oracle points at while keeping one nothing reads.
named = {t for o in mix.values() for t in (o.get("tp_uids") or [])}
keep = [k for k in sorted(by_tp) if k in named]
if LIMIT > 0:
    keep = keep[:LIMIT]
tp = [e for e in tp if (e.get("tp_uid") or e.get("uid")) in keep]
by_tp = {k: by_tp[k] for k in keep}
print(f"suite {len(mix)} checks over {len(tp)} testpoints "
      f"({len(named)} named by the set)", flush=True)

from specflow.run import run_suite            # noqa: E402
from specflow.tb.render import render_suite   # noqa: E402

suite = OUT / "suite"
render_suite(testplan=tp, bins=cov.get("bins") or [], checks=cov.get("checks") or [],
             contract=contract, out_dir=suite, stimulus_by_tp=by_tp)
shutil.copy(RUN / "specflow/witness.py", OUT / "ref_model.py")
shutil.copy(RTL, OUT / "rtl.sv")

res = run_suite(rtl_path=OUT / "rtl.sv", hdl_toplevel="i2c_master_bit_ctrl",
                suite_dir=suite, refmodel_path=OUT / "ref_model.py",
                # trace=True DUMPS A WAVEFORM, and `explain`'s block-internals
                # half is dark without one. The first live editor run had
                # trace=False: all five `explain` calls returned
                # `block_internals: {}`, so the agent saw boundary ports and
                # source and nothing about internal state -- the exact evidence
                # poverty B21 records the debugger inventing a timing theory
                # from. It is the one half of the annotation that a Verilog
                # mismatch table never had.
                iteration=0, coverage=False, trace=True,
                include_dirs=[str(RTL.parent), str(RTL.parent.parent)])
print("build_ok:", res.build_ok, flush=True)
if not res.build_ok:
    print((res.build_log or "")[-2000:])
    raise SystemExit(1)

# --- the surface, exactly as the editor would see it -----------------------
from eda_agent.explain import load_requirement_views    # noqa: E402
from eda_agent.specflow_node import (SpecflowReviewer,  # noqa: E402
                                     _frozen_oracles)
from types import SimpleNamespace                        # noqa: E402

rev = SpecflowReviewer(
    built=SimpleNamespace(suite_dir=suite, refmodel_path=OUT / "ref_model.py",
                          bins=cov.get("bins") or []),
    hdl_toplevel="i2c_master_bit_ctrl", output_dir=OUT,
    oracles=_frozen_oracles(OUT), contract=contract)
rev.req_results = rev._decide_requirements()

from eda_agent.rtl_editor import _EditSession            # noqa: E402
s = _EditSession(tb_path=None, rtl_path=str(OUT / "rtl.sv"), output_dir=str(OUT),
                 last_mismatch_cnt=0, sim_reviewer=rev, max_trials=30,
                 requirements=load_requirement_views(OUT, contract),
                 contract=contract)
s._pull_req_results()

out = s.list_failing_requirements()
print(f"\nreq_results: {len(s.req_results)}   FAILING {len(out['failing'])}   "
      f"UNCOVERED {len(out['uncovered'])}   passing {out['passing_count']}")
for r in out["failing"]:
    print(f"  {r['req_uid']}  {r['testpoint']:<9} {r['check_said'][:70]}")
json.dump({"failing": out["failing"], "uncovered": [r["req_uid"] for r in out["uncovered"]],
           "passing_count": out["passing_count"]},
          open(OUT / "surface.json", "w"), indent=1)

if out["failing"]:
    uid = out["failing"][0]["req_uid"]
    ex = s.explain(uid)
    print(f"\nexplain({uid}):")
    print(json.dumps({k: v for k, v in ex.items()
                      if k in ("check_said", "verdict", "testpoint", "span")}, indent=1))
    print("  boundary rows:", len(ex.get("boundary_ports") or []))
    print("  keys:", sorted(ex))
