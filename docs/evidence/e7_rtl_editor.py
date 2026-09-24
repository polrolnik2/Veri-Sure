"""The RTL Editor testbench: generate RTL, then repair it against the SHIPPED set.

    e7_rtl_editor.py <run-dir> <out-dir> --spec <description.txt>
                     [--trials N] [--rounds R] [--rtl START.v] [--summary OUT.json]

`e6_rtl_debug.py` generalised to any module. What it does, and nothing else:

    RTLGenerator writes rtl.sv from the specification and the run's contract
    -> for each round: SpecflowReviewer runs the suite and decides the shipped
       set on the recording -> RTLEditor.chat repairs against what failed

The set is the one the run SHIPPED -- `_frozen_oracles` reads `shipped.json`
when the run wrote one -- so the editor iterates on the same checks the run's
scorecard scored. The suite is the one the run rendered. The contract is the
run's in-force contract (probes folded in), read rather than rebuilt; the old
driver rebuilt it from bit_ctrl's baseline and could not run another module.

**THE GOLDEN DESIGN IS NOT IN THIS PATH.** No golden source, no golden trace and
no verdict computed against one reaches the generator or the editor; they see
the specification, the contract, the check's complaint, the recording of THEIR
OWN design and its source. The run's `ref_model.py` is read only because the
cocotb runtime advances a model in lockstep to record a trace; nothing it says
reaches a verdict. Grading the final RTL against golden is a separate step.
"""
from __future__ import annotations

import asyncio
import json
import shutil
import sys
import time
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, "/home/user/Veri-Sure")

from eda_agent.config import load_openai_config  # noqa: E402
from eda_agent.explain import load_requirement_views  # noqa: E402
from eda_agent.rtl_editor import RTLEditor  # noqa: E402
from eda_agent.rtl_generator import RTLGenerator  # noqa: E402
from eda_agent.specflow_node import (SpecflowReviewer,  # noqa: E402
                                     SpecflowStimulusStager, _frozen_oracles)
from specflow.integration import describe_oracle  # noqa: E402
from specflow.model_io import ApiPort  # noqa: E402


def _opt(name, default=None):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


args = [a for a in sys.argv[1:] if not a.startswith("--")
        and sys.argv[sys.argv.index(a) - 1] not in
        ("--spec", "--trials", "--rounds", "--rtl", "--summary")]
if len(args) < 2 or not _opt("--spec"):
    print(__doc__.strip().splitlines()[2])
    raise SystemExit(2)
RUN, OUT = Path(args[0]), Path(args[1])
SRC = RUN / "specflow" if (RUN / "specflow").is_dir() else RUN
TRIALS = int(_opt("--trials", 20))
ROUNDS = int(_opt("--rounds", 3))
START = _opt("--rtl")
SUMMARY = Path(_opt("--summary", str(OUT / "editor_summary.json")))
spec = Path(_opt("--spec")).read_text(encoding="utf-8")

#: A COPY: the loop writes rtl.sv, suite results and verdicts, and a measurement
#: must not be overwritten by the thing it measures.
if OUT.exists():
    shutil.rmtree(OUT)
(OUT / "specflow").mkdir(parents=True)
for name in ("oracles.json", "shipped.json", "requirements.json",
             "normalized.json", "testplan.json", "stimulus.json",
             "coverage_model.json", "probes.json", "contract.json"):
    if (SRC / name).is_file():
        shutil.copy(SRC / name, OUT / "specflow" / name)
shutil.copy(SRC / "ref_model.py", OUT / "ref_model.py")
shutil.copytree(SRC / "suite", OUT / "suite", dirs_exist_ok=True)
for f in (OUT / "suite" / "results").glob("*"):
    f.unlink()

contract = json.loads((OUT / "specflow" / "contract.json").read_text())
(OUT / "contract.json").write_text(json.dumps(contract, indent=1))
contract_json = json.dumps(contract)
cov = json.loads((OUT / "specflow" / "coverage_model.json").read_text())
oracles = _frozen_oracles(OUT)
shipped = (OUT / "specflow" / "shipped.json").is_file()
top = str(contract.get("module_name") or "TopModule")
n_req = len({o.req_uid for o in oracles})
print(f"run {RUN}\n{len(oracles)} check bodies over {n_req} requirement(s) "
      f"from {'shipped.json' if shipped else 'oracles.json (NO shipped set)'}; "
      f"trials={TRIALS} rounds={ROUNDS}", flush=True)

