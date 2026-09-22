"""Debug RTL DIRECTLY against the frozen check corpus. No reference model built.

    python docs/evidence/e6_rtl_debug.py <out_dir> <artifacts_dir> [trials] [rounds] [--rtl F]

**THE CHECKS ARE THE ORACLE, SO NOTHING HERE GENERATES A SECOND ONE.** The
first cut of this drove `run_specflow_node`, which owns the whole artifact
chain -- so pointing it at a finished run still rebuilt and re-judged the
reference model, the longest stage in the pipeline, before reaching a single
line of RTL. Measured: S1, normalize, S2, S3 and all 122 oracles reused without
one model call, and the run then spent its first quarter-hour on a model that
was already on disk and is not what decides anything.

`SpecflowReviewer._decide_requirements` decides the FROZEN SET over the
recorded DUT trace with `decide_rtl`. That is the verdict the editor repairs
against. The `ref_model.py` on disk is only what the cocotb runtime advances in
lockstep so a trace gets recorded at all -- it is read, never written, never
judged, and never regenerated.

So this builds the reviewer and the editor by hand, the way `edit_drive.py`
does, and calls `RTLEditor.chat` -- the real agentic repair loop, with
`_EditSession`'s staging discipline, its budget and its rollback.
"""
from __future__ import annotations

import asyncio
import json
import shutil
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, "/home/user/Veri-Sure")

from eda_agent.config import load_openai_config  # noqa: E402
from eda_agent.explain import load_requirement_views  # noqa: E402
from eda_agent.rtl_editor import RTLEditor  # noqa: E402
from eda_agent.rtl_generator import RTLGenerator  # noqa: E402
from eda_agent.specflow_node import (SpecflowReviewer,  # noqa: E402
                                     SpecflowStimulusStager, _frozen_oracles)
from specflow import probes as P  # noqa: E402
from specflow.integration import describe_oracle  # noqa: E402
from specflow.model_io import ApiPort  # noqa: E402

args = [a for a in sys.argv[1:] if not a.startswith("--")]
OUT, SRC = Path(args[0]), Path(args[1])
TRIALS = int(args[2]) if len(args) > 2 else 20
ROUNDS = int(args[3]) if len(args) > 3 else 3
START = None
if "--rtl" in sys.argv:
    START = Path(sys.argv[sys.argv.index("--rtl") + 1])

if OUT.exists():
    shutil.rmtree(OUT)
(OUT / "specflow").mkdir(parents=True)
for name in ("oracles.json", "requirements.json", "normalized.json",
             "testplan.json", "stimulus.json", "coverage_model.json",
             "probes.json", "contract.json"):
    src = SRC / "specflow" / name
    if src.is_file():
        shutil.copy(src, OUT / "specflow" / name)
#: READ, never rebuilt. The runtime needs a model to advance in lockstep so a
#: trace is recorded; nothing it says reaches a verdict.
shutil.copy(SRC / "specflow" / "ref_model.py", OUT / "ref_model.py")
shutil.copytree(SRC / "specflow" / "suite", OUT / "suite", dirs_exist_ok=True)
for f in (OUT / "suite" / "results").glob("*"):
    f.unlink()

base = json.loads(Path("benchmarks/baselines/i2c_master_bit_ctrl/arm_a/"
                       "contract.json").read_text())
contract = P.in_force(OUT, base)
(OUT / "contract.json").write_text(json.dumps(contract, indent=1))
contract_json = json.dumps(contract)
spec = (SRC / "prompt.txt").read_text(encoding="utf-8")
cov = json.loads((OUT / "specflow" / "coverage_model.json").read_text())
oracles = _frozen_oracles(OUT)
top = str(contract.get("module_name") or "TopModule")

print(f"run {OUT}\n{len(oracles)} frozen check(s); "
      f"{len(P.declared_probes(contract))} declared probe(s)\n"
      f"debug_max_trials={TRIALS} rounds={ROUNDS}\n"
      f"NO reference model is generated -- ref_model.py is read for the "
      f"runtime's lockstep and nothing else", flush=True)

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
GENERATE = False
if START is not None:
    rtl_path.write_text(Path(START).read_text(encoding="utf-8"),
                        encoding="utf-8")
    print(f"starting from {START} ({len(rtl_path.read_text().splitlines())} lines)",
          flush=True)
