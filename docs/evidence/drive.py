"""Re-author c1-i2c's golden-convicting checks with LOCAL agents as the model.

The real `run_oracle_stage`, unmodified, driven through `AgentPort`. Nothing
here teaches it anything: the inputs are c1-i2c's own frozen artifacts and the
only substitution is who answers the prompts.

WHAT MAY NOT BE PASSED, and why the omission is the experiment's validity:
`control_source` stays None. The golden i2c RTL is the scoring instrument, and
§4 is explicit -- "the control is an authority, and that is exactly why it may
not gate... gating on the control tunes the model toward the grade
transitively." No agent in this run sees it, directly or through a verdict.

THE WITNESS IS COPIED, NOT REGENERATED. `_witness` documents why: it is written
once and read forever, because "the thing doing the measuring has to hold
still." Regenerating it would make the over-strictness bound a different reading
of the same requirements than the one the 43 were measured against, and the
comparison would not be a comparison.
"""
import argparse, json, shutil, sys, time
from pathlib import Path
sys.path.insert(0, "/home/user/Veri-Sure")

S = Path("/tmp/claude-0/-home-user-Veri-Sure/12bb865e-7a51-5506-b55a-e5ac7cf72a4a/scratchpad")
SRC = Path("/home/user/runs/c1-i2c")

ap = argparse.ArgumentParser()
ap.add_argument("--name", default="pilot")
ap.add_argument("--limit", type=int, default=0, help="0 = all 43")
ap.add_argument("--workers", type=int, default=8)
ap.add_argument("--repair-attempts", type=int, default=2)
ap.add_argument("--correspondence", action="store_true", default=True)
ap.add_argument("--no-correspondence", dest="correspondence", action="store_false")
ap.add_argument("--staging", action="store_true", default=True)
ap.add_argument("--no-staging", dest="staging", action="store_false")
ap.add_argument("--timeout", type=float, default=7200.0)
ap.add_argument("--resume", action="store_true",
                help="keep the rendezvous and REPLAY every answer already in it")
a = ap.parse_args()

EXP = S / "asrt" / a.name
IO = EXP / "io"
RUN = EXP / "run"
if EXP.exists() and not a.resume:
    shutil.rmtree(EXP)
(RUN / "specflow").mkdir(parents=True, exist_ok=True)
IO.mkdir(parents=True, exist_ok=True)

over = json.load(open(S / "asrt/over_strict.json"))["over_strict"]
if a.limit:
    over = over[:a.limit]
want = set(over)

contract_json = (SRC / "contract.json").read_text()
contract = json.loads(contract_json)
# The idle-value correction rtl_probe applied: the c1 contract does not declare
# the open-drain pull-ups, so a bus line left alone reads 0 instead of 1.
for p in contract.get("io") or []:
    if p.get("name") in ("scl_i", "sda_i"):
        p["idle_value"] = 1
contract_json = json.dumps(contract, indent=2)
(RUN / "contract.json").write_text(contract_json)

reqs_all = json.load(open(SRC / "specflow/requirements.json"))["requirements"]
reqs = [r for r in reqs_all if r.get("uid") in want]
norm = {n["req_uid"]: n for n in json.load(open(SRC / "specflow/normalized.json"))["normalized"]}
normalized = {u: norm[u] for u in want if u in norm}

tp_all = json.load(open(SRC / "specflow/testplan.json"))
tp_all = tp_all.get("elements") or tp_all.get("testplan") or tp_all
def _covers(e):
    return {c.split("@")[0] for c in (e.get("covers") or [])}
testplan = [e for e in tp_all if _covers(e) & want]
keep = {e.get("tp_uid") or e.get("uid") for e in testplan}

stim = json.load(open(SRC / "specflow/stimulus.json"))
stim_by_tp = {t["tp_uid"]: t["stimulus_steps"] for t in stim["testpoints"]
              if t["tp_uid"] in keep}
shutil.copy(SRC / "specflow/witness.py", RUN / "specflow/witness.py")
shutil.copy(SRC / "specflow/stimulus.json", RUN / "specflow/stimulus.json")
spec = (SRC / "prompt.txt").read_text()

if not (RUN / "specflow/witness.py").is_file():
    raise SystemExit("the witness was not copied; the over-strictness bound would be a DIFFERENT reading")
print(f"requirements {len(reqs)}   testpoints {len(testplan)}   "
      f"stimulus {len(stim_by_tp)}   witness {'reused' if (RUN/'specflow/witness.py').is_file() else 'MISSING'}")
missing = want - {r["uid"] for r in reqs}
if missing:
    print(f"  WARNING: no S1 record for {sorted(missing)}")

# Widen the pool and drop the cache warm-up. `run_fanout`'s serial head exists
# to warm a PROVIDER'S prompt cache; there is no provider here, so it only
# serialises the first two prompts for nothing. Driver-only: the module default
# is untouched.
import functools
from specflow import stage as _stage
_wide = functools.partial(_stage.run_fanout, workers=a.workers, warmup=0)
from specflow.refmodel import oracle_gen as _og, correspondence as _corr
_og.run_fanout = _wide
_corr.run_fanout = _wide

from specflow.model_io import AgentPort, resumable
from specflow.oracles_stage import run_oracle_stage

(IO / "MANIFEST.json").write_text(json.dumps({
    "experiment": a.name, "requirements": sorted(want),
    "correspondence": a.correspondence, "staging": a.staging,
    "repair_attempts": a.repair_attempts,
}, indent=1))

t0 = time.time()
err = None
try:
    oset = run_oracle_stage(
        requirements=reqs, contract_json=contract_json, contract=contract,
        testplan=testplan, stimulus_by_tp=stim_by_tp,
        # RESUMABLE. `run_fanout` persists nothing per item, so a stage killed
        # part way loses every call it had already paid for -- and this one was
        # killed by its own wall-clock guard with 49 answers on disk.
        # `ResumePort` replays a recorded response by (stage, round_) and falls
        # through to the live port when there is none, so a second attempt costs
        # only the items the first did not reach.
        port=(resumable(AgentPort(root=IO, timeout=a.timeout), IO) if a.resume
              else AgentPort(root=IO, timeout=a.timeout)),
        workdir=RUN / "specflow", normalized=normalized, spec=spec,
        control_source=None,          # THE GOLDEN RTL MAY NOT GATE
        want_variants=False,          # ~14 calls each; #61: variants move liveness, not discrimination
        want_correspondence=a.correspondence,
        want_staging=a.staging,
        # rewrite=False DELIBERATELY. It unlinks witness.py (oracles_stage.py:895)
        # because a new requirement set deserves a new witness -- correct in
        # production, fatal here: the copied witness is the instrument the 43
        # were measured against, and regenerating it would change the ruler
        # mid-comparison. The run directory is freshly made, so rewrite has no
        # stale artifact to clear anyway.
        run_dir=RUN, fanout=True, rewrite=False,
        repair_attempts=a.repair_attempts,
    )
except BaseException as exc:   # noqa: BLE001
    err = repr(exc)
    print(f"\nSTAGE DID NOT COMPLETE: {err}", flush=True)
(IO / "DONE").write_text(err or "ok")
print(f"\nelapsed {time.time()-t0:.0f}s   "
      f"calls {len(list(IO.glob('*_prompt.txt')))}")
if err:
    raise SystemExit(1)

import collections
print("dispositions:", dict(collections.Counter(oset.dispositions.values())))
print(f"wrote {RUN/'specflow/oracles.json'}")
