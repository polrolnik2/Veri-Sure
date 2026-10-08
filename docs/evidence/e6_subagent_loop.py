"""Drive the edit session from OUTSIDE, so an agent with no gateway can steer it.

    e6_subagent_loop.py brief <run-dir>              -> current state, for an editor
    e6_subagent_loop.py apply <run-dir> <edit.json>  -> stage, commit, report

Both modes write their JSON to `<run-dir>/_brief.json` / `<run-dir>/_apply.json`
as well as printing it, because a review prints a quarter of a megabyte of
simulator chatter to the same stdout and the result is unreadable there.

`<run-dir>/budget.json` may hold `{"max": N}`; `apply` refuses once
`trials.json` reaches it, so a run has a fixed budget nobody can talk it out of.

**A TRIAL IS TWO FULL REVIEWS AND ONLY ONE OF THEM IS NEW.** `apply` has to
know the ACCEPTED design's verdicts before it can judge the edit against them,
and that design was reviewed by the previous `apply` -- the same bytes, the same
suite, the same answer. `baseline_cache.json` keys those verdicts on the md5 of
`rtl.sv`, so the baseline review runs once, at the very start, and never again.
Only `.ok` per requirement is cached, which is all the accept decision reads;
`brief` ignores the cache entirely and reviews for real, because it also reports
per-requirement DETAIL that `.ok` cannot reconstruct.

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
import hashlib
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
_oracles = _frozen_oracles(RUN)
if not _oracles:
    raise SystemExit(
        f"NO FROZEN ORACLES under {RUN / 'specflow' / 'oracles.json'}. "
        "`_frozen_oracles` degrades to [] rather than raising, so without this "
        "the whole 482-testpoint review runs and publishes NOTHING -- every "
        "per-requirement number downstream is then vacuously empty, and the "
        "only symptom is `_req_split()` returning None much later.")
reviewer = SpecflowReviewer(
    built=SimpleNamespace(suite_dir=RUN / "suite",
                          refmodel_path=RUN / "ref_model.py",
                          bins=cov.get("bins") or []),
    hdl_toplevel=str(contract.get("module_name") or "TopModule"),
    output_dir=RUN, oracles=_oracles, contract=contract)

tally = RUN / "trials.json"
spent = json.loads(tally.read_text())["spent"] if tally.is_file() else 0
cap = RUN / "budget.json"
max_trials = json.loads(cap.read_text())["max"] if cap.is_file() else None


def _emit(name: str, payload: dict) -> None:
    text = json.dumps(payload, indent=1, default=str)
    (RUN / f"_{name}.json").write_text(text)
    print(f"\n===JSON=== written to {RUN / f'_{name}.json'}\n{text[:14000]}")


if MODE == "apply" and max_trials is not None and spent >= max_trials:
    _emit("apply", {"staged": False, "why": f"budget spent: {spent}/{max_trials}",
                    "trials_spent": spent})
    raise SystemExit(0)
CACHE = RUN / "baseline_cache.json"
RTL = RUN / "rtl.sv"


def _key() -> str:
    return hashlib.md5(RTL.read_bytes()).hexdigest()


def _cache_put(key: str, failing: int, rr: dict) -> None:
    d = json.loads(CACHE.read_text()) if CACHE.is_file() else {}
    d[key] = {"failing": int(failing),
              "ok": {u: getattr(r, "ok", None) for u, (r, _t) in rr.items()}}
    CACHE.write_text(json.dumps(d))


def _cache_get(key: str):
    if not CACHE.is_file():
        return None
    d = json.loads(CACHE.read_text()).get(key)
    if not d:
        return None
    return d["failing"], {u: (SimpleNamespace(ok=v), None)
                          for u, v in d["ok"].items()}


start_key = _key()
hit = _cache_get(start_key) if MODE == "apply" else None
if hit is None:
    _ok, failing, _log = reviewer.review()
    cached = False
else:
    failing, reviewer.req_results = hit
    cached = True
s = _EditSession(tb_path=None, rtl_path=str(RTL),
                 output_dir=str(RUN), last_mismatch_cnt=failing,
                 sim_reviewer=reviewer, max_trials=1, contract=contract)
s._pull_req_results()
ok0, bad0, dark0 = s._req_split()
if not cached:
    _cache_put(start_key, failing, s.req_results)
# The accepted baseline is KNOWN here, so the session never has to fall back to
# re-deriving it from `req_results` -- which, after a trial, describes the design
# that was just discarded.
s._accepted_req_split = (ok0, bad0, dark0)

if MODE == "brief":
    fails = s.list_failing_requirements()
    _emit("brief", {
        "trials_spent": spent, "trials_max": max_trials,
        "failing_testpoints": failing,
        "passing": len(ok0), "failing": len(bad0), "uncovered": len(dark0),
        "failing_requirements": fails.get("requirements", fails),
        "suspect_blocks": s.list_suspect_blocks(),
    })
elif MODE == "apply":
    edit = json.loads(Path(sys.argv[3]).read_text())
    if "block_id" in edit:
        st = s.stage_replace(edit["block_id"], edit["new_code"])
    else:
        st = s.stage_edit(edit["old_text"], edit["new_text"])
    if not st.get("is_action_executed"):
        _emit("apply", {"staged": False, "why": st.get("error_msg"),
                        "trials_spent": spent})
        raise SystemExit(0)
    chk = s.check_staged()
    r = s.commit()
    tally.write_text(json.dumps({"spent": spent + 1}))
    # `commit` reviews the TRIAL and pulls its verdicts; a rollback restores the
    # file WITHOUT re-reviewing. So these are what the EDIT did, which is the
    # informative reading -- they are NOT the accepted design when `latched` is
    # false, and the key names say so.
    ok1, bad1, dark1 = s._req_split()
    if bool(r.get("is_action_executed")):
        _cache_put(_key(), int(r.get("sim_mismatch_cnt") or 0), s.req_results)
    _emit("apply", {
        "staged": True,
        "check_staged": {k: chk.get(k) for k in
                         ("syntax_ok", "multidriven", "warnings") if k in chk},
        "latched": bool(r.get("is_action_executed")),
        "reason": (r.get("accept_reason") or r.get("error_msg") or "")[:400],
        "failing_testpoints_accepted_then_trial":
            f"{failing} -> {r.get('sim_mismatch_cnt')}",
        "accepted_passing_then_trial_passing": f"{len(ok0)} -> {len(ok1)}",
        "accepted_failing_then_trial_failing": f"{len(bad0)} -> {len(bad1)}",
        "accepted_dark_then_trial_dark": f"{len(dark0)} -> {len(dark1)}",
        "trial_newly_passing": sorted(ok1 - ok0),
        "trial_newly_failing": sorted(bad1 - bad0),
        "trial_newly_uncovered": sorted(dark1 - dark0),
        "trials_spent": spent + 1, "trials_max": max_trials,
        "baseline_was_cached": cached,
    })
else:
    raise SystemExit(f"unknown mode {MODE!r}")
