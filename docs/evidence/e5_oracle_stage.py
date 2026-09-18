"""Re-run [O] ALONE against a completed run's upstream artifacts, then score it.

A full pipeline run is about three hours and most of it is S1, probes, S2, S3,
stimulus and normalize -- none of which changes when the thing under test is how
checks are authored, refuted and repaired. This re-enters `run_oracle_stage`
with the upstream held fixed, so an authoring change can be measured in about an
hour instead of three, and measured against IDENTICAL inputs rather than a fresh
draw that moves every number at once.

    python docs/evidence/e5_oracle_stage.py <source_run> <out_dir> [pop] [cells] [attempts]

The witness and the population are COPIED from the source run rather than
regenerated, for the reason the stage itself holds them on disk: "the thing
doing the measuring has to hold still". Two runs of this differ in the checks
and in nothing else.

The control is loaded for the scorecard's audit column only. It is not passed as
`control_source`, so it cannot reach the stage, an author or a repair prompt.
"""
import collections
import json
import logging
import shutil
import sys
from pathlib import Path

#: **THE STAGE'S OWN PROGRESS, ON STDOUT.** `run_oracle_stage` reports what it
#: is doing through `logger.info` and the drivers here never configured
#: logging, so a run of it was a silent hour -- which is how a cell-authoring
#: leg came to produce nothing with the only two lines that would have said so
#: going nowhere. Filtered to the pipeline's own loggers: the OpenAI client is
#: chatty at INFO and drowns them.
logging.basicConfig(level=logging.WARNING, format="%(message)s",
                    stream=sys.stdout)
for _name in ("specflow.oracles_stage", "specflow.scorecard",
              "specflow.refmodel.liveness"):
    logging.getLogger(_name).setLevel(logging.INFO)

sys.path.insert(0, "/home/user/Veri-Sure")
from specflow import scorecard as SC  # noqa: E402
from specflow.model_io import PortSettings, make_port  # noqa: E402
from specflow.oracles_stage import run_oracle_stage  # noqa: E402
from specflow.refmodel.compose import choose_base  # noqa: E402

SRC = Path(sys.argv[1])
OUT = Path(sys.argv[2])
POP = int(sys.argv[3]) if len(sys.argv) > 3 else 7
CELLS = int(sys.argv[4]) if len(sys.argv) > 4 else 12
ATTEMPTS = int(sys.argv[5]) if len(sys.argv) > 5 else 3
DRAFTS = int(sys.argv[6]) if len(sys.argv) > 6 else 0

src = SRC / "specflow"
out = OUT / "specflow"
if OUT.exists():
    shutil.rmtree(OUT)
out.mkdir(parents=True, exist_ok=True)

#: THE CONTRACT THAT WAS IN FORCE, rebuilt from the run's own probe table --
#: `[P]` appends the probes to `contract["io"]` and the architect's file has
#: none, so replaying against the file makes every probe-reading check abstain.
contract = json.loads(Path(
    "benchmarks/baselines/i2c_master_bit_ctrl/arm_a/contract.json").read_text())
probes = json.loads((src / "probes.json").read_text()).get("probes") or []
contract["io"] = list(contract["io"]) + [
    {"name": p["name"], "dir": "probe", "width": p.get("width", 1)}
    for p in probes]
contract["probes"] = [p["name"] for p in probes]
contract_json = json.dumps(contract)

reqs = json.loads((src / "requirements.json").read_text())
requirements = reqs.get("requirements", reqs)
testplan = json.loads((src / "testplan.json").read_text())["elements"]
stim = json.loads((src / "stimulus.json").read_text())
stimulus_by_tp = {s["tp_uid"]: s["stimulus_steps"] for s in stim["testpoints"]}
normalized = {s["req_uid"]: s for s in
              json.loads((src / "normalized.json").read_text())["normalized"]}
spec = Path("benchmarks/chipverilog/Des/i2c/i2c_master_bit_ctrl/"
            "description.txt").read_text()

#: HELD STILL, NOT REDRAWN. A freshly drawn witness is a different reading of
#: the same requirements, so a check could be accepted in one run of this and
#: rejected in the next for no reason anyone could name.
for name in ("witness.py",):
    if (src / name).is_file():
        shutil.copy2(src / name, out / name)
if (src / "population").is_dir():
    shutil.copytree(src / "population", out / "population", dirs_exist_ok=True)
    for extra in sorted((out / "population").glob("_gen*")):
        shutil.rmtree(extra, ignore_errors=True)
have = len(list((out / "population").glob("*.py"))) if (out / "population").is_dir() else 0
print(f"{len(requirements)} requirement(s), {len(testplan)} testpoint(s), "
      f"{len(normalized)} normalized form(s), {len(probes)} probe(s)")
print(f"carried over: witness {(out / 'witness.py').is_file()}, "
      f"population {have} of {POP} requested")
print(f"population {POP}, cells {CELLS}, repair attempts {ATTEMPTS}, "
      f"extra drafts {DRAFTS}\n", flush=True)

port = make_port("api", OUT / "agent_io", settings=PortSettings())
oracle_set = run_oracle_stage(
    requirements=requirements, contract_json=contract_json, contract=contract,
    testplan=testplan, stimulus_by_tp=stimulus_by_tp,
    port=port, workdir=out, base=choose_base(contract),
    normalized=normalized, spec=spec,
    control_source=None,
    want_variants=False, want_correspondence=False,
    demote_faithfulness=True,
    repair_attempts=ATTEMPTS,
    population=(), population_size=POP, cell_budget=CELLS, selection=None,
    extra_drafts=DRAFTS,
    #: **NOT `rewrite=True`, WHICH WOULD UNLINK THE WITNESS.** `rewrite`
    #: deletes `witness.py` along with the artifact, so it would regenerate the
    #: very thing this driver copies in to hold fixed -- and a freshly drawn
    #: witness is a different reading of the same requirements, which is how a
    #: check gets accepted in one run of this and rejected in the next for no
    #: reason anyone could name. `OUT` is emptied before each run instead, so
    #: there is no stale artifact for `freeze` to refuse to overwrite.
    run_dir=OUT, fanout=True, rewrite=False,
)
print(f"\nTRUSTED {len(oracle_set.trusted)}", flush=True)
print("dispositions:",
      dict(collections.Counter(oracle_set.dispositions.values())))
corp = getattr(oracle_set, "corpus", {}) or {}
arms = collections.Counter(b.arm for v in corp.values() for b in v)
print(f"corpus {sum(len(v) for v in corp.values())} bodies / {len(corp)} reqs, "
      f"provenance {dict(arms)}")
prefix = collections.Counter(
    str(v).split(":")[0][:60] for v in (oracle_set.reasons or {}).values())
print("reason prefixes:", dict(prefix.most_common(8)))

control = Path("benchmarks/controls/i2c_master_bit_ctrl/ref_model.py")
card = SC.score(
    oracles=[{"req_uid": o.req_uid, "tp_uids": list(o.tp_uids),
              "clause": o.clause, "source": o.source}
             for o in oracle_set.trusted],
    normalized=list(normalized.values()), stimulus_by_tp=stimulus_by_tp,
    contract=contract,
    population=[p.read_text() for p in sorted((out / "population").glob("*.py"))],
    audit_control=control.read_text() if control.is_file() else None)
SC.write(OUT, card)
print("\n" + SC.render(card))
print(f"\nTARGET span > 90%, blindness < 10%, audit = 0: "
      f"{'MET' if card.meets(span=0.9, blindness=0.1, audit=0.0) else 'NOT MET'}")
