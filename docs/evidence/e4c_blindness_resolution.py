"""Blindness at PAIR resolution against blindness at (TESTPOINT, PAIR) resolution.

Zero model calls. Reads the first probe-bearing run's own artifacts -- its three
spec-derived designs, its 151 first drafts, its stimulus and its testplan -- and
recomputes the blind-cell set both ways.

WHY IT EXISTS. That run was configured with `cell_budget=12` and a population of
three, and authored NOTHING: no cell bodies, no `agent_io` prompts, no record in
the artifact. The leg was reached and the budget arrived; `_cell_targets`
returned an empty list because `variety.blind` said no cell was blind.

**THE CONTRACT THIS FEEDS IS THE ONE THAT WAS IN FORCE, NOT THE ONE ON DISK.**
The architect's contract declares no probe; `[P]` appends the run's 16 probes to
`contract["io"]` before the oracle stage sees it. Replaying against the on-disk
contract makes every probe-reading check abstain -- 61 of 151 forms name a probe
here -- and the same instrument then reports 100% blind instead of 0.0%. Two
opposite wrong answers from one missing stage output, which is why the probe
table is rebuilt below rather than assumed away.

    python docs/evidence/e4c_blindness_resolution.py <run_dir>

`run_dir` defaults to the committed artifacts under `docs/evidence/e5` plus the
population and probe table the run left in its scratch directory; pass the run
directory to point it at another run.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, "/home/user/Veri-Sure")
from specflow import oracles_stage as OS  # noqa: E402
from specflow import variety as V  # noqa: E402
from specflow.refmodel.compose import choose_base  # noqa: E402
from specflow.refmodel.oracle_gen import RequirementOracle  # noqa: E402

RUN = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(
    "/tmp/claude-0/-home-user-Veri-Sure/"
    "12bb865e-7a51-5506-b55a-e5ac7cf72a4a/scratchpad/e5probe")
EV = Path("docs/evidence/e5")

contract = json.loads(Path(
    "benchmarks/baselines/i2c_master_bit_ctrl/arm_a/contract.json").read_text())
probes = json.loads((RUN / "specflow" / "probes.json").read_text())["probes"]
contract["io"] = list(contract["io"]) + [
    {"name": p["name"], "dir": "probe", "width": p.get("width", 1)}
    for p in probes]
contract["probes"] = [p["name"] for p in probes]

population = tuple((RUN / "specflow" / "population" / f"{i}.py").read_text()
                   for i in range(3))
orc = json.loads((EV / "real-oracles.json").read_text())
stim = json.loads((EV / "real-stimulus.json").read_text())
tpl = json.loads((EV / "real-testplan.json").read_text())
reqs = json.loads((EV / "real-requirements.json").read_text())

testplan = tpl["elements"]
by_uid = {r["uid"]: r for r in reqs["requirements"]}
stimulus_by_tp = {s["tp_uid"]: s["stimulus_steps"] for s in stim["testpoints"]}
covers = {str(t.get("uid")): [str(c).split("@")[0] for c in (t.get("covers") or [])]
          for t in testplan}

#: THE FIRST DRAFTS, which is what `held` holds when the cell leg runs -- the
#: corpus records every body with its arm, so the state at that moment is
#: recoverable from the artifact rather than guessed at.
held = {}
for uid, bodies in (orc.get("corpus") or {}).items():
    first = next((b for b in bodies if b.get("arm") == "generate"), None)
    if not first:
        continue
    held[uid] = RequirementOracle(
        req_uid=uid,
        tp_uids=[t for t, cs in covers.items() if uid in cs],
        clause=str(by_uid.get(uid, {}).get("text") or "")[:120],
        source=first["source"])

base = choose_base(contract)
transactional = True
outputs = [str(p.get("name")) for p in contract["io"]
           if p.get("dir") == "output" and p.get("name")]
rows = OS._population_rows(population, contract, stimulus_by_tp,  # noqa: SLF001
                           base=base, transactional=transactional)
cells = V.cells(rows, outputs)
print(f"{len(population)} design(s), {len(held)} first draft(s), "
      f"{len(outputs)} output port(s), base={base}")
print(f"{len(cells)} disagreement cell(s)\n")

flat = OS._population_verdicts(  # noqa: SLF001
    held, population, contract, stimulus_by_tp, base=base,
    transactional=transactional)
per_tp = OS._population_verdicts_by_tp(  # noqa: SLF001
    held, population, contract, stimulus_by_tp, base=base,
    transactional=transactional)

b_pair = V.blind(cells, flat)
b_at = V.blind_at(cells, per_tp)
print(f"blind, per-PAIR            {len(b_pair):>5}  "
      f"= {100 * len(b_pair) / len(cells):.1f}%")
print(f"blind, per-(TESTPOINT,pair) {len(b_at):>4}  "
      f"= {100 * len(b_at) / len(cells):.1f}%\n")

print("    pair     cells   testpoints   checks that separate it ANYWHERE")
for pair in sorted({c.pair for c in cells}):
    mine = [c for c in cells if c.pair == pair]
    sep = [cid for cid, per in flat.items()
           if per.get(pair[0]) is not None and per.get(pair[1]) is not None
           and per[pair[0]] != per[pair[1]]]
    print(f"    {str(pair):<9}{len(mine):>6}{len({c.testpoint for c in mine}):>13}"
          f"   {len(sep)}")

ports: dict[str, int] = {}
for c in b_at:
    ports[c.port] = ports.get(c.port, 0) + 1
print(f"\nthe per-testpoint residue covers "
      f"{len({c.testpoint for c in b_at})} testpoint(s); by port: "
      + ", ".join(f"{p}={n}" for p, n in sorted(ports.items(), key=lambda kv: -kv[1])))

targets = OS._cell_targets(  # noqa: SLF001
    population=population, held=held, contract=contract,
    stimulus_by_tp=stimulus_by_tp, testplan=testplan, by_uid=by_uid,
    normalized={s["req_uid"]: s for s in json.loads(
        (RUN / "specflow" / "normalized.json").read_text())["normalized"]},
    budget=12, base=base, transactional=transactional)
print(f"\n_cell_targets at budget 12: {len(targets)} target(s)"
      + (f" on ports {sorted({t['cell'].port for t in targets})}" if targets else ""))
