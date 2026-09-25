# ruff: noqa: F821
"""E0b + E2 through the SHIPPED stage: corpus depth, and both admission arms.

E2 was measured by hand-assembling `run_oracle_gen` + `correspondence`. This
drives `run_oracle_stage` itself, twice on identical inputs, so the numbers come
out of the code path a run uses -- and because the stage retains a corpus, it
also answers E0b: how much larger is a run's corpus than its frozen set?

E0b pre-registered: `placement` selected 151 from 464 bodies over 87
requirements, a median near 5 per requirement. A run median of 1 means selection
has nothing to choose from per requirement.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, "/home/user/Veri-Sure")
exec(open("docs/evidence/e4b_constriction.py").read().split("# ---- the ladder")[0])
from specflow import oracles_stage as O  # noqa: E402
from specflow.model_io import PortSettings, make_port  # noqa: E402

E3 = Path("docs/evidence/e3")
reqs = json.loads((E3 / "requirements.json").read_text())
norm = json.loads((E3 / "normalized.json").read_text())
CONTRACT = json.loads(Path("docs/evidence/e3_contract.json").read_text())
LIMIT = int(sys.argv[2]) if len(sys.argv) > 2 else 20
wanted = [r for r in reqs if r["uid"] in norm][:LIMIT]

#: the witness is a spec-derived design, which is what `_witness` generates.
WITNESS = Path("docs/evidence/h-i2c.ref_model.py").read_text()
testplan = [{"uid": tp, "covers": [f"{r['uid']}@1" for r in wanted]}
            for tp in TESTPOINTS]
stim = {tp: [row["inputs"] for row in designs[sorted(designs)[0]][tp]]
        for tp in TESTPOINTS}

#: the stage generates its own witness; supply a spec-derived one instead so
#: both arms replay against the same conforming implementation and the only
#: difference between them is the flag.
O._witness = lambda **_kw: (WITNESS, O.WITNESS)

out = {}
for demote in (False, True):
    root = Path(sys.argv[1]) / ("demoted" if demote else "gated")
    root.mkdir(parents=True, exist_ok=True)
    port = make_port("api", root, None, PortSettings())
    got = O.run_oracle_stage(
        requirements=wanted, contract_json=json.dumps(CONTRACT),
        contract=CONTRACT, testplan=testplan, stimulus_by_tp=stim, port=port,
        normalized=norm, workdir=root, base="step",
        run_dir=root, want_correspondence=True, demote_faithfulness=demote,
        max_repairs=1, repair_attempts=1, fanout=True)
    rates = got.rates()
    depth = [len(v) for v in got.corpus.values()]
    depth.sort()
    arm = "demoted" if demote else "gated"
    out[arm] = {"rates": {k: v for k, v in rates.items()},
                "corpus_bodies": sum(depth), "corpus_reqs": len(depth),
                "median_depth": depth[len(depth) // 2] if depth else 0,
                "labels": len(got.labels)}
    print(f"\n[{arm}] trusted={rates['trusted']} considered={rates['considered']} "
          f"labels={len(got.labels)}")
    print(f"  corpus: {sum(depth)} bodies over {len(depth)} requirements, "
          f"median depth {depth[len(depth)//2] if depth else 0}, max {max(depth) if depth else 0}")
    print(f"  dispositions: "
          f"{ {k: v for k, v in rates.items() if k.isupper()} }")

json.dump(out, open("docs/evidence/e0b-stage-both-arms.json", "w"), indent=2)
print("\nE0b: a run's corpus depth per requirement is the median above; "
      "`placement` needed a median near 5 to have anything to select from.")
