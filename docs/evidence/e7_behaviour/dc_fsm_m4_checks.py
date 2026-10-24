"""dc_fsm_m4_checks.py -- why no shipped dc_fsm check catches M4 (biu_read gated by load), per corpus.

M4 (qualitative/or1200_dc_fsm.md): golden raises biu_read in a STORE's miss-evaluation cycle
(biu_read = hitmiss_eval & tagcomp_miss | ~hitmiss_eval & load); most designs gate it by load.
The checks that restate the spec's formula sentence are replayed here on every testpoint of the
run's stimulus, against the run's reference model and the population of independently written
spec-derived designs (`specflow/population/`, 7 per run) -- the replay the shipping rule ("no
body a majority of the population convicts") decides by. For each design: failures, and how many
of them fall on a store's miss-evaluation edge with biu_read low (M4). Counts only.
-> docs/evidence/e7/DC-FSM-M4-CHECKS.json
"""

import json
import os
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from specflow.refmodel.compose import choose_base  # noqa: E402
from specflow.refmodel.oracles import RequirementOracle, decide, replay  # noqa: E402

EQ = Path(os.environ.get("E7_BEHAVIOUR_WORK", "/tmp/e7_behaviour"))
RUNS = Path(os.environ.get("E7_RUNS", "/home/user/runs-cf"))
E = Path(__file__).resolve().parents[1] / "e7"
#: the formula sentence's checks: luna12 REQ-0033, luna13 REQ-0031 (shipped), luna14 REQ-0032
CHECKS = {"luna12": "REQ-0033", "luna13": "REQ-0031", "luna14": "REQ-0032"}

out = {}
for run, q in CHECKS.items():
    d = RUNS / run / "or1200_dc_fsm"
    contract = json.loads((d / "contract.json").read_text())
    base = choose_base(contract)
    pool = json.loads((d / "oracles.json").read_text())
    pool = pool.get("oracles", pool) if isinstance(pool, dict) else pool
    o = next(x for x in pool if x["req_uid"] == q)
    orc = RequirementOracle(req_uid=q, tp_uids=[], clause=o["clause"], source=o["source"])
    shipped = json.loads((d / "shipped.json").read_text())
    st = json.loads((d / "stimulus.json").read_text())
    st = st["testpoints"] if isinstance(st, dict) else st
    steps = {t["tp_uid"]: t["stimulus_steps"] for t in st if t.get("stimulus_steps")}
    designs = [("reference model", (d / "ref_model.py").read_text())] + [
        (f"population {f.stem}", f.read_text())
        for f in sorted((EQ / "corpora" / run / "or1200_dc_fsm" / "population").glob("*.py"))]
    rows = {}
    for name, src in designs:
        fail = m4 = 0
        why = Counter()
        for s in steps.values():
            try:
                tr = replay(src, contract, s, base=base).rows
            except Exception:  # noqa: BLE001 -- a design that cannot replay decides nothing
                continue
            v = decide(orc, tr)
            if v.ok is False:
                fail += 1
                why[v.detail[:60]] += 1
                r = next((x for x in tr if x.get("edge") == v.edge), None)
                m4 += bool(r and r["outputs"].get("store") == 1 and r["outputs"].get("hitmiss_eval") == 1
                           and r["outputs"].get("biu_read") == 0)
        rows[name] = {"fails": fail, "at_store_miss_eval": m4, "reason": why.most_common(1)[0][0] if why else ""}
    pop = [v for k, v in rows.items() if k.startswith("population")]
    out[run] = {"check": q, "clause": o["clause"][:160], "shipped": q in shipped["keys"],
                "excluded_by_population": q in shipped["refuted_excluded"], "testpoints": len(steps),
                "population_convicted": sum(v["fails"] > 0 for v in pop), "population": len(pop), "designs": rows}
    print(f"{run} {q}: shipped {out[run]['shipped']}, excluded by the population {out[run]['excluded_by_population']}; "
          f"population convicted {out[run]['population_convicted']} of {len(pop)}")
    for name, v in rows.items():
        print(f"   {name}: fails {v['fails']} testpoints, {v['at_store_miss_eval']} at a store's miss evaluation; {v['reason']}")
(E / "DC-FSM-M4-CHECKS.json").write_text(json.dumps(out, indent=1) + "\n")

# ---------------------------------------------------------------- how common is M4 in each population?
#: luna14 REQ-0032 is golden's formula; replayed on every corpus it reads M4 in any design whose
#: probes it can see (all three contracts expose hitmiss_eval, load and store).
src14 = next(x for x in (lambda p: p.get("oracles", p) if isinstance(p, dict) else p)(
    json.loads((RUNS / "luna14" / "or1200_dc_fsm" / "oracles.json").read_text())) if x["req_uid"] == "REQ-0032")["source"]
probe = RequirementOracle(req_uid="M4", tp_uids=[], clause="golden's biu_read formula (luna14 REQ-0032)", source=src14)
print("\nluna14's correct check on every corpus (designs convicted at a store's miss evaluation):")
out["prevalence"] = {}
for run in CHECKS:
    d = RUNS / run / "or1200_dc_fsm"
    contract = json.loads((d / "contract.json").read_text())
    st = json.loads((d / "stimulus.json").read_text())
    st = st["testpoints"] if isinstance(st, dict) else st
    designs = [("reference model", (d / "ref_model.py").read_text())] + [
        (f"population {f.stem}", f.read_text())
        for f in sorted((EQ / "corpora" / run / "or1200_dc_fsm" / "population").glob("*.py"))]
    got = {}
    for name, src in designs:
        m4 = 0
        for t in st:
            if not t.get("stimulus_steps"):
                continue
            try:
                tr = replay(src, contract, t["stimulus_steps"], base=choose_base(contract)).rows
            except Exception:  # noqa: BLE001
                continue
            v = decide(probe, tr)
            r = next((x for x in tr if x.get("edge") == v.edge), None) if v.ok is False else None
            m4 += bool(r and r["outputs"].get("store") == 1 and r["outputs"].get("hitmiss_eval") == 1
                       and r["outputs"].get("biu_read") == 0)
        got[name] = m4
    out["prevalence"][run] = got
    pop = [v for k, v in got.items() if k.startswith("population")]
    print(f"   {run}: reference model {'M4' if got['reference model'] else 'correct'}; population "
          f"{sum(v > 0 for v in pop)} of {len(pop)} carry M4")
(E / "DC-FSM-M4-CHECKS.json").write_text(json.dumps(out, indent=1) + "\n")
