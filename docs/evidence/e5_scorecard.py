"""Score a COMPLETED run with the pipeline's own scorecard.

For a run that predates the stage, or to re-score one after a measurement fix.
A live run writes `scorecard.json` itself and needs none of this.

    python docs/evidence/e5_scorecard.py <run_dir> [--no-control]

Reads the run's own artifacts, its own probe table and its own population --
the three things a driver got wrong before the stage existed. The control is
read for the audit column only and is never returned to anything.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, "/home/user/Veri-Sure")
from specflow import scorecard as S  # noqa: E402

RUN = Path(sys.argv[1])
WANT_CONTROL = "--no-control" not in sys.argv

art = RUN / "specflow"
orc = json.loads((art / "oracles.json").read_text())
norm = json.loads((art / "normalized.json").read_text())["normalized"]
stim = json.loads((art / "stimulus.json").read_text())
stimulus_by_tp = {s["tp_uid"]: s["stimulus_steps"]
                  for s in (stim["testpoints"] if isinstance(stim, dict) else stim)}

#: THE CONTRACT THAT WAS IN FORCE. `[P]` appends the run's probes to
#: `contract["io"]` before the oracle stage sees it, and the architect's file
#: on disk has none -- so replaying against the file makes every probe-reading
#: check abstain. A live run has the augmented contract in hand; here it is
#: rebuilt from the probe table the run wrote.
contract = json.loads(Path(
    "benchmarks/baselines/i2c_master_bit_ctrl/arm_a/contract.json").read_text())
pfile = art / "probes.json"
if pfile.is_file():
    probes = json.loads(pfile.read_text()).get("probes") or []
    contract["io"] = list(contract["io"]) + [
        {"name": p["name"], "dir": "probe", "width": p.get("width", 1)}
        for p in probes]
    contract["probes"] = [p["name"] for p in probes]
    print(f"contract: {len(probes)} probe(s) restored from the run's own table")

population = [p.read_text() for p in sorted((art / "population").glob("*.py"))
              if p.read_text().strip()]
control = None
if WANT_CONTROL:
    cp = Path("benchmarks/controls/i2c_master_bit_ctrl/ref_model.py")
    control = cp.read_text() if cp.is_file() else None

print(f"{len(orc.get('oracles') or [])} frozen check(s), {len(norm)} normalized "
      f"form(s), {len(population)} design(s), "
      f"control {'yes' if control else 'no'}", flush=True)

card = S.score(oracles=orc.get("oracles") or [], normalized=norm,
               stimulus_by_tp=stimulus_by_tp, contract=contract,
               population=population, audit_control=control)
print("\n" + S.render(card))
print(f"\nTARGET span > 90%, blindness < 10%, audit = 0: "
      f"{'MET' if card.meets(span=0.9, blindness=0.1, audit=0.0) else 'NOT MET'}")
S.write(RUN, card)
print(f"written: {RUN / 'specflow' / 'scorecard.json'}")
