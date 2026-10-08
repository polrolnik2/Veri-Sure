"""E4: author a check AT a disagreement cell, and replay it across the population.

The plan's untried half. Resampling one prompt returns 69% identical bodies among
sound pairs; varying the stimulus ROUTE was pre-registered at >=40% = lever,
<15% = closed and delivered 1 of 20 = 5%. This varies neither: it hands the
author a LOCATION the current set adjudicates nothing at, and asks what the
specification says belongs there.

**THE POPULATION IS A POINTER, NOT AN ORACLE.** `CellBrief` can only be built
through `.at()`, whose parameters are a cell, a requirement, an activation and
the driven inputs. A cell holds two design NAMES and no values, and the names
are never rendered. The author is not shown the designs, is not shown what they
did, and is never told either is correct.

Reads the first probe-bearing run's artifacts, so no stage before [O] is re-paid
for. 12 model calls. Pre-registered by the plan: <=15% fully caught closes the
authoring-at-cells line; the honest bar is the stimulus round's 5%, not 0.

    python docs/evidence/e4d_author_at_cells.py <run_dir> [budget]
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, "/home/user/Veri-Sure")
from specflow import oracles_stage as OS  # noqa: E402
from specflow import variety as V  # noqa: E402
from specflow.model_io import PortSettings, make_port  # noqa: E402
from specflow.refmodel.compose import choose_base  # noqa: E402
from specflow.refmodel.oracle_gen import RequirementOracle, run_cell_gen  # noqa: E402

RUN = Path(sys.argv[1])
BUDGET = int(sys.argv[2]) if len(sys.argv) > 2 else 12
EV = Path("docs/evidence/e5")

contract = json.loads(Path(
    "benchmarks/baselines/i2c_master_bit_ctrl/arm_a/contract.json").read_text())
#: THE CONTRACT THAT WAS IN FORCE. `[P]` appends the run's probes to
#: `contract["io"]` before the oracle stage sees it; replaying against the
#: architect's probe-free contract makes every probe-reading check abstain --
#: 82 of this run's 96 trusted checks read at least one probe -- and the same
#: instrument then reports 100% blind instead of 0.0%.
probes = json.loads((RUN / "specflow" / "probes.json").read_text())["probes"]
contract["io"] = list(contract["io"]) + [
    {"name": p["name"], "dir": "probe", "width": p.get("width", 1)} for p in probes]
contract["probes"] = [p["name"] for p in probes]
contract_json = json.dumps(contract)

population = tuple((RUN / "specflow" / "population" / f"{i}.py").read_text()
                   for i in range(3))
witness = (RUN / "specflow" / "witness.py").read_text()
orc = json.loads((EV / "real-oracles.json").read_text())
stim = json.loads((EV / "real-stimulus.json").read_text())
tpl = json.loads((EV / "real-testplan.json").read_text())
reqs = json.loads((EV / "real-requirements.json").read_text())
norm = json.loads((RUN / "specflow" / "normalized.json").read_text())["normalized"]
spec = Path("benchmarks/chipverilog/Des/i2c/i2c_master_bit_ctrl/"
            "description.txt").read_text()

testplan = tpl["elements"]
by_uid = {r["uid"]: r for r in reqs["requirements"]}
stimulus_by_tp = {s["tp_uid"]: s["stimulus_steps"] for s in stim["testpoints"]}
normalized = {s["req_uid"]: s for s in norm}
covers = {str(t.get("uid")): [str(c).split("@")[0] for c in (t.get("covers") or [])]
          for t in testplan}
held = {}
for uid, bodies in (orc.get("corpus") or {}).items():
    first = next((b for b in bodies if b.get("arm") == "generate"), None)
    if not first:
        continue
    held[uid] = RequirementOracle(
        req_uid=uid, tp_uids=[t for t, cs in covers.items() if uid in cs],
        clause=str(by_uid.get(uid, {}).get("text") or "")[:120],
        source=first["source"])

base, transactional = choose_base(contract), True
outputs = [str(p.get("name")) for p in contract["io"]
           if p.get("dir") == "output" and p.get("name")]
rows = OS._population_rows(population, contract, stimulus_by_tp,  # noqa: SLF001
                           base=base, transactional=transactional)
cells = V.cells(rows, outputs)
before_tbl = OS._population_verdicts_by_tp(  # noqa: SLF001
    held, population, contract, stimulus_by_tp, base=base,
    transactional=transactional)
before = V.blind_at(cells, before_tbl)
print(f"{len(cells)} cell(s); {len(before)} blind "
      f"= {100 * len(before) / len(cells):.1f}% before authoring", flush=True)

targets = OS._cell_targets(  # noqa: SLF001
    population=population, held=held, contract=contract,
    stimulus_by_tp=stimulus_by_tp, testplan=testplan, by_uid=by_uid,
    normalized=normalized, budget=BUDGET, base=base, transactional=transactional)
print(f"{len(targets)} target(s): "
      + ", ".join(f"{t['requirement']['uid']}@{t['cell'].testpoint}/{t['cell'].port}"
                  for t in targets), flush=True)

port = make_port("api", RUN / "agent_io", settings=PortSettings())
authored = list(run_cell_gen(
    targets=targets, contract_json=contract_json, contract=contract, port=port,
    testplan=testplan, normalized=normalized, spec=spec, siblings=by_uid,
    conforming_source=witness, stimulus_by_tp=stimulus_by_tp, base=base,
    max_repairs=2, fanout=True, label="_e4d"))
print(f"\n{len(authored)} body/bodies returned of {len(targets)} asked for\n",
      flush=True)

# ---- what each one closes, on its own -----------------------------------
blind_before = set(before)
per_body = {}
for body in authored:
    tbl = OS._population_verdicts_by_tp(  # noqa: SLF001
        {body.req_uid: body}, population, contract, stimulus_by_tp,
        base=base, transactional=transactional)
    col = tbl.get(body.req_uid) or {}
    closed = [c for c in before if V.separates_at(c, col)]
    tgt = next((t for t in targets if t["requirement"]["uid"] == body.req_uid), None)
    own = tgt["cell"] if tgt else None
    per_body[body.req_uid] = {
        "closes": len(closed),
        "closes_its_own_cell": bool(own and own in set(closed)),
        "decides_anywhere": any(
            vv is not None for c in col.values() for vv in c.values()),
    }
caught = [u for u, r in per_body.items() if r["closes_its_own_cell"]]
partly = [u for u, r in per_body.items()
          if not r["closes_its_own_cell"] and r["closes"]]
fully_blind = [u for u, r in per_body.items() if not r["closes"]]
print(f"FULLY CAUGHT  {len(caught)} of {len(targets)} targets "
      f"= {100 * len(caught) / max(1, len(targets)):.1f}%  "
      f"(pre-registered: <=15% closes the line)")
print(f"PARTLY        {len(partly)} close some cell but not their own")
print(f"FULLY BLIND   {len(fully_blind)} close nothing")
for uid, r in sorted(per_body.items()):
    print(f"   {uid:<10} closes {r['closes']:>5} cell(s), own cell "
          f"{'YES' if r['closes_its_own_cell'] else 'no '}, decides "
          f"{'yes' if r['decides_anywhere'] else 'NO'}")

# ---- and as a SET, which is the only honest aggregate --------------------
merged = dict(held)
merged.update({b.req_uid: b for b in authored})
after_tbl = OS._population_verdicts_by_tp(  # noqa: SLF001
    merged, population, contract, stimulus_by_tp, base=base,
    transactional=transactional)
after = V.blind_at(cells, after_tbl)


def effective(tbl):
    return len({json.dumps(sorted(
        ((tp, tuple(sorted(col.items()))) for tp, col in t.items())), default=str)
        for t in tbl.values() if t})


print(f"\nSET blindness  {len(before)} -> {len(after)} of {len(cells)}"
      f"  = {100 * len(before) / len(cells):.1f}% -> "
      f"{100 * len(after) / len(cells):.1f}%")
print(f"effective_size {effective(before_tbl)} -> {effective(after_tbl)}"
      "   (a count of checks is never reported in its place)")

out = Path("docs/evidence/e4d-cell-authoring.json")
out.write_text(json.dumps({
    "targets": [{"req": t["requirement"]["uid"], "tp": t["cell"].testpoint,
                 "port": t["cell"].port} for t in targets],
    "authored": {b.req_uid: b.source for b in authored},
    "per_body": per_body, "cells": len(cells),
    "blind_before": len(before), "blind_after": len(after),
    "effective_before": effective(before_tbl),
    "effective_after": effective(after_tbl),
    "fully_caught": caught, "partly": partly, "fully_blind": fully_blind,
}, indent=2))
print(f"\nwritten: {out}")
