"""Recover the STAGED stimulus and give it real traces.

MY ERROR, not the pipeline's. I handed the stage a FILTERED testplan -- 106 of
c1-i2c's 331 testpoints -- so `next_index` minted TP-0318.. over 106 entries.
TP-0318..TP-0330 already exist in c1's full set, so every staged testpoint
collided with a real one, and scoring looked the staged id up in golden's traces
and found a DIFFERENT scenario.

The scorer's guard only catches a MISSING trace. A trace that exists but is the
wrong one is invisible to it -- exactly the silent-wrong-answer class this
project keeps finding elsewhere.

This renders the staged testpoints under their own ids into a separate suite and
runs them, so the scorer can override the collided ids with the real thing.
"""
import json, shutil, sys, re
from pathlib import Path
sys.path.insert(0, "/home/user/Veri-Sure")

S = Path("/tmp/claude-0/-home-user-Veri-Sure/12bb865e-7a51-5506-b55a-e5ac7cf72a4a/scratchpad")
A = S / "asrt"
IO = A / "full43/io"
RTL = Path(sys.argv[1])
OUT = Path(sys.argv[2])

art = json.load(open(A / "full43/run/specflow/oracles.json"))
added = art["stimulus_added"]                     # {req: [tp_uid, ...]}
contract = json.loads((A / "full43/run/contract.json").read_text())

def latest(req: str):
    """The LAST restimulus answer for this requirement, by round tag.

    r1 supersedes r0: a rejected staging attempt was regenerated, and the
    accepted steps are the later ones. Same discipline as `latest_source`.
    """
    fs = sorted(IO.glob(f"restimulus_{req}_*_response.txt"),
                key=lambda p: p.stat().st_mtime)
    return json.loads(fs[-1].read_text()) if fs else None

stim_by_tp, testplan = {}, []
for req, ids in sorted(added.items()):
    d = latest(req)
    tps = (d or {}).get("testpoints") or []
    if len(tps) != len(ids):
        print(f"  WARNING {req}: {len(ids)} id(s) staged but {len(tps)} testpoint(s) "
              f"in the last answer -- pairing by position over min()")
    for tp_uid, entry in zip(ids, tps):
        steps = entry.get("stimulus_steps") or []
        if not steps:
            print(f"  WARNING {req}/{tp_uid}: no steps"); continue
        stim_by_tp[tp_uid] = steps
        testplan.append({"uid": tp_uid, "tp_uid": tp_uid,
                         "covers": [f"{req}@1"], "stimulus": "staged",
                         "expected_response": "", "dimension": "D2_control_flow"})
print(f"recovered {len(stim_by_tp)} staged testpoint(s): {sorted(stim_by_tp)}")

from specflow.run import run_suite
from specflow.tb.render import render_suite

if OUT.exists():
    shutil.rmtree(OUT)
suite = OUT / "suite"
render_suite(testplan=testplan, bins=[], checks=[], contract=contract,
             out_dir=suite, stimulus_by_tp=stim_by_tp)
shutil.copy(A / "full43/run/specflow/witness.py", OUT / "ref_model.py")

res = run_suite(rtl_path=RTL, hdl_toplevel="i2c_master_bit_ctrl", suite_dir=suite,
                refmodel_path=OUT / "ref_model.py", iteration=99,
                coverage=False, trace=False,
                # The design `include`s i2c_master_defines.v, which sits one
                # level UP from the module -- the same defines file whose
                # absence from the specification is #141.
                include_dirs=[str(RTL.parent), str(RTL.parent.parent)])
print("build_ok:", res.build_ok)
if not res.build_ok:
    print((res.build_log or "")[-1200:]); raise SystemExit(1)
traces = sorted((suite / "results").glob("*.trace.json"))
print(f"traces written: {len(traces)}  -> {suite/'results'}")