else:
    GENERATE = True

tb_text = describe_oracle(suite_dir=OUT / "suite",
                          refmodel_path=OUT / "ref_model.py",
                          testplan=json.loads(
                              (OUT / "specflow" / "testplan.json").read_text()),
                          max_chars=12000)
#: **ONE EVENT LOOP FOR THE WHOLE DRIVER.** `asyncio.run` per round closes the
#: loop while the HTTP client from that round still has a finalizer queued, so
#: every round but the last ended in a `RuntimeError: Event loop is closed`
#: traceback from `httpx`'s pool teardown. Harmless in itself and exactly the
#: kind of noise that hides a real one.
async def _drive() -> None:
    remaining = TRIALS
    if GENERATE:
        ok, code = await RTLGenerator(cfg).chat(
            input_spec=spec, testbench="", interface="",
            rtl_path=str(rtl_path), contract_json=contract_json)
        if not ok or not code.strip():
            print("RTL generation produced nothing")
            raise SystemExit(1)
        rtl_path.write_text(code, encoding="utf-8")
        print(f"generated rtl.sv ({len(code.splitlines())} lines)", flush=True)

    for rnd in range(ROUNDS):
        is_pass, failing, sim_output = reviewer.review()
        decided = reviewer.req_results or {}
        bad = sorted(u for u, (r, _t) in decided.items()
                     if getattr(r, "ok", None) is False)
        quiet = sorted(u for u, (r, _t) in decided.items()
                       if getattr(r, "ok", None) is None)
        print(f"\nROUND {rnd}: {len(decided) - len(bad) - len(quiet)} pass, "
              f"{len(bad)} FAIL, {len(quiet)} abstain of {len(decided)} "
              f"check(s); {failing} failing testpoint(s)", flush=True)
        if bad:
            print(f"  failing: {', '.join(bad[:12])}", flush=True)
        #: **ABSTENTIONS ARE NAMED, NOT COUNTED.** A check that decided last
        #: round and abstains this one is the vacuity sign: the repair made it
        #: stop firing rather than pass. Measured on the first run -- 3 -> 5
        #: across one editor turn, with the design shrinking 518 -> 380 lines.
        if quiet:
            print(f"  abstain: {', '.join(quiet)}", flush=True)
        if is_pass or not remaining:
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
        #: **THE EDITOR'S CACHE RATE, WHICH NOTHING WAS READING.** `model.py`
        #: accumulates `input_tokens_details.cached_tokens` into
        #: `total_cached_tokens` -- the instrumentation exists and this driver
        #: simply never asked for it, so the most token-expensive loop in the
        #: system (the whole RTL and its traces on every turn, once per trial)
        #: was the one with no usage recorded anywhere.
        #:
        #: The editor is well placed to cache: `to_responses_input` maps
        #: `system` to `developer` every turn, `make_openai_model` sets
        #: `prompt_cache_key=veri-sure:rtl-debug:<model>`, and agentscope
        #: re-sends an append-only history, so each turn's prefix is the last
        #: turn's whole context.
        m = getattr(editor, "_model", None)
        inp = int(getattr(m, "total_input_tokens", 0) or 0)
        cac = int(getattr(m, "total_cached_tokens", 0) or 0)
        if inp:
            print(f"  editor used {used} trial(s); {remaining} left; "
                  f"cache {cac:,}/{inp:,} = {100*cac/inp:.1f}%", flush=True)
        else:
            print(f"  editor used {used} trial(s); {remaining} left "
                  f"(cached {cac:,}; input total not exposed)", flush=True)
        if repaired.strip():
            rtl_path.write_text(repaired, encoding="utf-8")


asyncio.run(_drive())
print(f"\nFINAL rtl.sv: {len(rtl_path.read_text().splitlines())} lines")
