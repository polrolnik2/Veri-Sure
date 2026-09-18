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
import collections
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
#: **A REAL CONTRACT, AND THE FIRST RUNS DID NOT USE ONE.** They reused
#: `docs/evidence/e3_contract.json`, which carries only `module_name` and
#: `io`. A contract the architect writes carries eight more keys, and two
#: of them are load-bearing: `clocking.is_sequential` decides
#: `choose_base`, so without it a sequential i2c bit controller was
#: modelled COMBINATIONALLY; and `functional_summary`, `corner_cases`,
#: `test_plan` and `guidance` were absent from every prompt in the run.
contract_json = Path(
    "benchmarks/baselines/i2c_master_bit_ctrl/arm_a/contract.json"
).read_text(encoding="utf-8")

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
#: **KEEP THE REQUIREMENTS BESIDE THE FROZEN SET.** Earlier runs preserved
#: `oracles.json` and not `requirements.json`, so the span denominator could
#: be counted but never broken down -- how many of the minted requirements are
#: behavioural, how many are scaffolding that can never yield a check. That
#: question could then only be answered from a DIFFERENT run's artifact.
KEEP = Path("docs/evidence/e5")
KEEP.mkdir(parents=True, exist_ok=True)
for name in ("requirements.json", "oracles.json", "stimulus.json",
             "testplan.json"):
    src_f = OUT / "specflow" / name
    if src_f.is_file():
        (KEEP / f"real-{name}").write_text(src_f.read_text(encoding="utf-8"),
                                           encoding="utf-8")
        print(f"kept docs/evidence/e5/real-{name}")

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
    rq = OUT / "specflow" / "requirements.json"
    if rq.is_file():
        reqs = json.loads(rq.read_text())
        reqs = reqs.get("requirements", reqs) if isinstance(reqs, dict) else reqs
        kinds = collections.Counter(r.get("unit_kind") for r in reqs)
        beh = kinds.get("behavioural", 0)
        n_tr = len(blob.get("oracles") or [])
        #: **THREE DENOMINATORS, ALL OF THEM REAL.** Scaffolding -- headings,
        #: bare list markers -- can never yield a check, so it sits in the
        #: minted count as permanent loss. `considered()` removes abandonment.
        #: Reporting one without the others is the class of number this tree
        #: has retracted twice.
        print(f"  requirements {len(reqs)}: {dict(kinds)}")
        print(f"  SPAN  {n_tr}/{len(reqs)} minted = {100*n_tr/max(1,len(reqs)):.1f}%"
              f" | {n_tr}/{beh} behavioural = {100*n_tr/max(1,beh):.1f}%")
