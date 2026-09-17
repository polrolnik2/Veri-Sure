# ruff: noqa: F821,E402
"""E2, redone on an UNBIASED population.

The first E2 ran the stage on 20 requirements that were ALL span-naming,
because E3 had normalized only the windowed ones. That is 17% of the module,
drawn entirely from the population E3 measured as 65.9% defective -- exactly
where correspondence over-rejects and where demoting therefore recovers most.
Span 6 -> 14 was measured on the worst case and is plausibly inflated.

This normalizes the remaining requirements so the pool is the whole module, then
re-runs both arms on a seeded sample drawn across all of it.

PRE-REGISTERED, unchanged from the plan:
  audit no worse on the admitted set => the gate discarded at random w.r.t.
      soundness and admission is a clean gain;
  audit worse                        => the gate constricted toward the correct
      class; a TRADE, not a win;
  blindness unimproved               => the admitted checks object where the
      kept ones already do and the span gain is NOMINAL.
AND, new to this run: if the demotion effect is materially smaller here than the
6 -> 14 measured on the windowed subset, the first E2 was a sampling artifact
and is corrected rather than confirmed.
"""
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, "/home/user/Veri-Sure")
exec(open("docs/evidence/e4b_constriction.py").read().split("# ---- the ladder")[0])
from specflow import oracles_stage as O
from specflow.model_io import PortSettings, make_port
from specflow.normalize import _names_a_window, run_normalize_fanout

E3 = Path("docs/evidence/e3")
SC = Path(sys.argv[1])
reqs = json.loads((E3 / "requirements.json").read_text())
have = json.loads((E3 / "normalized.json").read_text())
CONTRACT = json.loads(Path("docs/evidence/e3_contract.json").read_text())
CJ = json.dumps(CONTRACT)

rest = [r for r in reqs if r["uid"] not in have]
print(f"module: {len(reqs)} requirements; {len(have)} already normalized "
      f"(windowed only); normalizing the remaining {len(rest)}")
print(f"  of the remaining, {sum(1 for r in rest if _names_a_window(r['text']))} "
      f"name a span (should be ~0 -- they are the non-windowed ones)")

port = make_port("api", SC / "norm_rest", None, PortSettings())
more, _ = run_normalize_fanout(requirements=rest, contract_json=CJ,
                               contract=CONTRACT, port=port, max_repairs=2)
have.update({n.req_uid: json.loads(n.model_dump_json()) for n in more})
(E3 / "normalized-all.json").write_text(json.dumps(have, indent=2))
print(f"  normalized now covers {len(have)} of {len(reqs)} requirements")

#: A SEEDED SAMPLE ACROSS THE WHOLE MODULE, not the head of a windowed list.
pool = [r for r in reqs if r["uid"] in have]
random.Random(20260917).shuffle(pool)
N = int(sys.argv[2]) if len(sys.argv) > 2 else 40
sample = pool[:N]
w = sum(1 for r in sample if _names_a_window(r["text"]))
print(f"\nsample: {len(sample)} of {len(pool)}; span-naming {w} = "
      f"{100*w/len(sample):.0f}% (the module's own rate is 36.5%; "
      f"the first E2 was 100%)")

WITNESS = Path("docs/evidence/h-i2c.ref_model.py").read_text()
O._witness = lambda **_kw: (WITNESS, O.WITNESS)
testplan = [{"uid": tp, "covers": [f"{r['uid']}@1" for r in sample]}
            for tp in TESTPOINTS]
stim = {tp: [row["inputs"] for row in designs[sorted(designs)[0]][tp]]
        for tp in TESTPOINTS}

out = {}
for demote in (False, True):
    arm = "demoted" if demote else "gated"
    root = SC / f"unbiased_{arm}"
    root.mkdir(parents=True, exist_ok=True)
    got = O.run_oracle_stage(
        requirements=sample, contract_json=CJ, contract=CONTRACT,
        testplan=testplan, stimulus_by_tp=stim,
        port=make_port("api", root, None, PortSettings()),
        normalized=have, workdir=root, base="step", run_dir=root,
        want_correspondence=True, demote_faithfulness=demote,
        max_repairs=1, repair_attempts=1, fanout=True)
    r = got.rates()
    depth = sorted(len(v) for v in got.corpus.values())
    out[arm] = {"trusted": r["trusted"], "considered": r["considered"],
                "labels": len(got.labels), "sample": len(sample),
                "dispositions": {k: v for k, v in r.items() if k.isupper()},
                "corpus_bodies": sum(depth), "corpus_reqs": len(depth),
                "median_depth": depth[len(depth) // 2] if depth else 0}
    print(f"\n[{arm}] TRUSTED {r['trusted']} of {len(sample)}"
          f"   considered {r['considered']}   labels {len(got.labels)}")
    print(f"  corpus {sum(depth)} bodies / {len(depth)} reqs, "
          f"median depth {depth[len(depth)//2] if depth else 0}")
    print(f"  {out[arm]['dispositions']}")

g, d = out["gated"]["trusted"], out["demoted"]["trusted"]
print(f"\nSPAN: {g} -> {d} of {len(sample)} "
      f"({100*g/len(sample):.0f}% -> {100*d/len(sample):.0f}%)")
print("  the windowed-only run measured 6 -> 14 of 20 (30% -> 70%)")
json.dump(out, open("docs/evidence/e2-unbiased.json", "w"), indent=2)
