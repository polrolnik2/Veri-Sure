# ruff: noqa: F821
"""E2: does admitting what the faithfulness gate rejects cost audit?

E0 established this cannot be priced from the surviving artifacts: liveness
verdicts exist for 15/15 and 24/24 KEPT checks and 0/8 and 0/19 DISCARDED ones,
and only TRUSTED bodies are stored. So the rejected checks have to be generated
fresh, which is what this does -- on E3's requirements, against the nine
spec-derived designs, with the known-good control supplying the audit column
last and feeding nothing.

PRE-REGISTERED, from the plan:
  audit no worse on the admitted set => the gate was discarding at random with
      respect to soundness, and admission is a clean gain;
  audit worse                        => the gate was constricting toward the
      correct class, the label must carry weight in the debug loop, and this is
      reported as a TRADE, not a win;
  blindness unimproved               => the admitted checks object where the
      kept ones already do, and the span gain is NOMINAL.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, "/home/user/Veri-Sure")
exec(open("docs/evidence/e4b_constriction.py").read().split("# ---- the ladder")[0])
from specflow import variety as V  # noqa: E402
from specflow.model_io import PortSettings, make_port  # noqa: E402
from specflow.refmodel import correspondence as C  # noqa: E402
from specflow.refmodel.oracle_gen import run_oracle_gen  # noqa: E402
from specflow.refmodel.oracles import decide  # noqa: E402

E3 = Path("docs/evidence/e3")
reqs = json.loads((E3 / "requirements.json").read_text())
norm = json.loads((E3 / "normalized.json").read_text())
CONTRACT = json.loads(Path("docs/evidence/e3_contract.json").read_text())
LIMIT = int(sys.argv[3]) if len(sys.argv) > 3 else 20
wanted = [r for r in reqs if r["uid"] in norm][:LIMIT]
print(f"E2: {len(wanted)} requirements with a normalized form")

port = make_port("api", Path(sys.argv[1]), None, PortSettings())
testplan = [{"uid": tp, "covers": [f"{r['uid']}@1" for r in wanted]}
            for tp in TESTPOINTS]
stim = {tp: [row["inputs"] for row in designs[sorted(designs)[0]][tp]]
        for tp in TESTPOINTS}

oracles, _ = run_oracle_gen(
    requirements=wanted, contract_json=json.dumps(CONTRACT), contract=CONTRACT,
    testplan=testplan, port=port, normalized=norm, conforming_source="",
    stimulus_by_tp=stim, base="step", max_repairs=1, fanout=True)
print(f"  authored {len(oracles)} oracles")

reviews = C.review(oracles, {r["uid"]: r for r in wanted}, port=port,
                   normalized=norm, contract=CONTRACT, fanout=True)
rejected = {o.req_uid: C.rejects(reviews[o.req_uid])
            for o in oracles if o.req_uid in reviews
            and C.rejects(reviews[o.req_uid])}
print(f"  correspondence rejects {len(rejected)} of {len(oracles)}")

# ---- the audit column, computed LAST and feeding nothing -----------------
def profile(o):
    per = {}
    for d, rows in designs.items():
        vals = [decide(o, rows[tp]).ok for tp in TESTPOINTS]
        vals = [v for v in vals if v is not None]
        per[d] = False if any(v is False for v in vals) else (True if vals else None)
    convicts_control = any(decide(o, control[tp]).ok is False for tp in TESTPOINTS)
    return per, convicts_control

kept_v, adm_v, kept_bad, adm_bad = {}, {}, 0, 0
for o in oracles:
    per, bad = profile(o)
    if o.req_uid in rejected:
        adm_v[o.req_uid] = per
        adm_bad += bad
    else:
        kept_v[o.req_uid] = per
        kept_bad += bad

def rate(n, d):
    return f"{100*n/d:.1f}%" if d else "n/a"

print(f"\n{'arm':12} {'checks':>7} {'convict the control':>20} {'blind':>8}")
print(f"{'KEPT':12} {len(kept_v):>7} "
      f"{rate(kept_bad, len(kept_v)):>20} "
      f"{100*len(V.blind(cells, kept_v))/len(cells):>7.1f}%")
print(f"{'ADMITTED':12} {len(adm_v):>7} "
      f"{rate(adm_bad, len(adm_v)):>20} "
      f"{100*len(V.blind(cells, adm_v))/len(cells):>7.1f}%")
both = {**kept_v, **adm_v}
print(f"{'UNION':12} {len(both):>7} "
      f"{rate(kept_bad + adm_bad, len(both)):>20} "
      f"{100*len(V.blind(cells, both))/len(cells):>7.1f}%")
json.dump({"kept": len(kept_v), "kept_convict_control": kept_bad,
           "admitted": len(adm_v), "admitted_convict_control": adm_bad,
           "rejected_reasons": rejected}, open(sys.argv[2], "w"), indent=2)
