"""THE PIPELINE'S OWN RTL LOOP, pointed at a finished run's check set.

    python docs/evidence/e6_rtl_loop.py <out_dir> <artifacts_dir> [retries] [trials]

**WHY THIS AND NOT A SUBAGENT WITH A FILE.** The first attempt at this question
handed a fresh agent the specification and a pass/fail harness and let it write
`candidate.v` from scratch each round. That is not what this tree does and it
tests none of it: `RTLEditor` repairs INCREMENTALLY through `_EditSession` --
`list_failing_requirements`, `explain`, `focus`, `list_suspect_blocks`,
`read_block`, `find_signal`, then `replace_block` / `edit` / `add_block` /
`remove_block` into a STAGING area, `check_staged` before `commit`, with
`rollback_on_regression` and a trial budget. A loop that rewrites the file every
round exercises the check set and throws the editor away.

So this drives `run_specflow_node`, which is the real thing end to end:

    build_artifacts (REUSED here) -> rtl_gen.chat once -> for each retry:
        reviewer.review() -> RTLEditor.chat repairs -> re-review

`reuse=True` points it at an existing run directory, so the 3.5 hours of
artifacts are not re-bought and the RTL loop is measured against the SAME
frozen set the scorecard scored.

**THE CONTROL IS NOT IN THIS PATH.** `refmodel_control` is left None. A control
may reject an oracle and may never repair one, and it may certainly never reach
a design the loop is editing.
"""
from __future__ import annotations

import asyncio
import json
import logging
import shutil
import sys
from pathlib import Path

sys.path.insert(0, "/home/user/Veri-Sure")

logging.basicConfig(level=logging.WARNING, format="%(message)s",
                    stream=sys.stdout)
for _n in ("specflow.oracles_stage", "specflow.integration", "specflow.run",
           "eda_agent.specflow_node", "eda_agent.rtl_editor"):
    logging.getLogger(_n).setLevel(logging.INFO)

from eda_agent.config import load_openai_config  # noqa: E402
from eda_agent.rtl_generator import RTLGenerator  # noqa: E402
from eda_agent.specflow_node import run_specflow_node  # noqa: E402

OUT = Path(sys.argv[1])
SRC = Path(sys.argv[2])
RETRIES = int(sys.argv[3]) if len(sys.argv) > 3 else 4
TRIALS = int(sys.argv[4]) if len(sys.argv) > 4 else 30

#: A COPY, because the loop writes `rtl.sv`, `suite/results` and a verdict into
#: the run directory it is given. Scoring a set while a design is being repaired
#: against it in the same directory is how a measurement gets overwritten by the
#: thing it measures.
if OUT.exists():
    shutil.rmtree(OUT)
(OUT / "specflow").mkdir(parents=True)
for name in ("oracles.json", "requirements.json", "normalized.json",
             "testplan.json", "stimulus.json", "coverage_model.json",
             "probes.json", "contract.json", "scorecard.json"):
    src = SRC / "specflow" / name if (SRC / "specflow" / name).is_file() \
        else SRC / name
    if src.is_file():
        shutil.copy(src, OUT / "specflow" / name)
for name in ("ref_model.py", "witness.py"):
    if (SRC / "specflow" / name).is_file():
        shutil.copy(SRC / "specflow" / name, OUT / "specflow" / name)
if (SRC / "specflow" / "suite").is_dir():
    shutil.copytree(SRC / "specflow" / "suite", OUT / "suite",
                    dirs_exist_ok=True)
    #: Never the previous design's traces. `load_traces` reads the directory,
    #: not a manifest, so a stale recording is decided as this candidate's.
    for f in (OUT / "suite" / "results").glob("*"):
        f.unlink()

#: **THE CONTRACT THE RUN WORKED TO, not the input one.** `probes.write_contract`
#: put the probe table in `io`, and a design is required to expose what its
#: contract declares -- which is the whole reason the loop can be judged on 122
#: checks instead of the 16 that name no probe.
contract = json.loads((OUT / "specflow" / "contract.json").read_text()) \
    if (OUT / "specflow" / "contract.json").is_file() else None
if contract is None:
    from specflow import probes as P
    contract = P.in_force(SRC, json.loads(Path(
        "benchmarks/baselines/i2c_master_bit_ctrl/arm_a/contract.json"
    ).read_text()))
(OUT / "contract.json").write_text(json.dumps(contract, indent=1),
                                   encoding="utf-8")
contract_json = json.dumps(contract)
spec = (SRC / "prompt.txt").read_text(encoding="utf-8") \
    if (SRC / "prompt.txt").is_file() else (SRC.parent / "prompt.txt").read_text()

n_probes = sum(1 for p in contract.get("io") or [] if p.get("dir") == "probe")
print(f"run {OUT}\nartifacts from {SRC}\n"
      f"contract declares {n_probes} probe(s); "
      f"{len(json.loads((OUT/'specflow'/'oracles.json').read_text())['oracles'])}"
      f" frozen check(s)\nsim_max_retry={RETRIES} debug_max_trials={TRIALS}",
      flush=True)

cfg = load_openai_config()
ok, rtl, detail = asyncio.run(run_specflow_node(
    cfg=cfg, spec=spec, contract_json=contract_json, output_dir_per_run=OUT,
    rtl_gen=RTLGenerator(cfg),
    sim_max_retry=RETRIES, debug_max_trials=TRIALS,
    model_port="api", reuse=True,
    #: NEVER in this path. A control may reject an oracle and may never repair
    #: one, and it may certainly never reach a design being edited.
    refmodel_control=None,
))
print(f"\nNODE ok={ok}")
print(f"verdict: {detail.get('verdict')}")
for line in detail.get("history") or []:
    print(f"  {line}")
(OUT / "node_detail.json").write_text(json.dumps(detail, indent=1, default=str),
                                      encoding="utf-8")
print(f"\nrtl.sv: {len((rtl or '').splitlines())} lines")
