"""Everything downstream of normalization, re-run on the new normalized set.

`normalized_by_uid` feeds four stages, and each one is regenerated here because
each one read the old forms:

    S2 testplan      run_s2_fanout(normalized=...)   -> new testpoints
    S3 coverage      run_s3_fanout(normalized=...)   -> new bins and checks
    stimulus         per testpoint, so it moves when S2 does
    [O] oracles      run_oracle_stage(normalized=...) -> the checks themselves

S2 IS WHY THE WHOLE CHAIN HAS TO MOVE. Its testpoint uids are what every
oracle's `tp_uids` names and what every stimulus entry is keyed by, so a new
testplan invalidates the frozen oracle set outright -- there is no way to
regenerate only the checks and keep the suite.

THE REFERENCE MODEL IS NOT RUN. It reads `normalized` too, so it is strictly in
scope, and it is skipped deliberately: it is the artifact the plan retires, its
debug turn is measured moving the held-out grade by exactly zero, and c1-i2c's
own node failed at that stage with 68 issues while the oracle set it is
compared against had already been written. Running it would be the most
expensive call in the chain and would change nothing being measured. Named here
rather than quietly omitted.

THE WITNESS IS COPIED, NOT REGENERATED, for the reason it always is: it is the
instrument that bounds over-strictness, and "the thing doing the measuring has
to hold still". Regenerating it would make this run's over-strictness a
different reading of the same requirements than c1-i2c's.

NOTHING HERE SEES THE GOLDEN RTL. `control_source` stays None.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, "/home/user/Veri-Sure")

SRC = Path("/home/user/runs/c1-i2c")


def main() -> int:
    from specflow.model_io import PortSettings, make_port, resumable
    from specflow.oracles_stage import run_oracle_stage
    from specflow.refmodel.compose import choose_base
    from specflow.s2_testplan import TestplanOutput, run_s2_fanout
    from specflow.s2_testplan import write_artifacts as write_s2
    from specflow.s3_coverage import run_s3_fanout
    from specflow.s3_coverage import write_artifacts as write_s3
    from specflow.stage import StageResult
    from specflow.testcase_agent import (
        SuiteStimulus,
        run_suite_stimulus_fanout,
        stimulus_by_tp,
    )

    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", default="/home/user/runs/n1-i2c")
    ap.add_argument("--max-repairs", type=int, default=3)
    ap.add_argument("--model", default="gpt-5-mini",
                    help="S2, S3 and stimulus: the model c1-i2c recorded")
    #: THE CHECK AUTHOR GETS ITS OWN MODEL, and only it.
    #:
    #: `PortSettings.deep_effort_stages` already names `oracle` as the stage
    #: worth spending more on, and records why: eleven oracles [O] could not
    #: make non-vacuous were re-authored at full strength and "one of the first
    #: five produced a check `gpt-5-mini`/medium could not write... So authoring
    #: quality is a real lever." Its cheap arm -- raise effort, keep the model
    #: -- ships disabled (`deep_effort` defaults to None) and is unmeasured.
    #: This is the expensive arm, run deliberately.
    #:
    #: TWO COSTS, both known. `gpt-5.6-luna` caches on EXACT INPUT rather than
    #: on a prefix, so a fan-out gets no shared-prefix discount and every call
    #: pays its whole prompt. And this buys the REPAIR rounds as well as
    #: generation, which is where a stronger author was already measured to
    #: help -- `run_stage` takes one port for both, so they cannot be split
    #: without changing it.
    ap.add_argument("--oracle-model", default="gpt-5.6-luna")
    ap.add_argument("--oracle-effort", default="medium",
                    choices=["low", "medium", "high", "xhigh"],
                    help="high is safe: EFFORT_CHUNK gives it a 48000 slice, "
                         "and the measured stream deaths were at 9000")
    ap.add_argument("--effort", default="medium")
    ap.add_argument("--skip", default="", help="comma list: s2,s3,stimulus,oracles")
    a = ap.parse_args()
    skip = {s.strip() for s in a.skip.split(",") if s.strip()}

    run_dir = Path(a.run_dir)
    sf = run_dir / "specflow"
    reqs = json.loads((SRC / "specflow/requirements.json").read_text())["requirements"]
    contract_json = (SRC / "contract.json").read_text()
    contract = json.loads(contract_json)
    spec = (SRC / "prompt.txt").read_text()

    norm_path = sf / "normalized.json"
    if not norm_path.is_file():
        raise SystemExit(f"{norm_path} missing -- run renorm.py first")
    normalized_by_uid = {
        n["req_uid"]: n
        for n in json.loads(norm_path.read_text()).get("normalized", [])
        if n.get("req_uid")
    }
    print(f"normalized forms in hand: {len(normalized_by_uid)}", flush=True)

    settings = PortSettings(model=a.model, effort=a.effort,
                            small_model=a.model, small_effort=a.effort)
    port = resumable(make_port("api", run_dir / "agent_io", settings=settings),
                     run_dir / "agent_io")
    oracle_settings = PortSettings(
        model=a.oracle_model, effort=a.oracle_effort,
        small_model=a.oracle_model, small_effort=a.oracle_effort)
    oracle_port = resumable(
        make_port("api", run_dir / "agent_io", settings=oracle_settings),
        run_dir / "agent_io")
    t0 = time.time()

    # --- S2 ------------------------------------------------------------------
    if "s2" not in skip:
        merged, per_item = run_s2_fanout(
            requirements=reqs, contract_json=contract_json, port=port,
            normalized=normalized_by_uid, max_repairs=a.max_repairs)
        s2 = StageResult(merged, [i for r in per_item for i in r.issues],
                         max((r.rounds for r in per_item), default=0))
        write_s2(run_dir, s2)
        print(f"S2: {len(s2.output.elements)} testpoints, ok={s2.ok} "
              f"({time.time()-t0:.0f}s)", flush=True)
    # Read back from disk rather than from `s2` above, so a --skip s2 re-entry
    # takes exactly the same path as a fresh one.
    tps = [e.model_dump() for e in TestplanOutput(
        **json.loads((sf / "testplan.json").read_text())).elements]

    # --- S3 ------------------------------------------------------------------
    if "s3" not in skip:
        merged3, per3 = run_s3_fanout(
            testplan=tps, contract_json=contract_json, port=port,
            normalized=normalized_by_uid, max_repairs=a.max_repairs)
        s3 = StageResult(merged3, [i for r in per3 for i in r.issues],
                         max((r.rounds for r in per3), default=0))
        write_s3(run_dir, s3)
        print(f"S3: {len(s3.output.bins)} bins, ok={s3.ok} "
              f"({time.time()-t0:.0f}s)", flush=True)

    # --- stimulus ------------------------------------------------------------
    if "stimulus" not in skip:
        merged_s, per_s = run_suite_stimulus_fanout(
            testplan=tps, contract=contract, port=port,
            max_repairs=a.max_repairs, requirements=reqs)
        (sf / "stimulus.json").write_text(
            json.dumps(merged_s.model_dump(), indent=2) + "\n", encoding="utf-8")
        print(f"stimulus: {len(merged_s.testpoints)} testpoints "
              f"({time.time()-t0:.0f}s)", flush=True)
    stim_by_tp = stimulus_by_tp(SuiteStimulus(
        **json.loads((sf / "stimulus.json").read_text())))

    # --- [O] the oracles -----------------------------------------------------
    if "oracles" not in skip:
        # HOLD THE TWO INSTRUMENTS STILL: the witness, which bounds
        # over-strictness, and the variants, which are the must-fail leg.
        #
        # `variants.json` carries 335 wrong implementations over 104 of the 127
        # requirements. The requirement set here is byte-identical to c1-i2c's,
        # and `run_oracle_stage` states the rule itself: "GENERATED ONCE, FROM
        # THE WITNESS, AND THEN NEVER AGAIN... A variant is a wrong
        # implementation of ONE requirement, and the requirement does not
        # change." Regenerating is not merely 335 calls -- it is a DIFFERENT
        # DRAW, so "an oracle can be convicted vacuous this round and cleared
        # the next for no reason anyone could name".
        #
        # The normalized form does reach variants, in two narrow places, and
        # neither is touched by what changed: `kinds_for` scans only
        # `activation.text` and `expectation` (never `observed_via` or `when`),
        # and `build_prompt` carries the form as context. `kinds_delta` below
        # checks the first empirically rather than trusting the reading.
        for name in ("_witness", "witness.py", "variants.json", "exercised.json"):
            src, dst = SRC / "specflow" / name, sf / name
            if src.exists() and not dst.exists():
                (shutil.copytree if src.is_dir() else shutil.copy2)(src, dst)
        oracle_set = run_oracle_stage(
            requirements=reqs, contract_json=contract_json, contract=contract,
            testplan=tps, stimulus_by_tp=stim_by_tp, port=oracle_port,
            workdir=sf, base=choose_base(contract),
            normalized=normalized_by_uid, spec=spec,
            control_source=None,          # the golden RTL never reaches here
            want_variants=True, want_correspondence=True,
            run_dir=run_dir, fanout=True,
            # NOT rewrite=True. It unlinks variants.json AND witness.py, so the
            # two files copied above would be deleted and regenerated -- the
            # exact opposite of holding them still. The flag exists for a
            # CHANGED REQUIREMENT SET, where old variants describe requirements
            # that no longer exist; this run reuses c1-i2c's requirements.json
            # unchanged, so it does not apply. A fresh run dir has no
            # oracles.json, so nothing stale is reused either.
            rewrite=False)
        print(f"[O]: {len(oracle_set.trusted)} trusted "
              f"({time.time()-t0:.0f}s)", flush=True)

    print(f"\ndone in {time.time()-t0:.0f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
