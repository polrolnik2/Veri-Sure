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
import logging
import sys
from pathlib import Path

#: **THE PIPELINE'S OWN PROGRESS, ON STDOUT.** Every stage reports what it is
#: doing through `logger.info` and this driver configured no logging, so a
#: three-hour run printed one line at the start and one at the end -- which is
#: how a cell-authoring leg came to produce nothing with the only two lines
#: that would have said so going nowhere. Filtered to the pipeline's own
#: loggers, because the OpenAI client is chatty at INFO and drowns them.
logging.basicConfig(level=logging.WARNING, format="%(message)s",
                    stream=sys.stdout)
for _name in ("specflow.oracles_stage", "specflow.scorecard",
              "specflow.integration", "specflow.probes",
              "specflow.refmodel.liveness"):
    logging.getLogger(_name).setLevel(logging.INFO)

sys.path.insert(0, "/home/user/Veri-Sure")
from specflow.integration import build_artifacts  # noqa: E402
from specflow.model_io import PortSettings  # noqa: E402

TASK = Path("benchmarks/chipverilog/Des/i2c/i2c_master_bit_ctrl")
OUT = Path(sys.argv[1])
#: **SEVEN, NOT THREE, AND THE SWEEP SAYS WHY.** Refutation requires the check
#: to convict EVERY member, so a bigger population makes unanimity both rarer
#: and stronger: on the probe run's own frozen 96, over the wide replay scope,
#:
#:     k   cells   refuted   blind(all set)
#:     3    3530        47            22.3%
#:     5   13546        45            19.3%
#:     7   37288        41            10.4%
#:     9   62932        40            11.2%
#:
#: More readings means fewer good checks lost to a coincidence of three, and
#: more of the design space in the blindness denominator. Nine buys nothing
#: over seven here and costs 69% more replay.
POP = int(sys.argv[2]) if len(sys.argv) > 2 else 7
#: **FORTY, NOT TWELVE.** A cell check is taken when it separates strictly
#: more than the body it would replace, so the budget is how many requirements
#: get the chance. At 12 the leg authored 12 and adopted 6; at 40 it authored
#: 40 and adopted 5 more, and the run's blindness went 49.1% -> 20.4%.
CELLS = int(sys.argv[3]) if len(sys.argv) > 3 else 40
#: SET-LEVEL repair attempts. The default is 2 and nothing ever passed it --
#: `build_artifacts` did not forward `repair_attempts` at all until this run.
#: Over-strictness is what needs the extra round: at the wide scope 47 of 96
#: frozen checks are refuted by the whole population, and each attempt costs
#: about one call per still-rejected check.
ATTEMPTS = int(sys.argv[4]) if len(sys.argv) > 4 else 3
#: ONE EXTRA FIRST DRAFT PER REQUIREMENT, kept in the corpus and never held --
#: the pool `_choose_bodies` selects from. One call per requirement.
DRAFTS = int(sys.argv[5]) if len(sys.argv) > 5 else 1

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

#: THE CONTROL, FOR THE SCORECARD'S AUDIT COLUMN AND FOR NOTHING ELSE. It goes
#: in as `audit_control`, which reaches `scorecard.score` -- a module with no
#: author, no prompt and no repair path -- and NOT as `refmodel_control`, which
#: reaches the oracle stage and can reject. A control may REJECT an oracle and
#: may never REPAIR one; here it does not even reject, it only scores.
CONTROL = Path("benchmarks/controls/i2c_master_bit_ctrl/ref_model.py")
control_source = CONTROL.read_text() if CONTROL.is_file() else None

print(f"spec {len(spec)} bytes; population {POP}; cell budget {CELLS}; "
      f"repair attempts {ATTEMPTS}; extra drafts {DRAFTS}; "
      f"control {'loaded for the audit column' if control_source else 'ABSENT'}")
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
    oracle_repair_attempts=ATTEMPTS,
    oracle_extra_drafts=DRAFTS,
    audit_control=control_source,
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
#:
#: **AND KEEP THEM UNDER THE RUN THAT PRODUCED THEM.** `docs/evidence/e5` is a
#: fixed path, so every run overwrote the previous one's artifacts -- including
#: the corpus the previous run's published figures were computed from and the
#: only input `e5_rechoose.py` can be re-run against. A second copy goes to a
#: directory named for `--out`, which is per-run by construction.
KEEP = Path("docs/evidence/e5")
MINE = Path("docs/evidence") / f"e5run-{OUT.name}"
KEEP.mkdir(parents=True, exist_ok=True)
MINE.mkdir(parents=True, exist_ok=True)
for name in ("requirements.json", "oracles.json", "stimulus.json",
             "testplan.json", "normalized.json", "probes.json",
             "scorecard.json"):
    src_f = OUT / "specflow" / name
    if src_f.is_file():
        body = src_f.read_text(encoding="utf-8")
        (KEEP / f"real-{name}").write_text(body, encoding="utf-8")
        (MINE / name).write_text(body, encoding="utf-8")
        print(f"kept docs/evidence/e5/real-{name} and {MINE}/{name}")

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


#: THE TRIPLE, AS THE RUN ITSELF COMPUTED IT. Not re-derived here: a number a
#: run cannot produce about itself is a number nobody can reproduce, and every
#: figure on this branch before the scorecard was taken afterwards by a driver
#: against inputs the driver chose.
card_path = OUT / "specflow" / "scorecard.json"
if card_path.is_file():
    from specflow.scorecard import Scorecard, render  # noqa: E402

    card = Scorecard(**json.loads(card_path.read_text()))
    print("\n" + render(card))
    print(f"\nTARGET span > 90%, blindness < 10%, audit = 0: "
          f"{'MET' if card.meets(span=0.9, blindness=0.1, audit=0.0) else 'NOT MET'}")
else:
    print("\nscorecard.json: MISSING -- the run could not score itself")
