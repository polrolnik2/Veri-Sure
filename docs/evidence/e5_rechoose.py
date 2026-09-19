"""Re-choose a completed run's bodies with the CURRENT rule, and score both.

The pipeline chooses each requirement's body at freeze. When that rule changes,
this says what the change is worth on a run already paid for -- the corpus, the
population and the stimulus are the run's own, so the two scorecards differ in
the RULE and in nothing else. Zero model calls.

    python docs/evidence/e5_rechoose.py

It is a measurement and not a pipeline: the numbers a run reports are the ones
its own `scorecard.json` carries. What this is for is deciding whether a rule
change is worth another four hours before spending them.

Measured when the chooser learned to pass over a body the whole population
refutes:

    as the run froze it          span  99.1%   blind 1.4%   audit 2/14
    refuted bodies passed over   span 100.0%   blind 5.7%   audit 0/16

Blindness rose because those bodies were closing cells BY convicting: a check
refuted overall still separates a pair at one testpoint, so marginal gain
rewards it. That is the recorded way this metric was gamed, arriving through
the per-testpoint predicate.
"""
import json
import sys
from pathlib import Path
sys.path.insert(0, "/home/user/Veri-Sure")
from specflow import oracles_stage as OS
from specflow import scorecard as SC
from specflow.refmodel.oracle_gen import RequirementOracle

E, F = Path("docs/evidence/e5"), Path("docs/evidence/e5full")
contract = json.loads(Path(
    "benchmarks/baselines/i2c_master_bit_ctrl/arm_a/contract.json").read_text())
pr = json.loads((E/"real-probes.json").read_text())["probes"]
contract["io"] = list(contract["io"]) + [
    {"name": p["name"], "dir": "probe", "width": p.get("width", 1)} for p in pr]
contract["probes"] = [p["name"] for p in pr]
stim = json.loads((E/"real-stimulus.json").read_text())
stimulus_by_tp = {s["tp_uid"]: s["stimulus_steps"] for s in stim["testpoints"]}
o = json.loads((E/"real-oracles.json").read_text())
reqs = json.loads((E/"real-requirements.json").read_text())["requirements"]
norm = json.loads((E/"real-normalized.json").read_text())["normalized"]
population = [p.read_text() for p in sorted((F/"population").glob("*.py"))]
held = {x["req_uid"]: RequirementOracle(
    req_uid=x["req_uid"], tp_uids=list(x["tp_uids"]), clause=x.get("clause",""),
    source=x["source"]) for x in o["oracles"]}
corpus = {u: [OS.CorpusBody(req_uid=u, source=b["source"], arm=b.get("arm",""),
                            round_=int(b.get("round", 0)))
              for b in bodies] for u, bodies in o["corpus"].items()}
base = SC.choose_base(contract)
print(f"{len(held)} frozen, {sum(len(v) for v in corpus.values())} bodies, "
      f"{len(population)} designs", flush=True)

control = Path("benchmarks/controls/i2c_master_bit_ctrl/ref_model.py").read_text()

def card(h, label):
    c = SC.score(oracles=[{"req_uid": u, "tp_uids": list(x.tp_uids),
                           "clause": x.clause, "source": x.source}
                          for u, x in h.items()],
                 normalized=norm, stimulus_by_tp=stimulus_by_tp,
                 contract=contract, population=population, requirements=reqs,
                 audit_control=control)
    print(f"\n{label}\n" + SC.render(c))
    print(f"  TARGET: {'MET' if c.meets(span=0.9, blindness=0.1, audit=0.0) else 'NOT MET'}",
          flush=True)

card(dict(held), "as the run froze it")
again = dict(held)
for uid, body in OS._choose_bodies(
        corpus=corpus, held=again, population=population, contract=contract,
        stimulus_by_tp=stimulus_by_tp, base=base, transactional=True).items():
    again[uid] = body
card(again, "re-chosen, refuted bodies passed over")