cfg = load_openai_config()
port = ApiPort(root=OUT / "agent_io")
stager = SpecflowStimulusStager(
    run_dir=OUT, contract=contract, bins=cov.get("bins") or [],
    suite_dir=OUT / "suite", model_port=port)
reviewer = SpecflowReviewer(
    built=SimpleNamespace(suite_dir=OUT / "suite",
                          refmodel_path=OUT / "ref_model.py",
                          bins=cov.get("bins") or []),
    hdl_toplevel=top, output_dir=OUT, stager=stager,
    oracles=oracles, contract=contract)
rtl_path = OUT / "rtl.sv"
tb_text = describe_oracle(
    suite_dir=OUT / "suite", refmodel_path=OUT / "ref_model.py",
    testplan=json.loads((OUT / "specflow" / "testplan.json").read_text()),
    max_chars=12000)
history: list[dict] = []


def _tally(rnd: int, failing: int) -> dict:
    decided = reviewer.req_results or {}
    bad = sorted(u for u, (r, _t) in decided.items() if getattr(r, "ok", None) is False)
    quiet = sorted(u for u, (r, _t) in decided.items() if getattr(r, "ok", None) is None)
    row = {"round": rnd, "requirements": len(decided),
           "pass": len(decided) - len(bad) - len(quiet), "fail": len(bad),
           "abstain": len(quiet), "failing_testpoints": failing,
           "failing": bad, "abstaining": quiet,
           "rtl_lines": len(rtl_path.read_text().splitlines())
           if rtl_path.is_file() else 0}
    history.append(row)
    print(f"\nROUND {rnd}: {row['pass']} pass, {row['fail']} FAIL, "
          f"{row['abstain']} abstain of {row['requirements']} requirement(s); "
          f"{failing} failing testpoint(s)", flush=True)
    if bad:
        print(f"  failing: {', '.join(bad[:16])}{' ...' if len(bad) > 16 else ''}",
              flush=True)
    return row


async def _drive() -> None:
    remaining = TRIALS
    if START:
        rtl_path.write_text(Path(START).read_text(encoding="utf-8"), encoding="utf-8")
    else:
        ok, code = await RTLGenerator(cfg).chat(
            input_spec=spec, testbench="", interface="",
            rtl_path=str(rtl_path), contract_json=contract_json)
        if not ok or not code.strip():
            print("RTL generation produced nothing", flush=True)
            raise SystemExit(1)
        rtl_path.write_text(code, encoding="utf-8")
        shutil.copy(rtl_path, OUT / "rtl_generated.sv")
        print(f"generated rtl.sv ({len(code.splitlines())} lines)", flush=True)

    for rnd in range(ROUNDS + 1):
        is_pass, failing, sim_output = reviewer.review()
        row = _tally(rnd, failing)
        if is_pass or row["fail"] == 0 or not remaining or rnd == ROUNDS:
            break
        editor = RTLEditor(cfg, sim_reviewer=reviewer, max_trials=remaining,
                           stimulus_stager=stager,
                           requirements=load_requirement_views(OUT, contract),
                           contract=contract)
        _, repaired, used, _ = await editor.chat(
            spec=spec, output_dir_per_run=str(OUT), sim_failed_log=sim_output,
            sim_mismatch_cnt=failing, contract_json=contract_json,
            max_trials=remaining, tb_text=tb_text, tb_clip_chars=12000)
        remaining -= max(1, int(used))
        row["editor_trials_used"] = int(used)
        print(f"  editor used {used} trial(s); {remaining} left", flush=True)
        if repaired.strip():
            rtl_path.write_text(repaired, encoding="utf-8")


t0 = time.time()
asyncio.run(_drive())
SUMMARY.write_text(json.dumps({
    "run": str(RUN), "module": top, "bodies": len(oracles),
    "requirements": n_req, "set": "shipped" if shipped else "oracles",
    "trials": TRIALS, "rounds": ROUNDS, "seconds": round(time.time() - t0),
    "history": history, "final": history[-1] if history else None,
}, indent=2) + "\n")
print(f"\nFINAL rtl.sv: {len(rtl_path.read_text().splitlines())} lines; "
      f"summary {SUMMARY}", flush=True)
