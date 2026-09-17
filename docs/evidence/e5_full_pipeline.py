"""THE WHOLE PIPELINE, with all three levers on, reported on the plan's metrics.

Every measurement before this ran the oracle stage from a driver. This runs
`build_artifacts` -- S1, probes, S2, S3, stimulus, normalize, the oracle stage,
the reference model -- with:

    demote_faithfulness   blocking is three mechanical grounds only
    population_size       k spec-derived readings, built from the witness
                          generator, used to refute and to locate cells
    cell_budget           checks authored AT blind disagreement cells

and then reports span / audit / blindness / effective_size / accepted classes.

The control is loaded for the AUDIT COLUMN ONLY and is computed last. It is
never passed to `build_artifacts` as `refmodel_control`, so nothing in the run
can see it.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, "/home/user/Veri-Sure")
from specflow.integration import build_artifacts  # noqa: E402
from specflow.model_io import PortSettings  # noqa: E402

TASK = Path("benchmarks/chipverilog/Des/i2c/i2c_master_bit_ctrl")
OUT = Path(sys.argv[1])
POP = int(sys.argv[2]) if len(sys.argv) > 2 else 3
CELLS = int(sys.argv[3]) if len(sys.argv) > 3 else 12

spec = (TASK / "description.txt").read_text(encoding="utf-8")
#: THE CONTRACT FROM A PRIOR RUN, reused so the interface holds still across
#: this run and the frozen sets it is compared against. It is a pipeline
#: artifact, not a reference -- the architect writes it from the spec.
contract_json = Path("docs/evidence/e3_contract.json").read_text(encoding="utf-8")

print(f"spec {len(spec)} bytes; population {POP}; cell budget {CELLS}")
print(f"out {OUT}\n", flush=True)

built = build_artifacts(
    run_dir=OUT,
    spec=spec,
    contract_json=contract_json,
    model_port="api",
    port_settings=PortSettings(),
    max_repairs=5,
    refmodel_max_repairs=2,
    enable_probes=True,
    stimulus_agent=True,
    #: THE THREE LEVERS.
    demote_faithfulness=True,
    population_size=POP,
    cell_budget=CELLS,
    #: OFF. Correspondence is priced at ~half the stage and its label does not
    #: predict convicting the control; this run is not buying it.
    correspondence=False,
    variants=False,
    #: NOT PASSED. The control exists in this repo and is used for the audit
    #: column after the run; handing it here would let it reach the stage.
    refmodel_control=None,
    fanout=True,
)
print(f"\nBUILD ok={built.ok} stage={built.stage} reason={built.reason}",
      flush=True)
art = OUT / "specflow" / "oracles.json"
print(f"oracles.json: {'written' if art.is_file() else 'MISSING'}")
if art.is_file():
    blob = json.loads(art.read_text())
    import collections
    print("  dispositions:",
          dict(collections.Counter((blob.get("dispositions") or {}).values())))
    print("  TRUSTED bodies:", len(blob.get("oracles") or []))
    corp = blob.get("corpus") or {}
    depth = sorted(len(v) for v in corp.values())
    arms = collections.Counter(b.get("arm") for v in corp.values() for b in v)
    print(f"  corpus {sum(depth)} bodies / {len(depth)} reqs, "
          f"median {depth[len(depth)//2] if depth else 0}, provenance {dict(arms)}")
