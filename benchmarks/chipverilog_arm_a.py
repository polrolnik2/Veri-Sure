#!/usr/bin/env python3
"""Arm A of the ChipVerilog comparison: the pre-specflow SystemVerilog path.

Run from a git worktree checked out at the merge-base, so `TBGenerator`,
`_run_instance` and the `TB_4_SHOT_EXAMPLES` corpus are all still present. Kept
here rather than in that worktree so the two arms are versioned together and the
comparison stays reproducible after the worktree is gone.

## The confound, and what is held constant

"Veri-Sure without our modifications" cannot reach `gpt-5.6-luna` at all. Three
transport-layer blockers, none of which has anything to do with testbench
quality:

1. `--temperature 0.0` was hardcoded, and reasoning models reject an explicit
   temperature ("only the default (1) value is supported");
2. `reasoning_effort` had no path from the environment, so it was silently
   dropped and every call ran at the endpoint's default;
3. the gateway refuses function tools together with `reasoning_effort` on
   /v1/chat/completions, and every agent here is tool-using.

Reporting "the old code scores zero" on those grounds would measure the
transport, not the oracle. So arm A is the merge-base tree plus *only* the
transport fixes -- `config.py`, `model.py`, `responses_model.py`, and a
temperature left unset -- which is 39 changed lines and no change to any
testbench, prompt, or verdict logic. Both arms then face the same model at the
same effort, and the only difference left is the thing under test: one
monolithic generated `tb.sv` versus the spec-grounded chain.

Whatever this arm scores, that number is what the specflow arm has to beat.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import traceback
from pathlib import Path


def load_env_file(path: Path) -> dict[str, str]:
    """Read `KEY=value` credentials. Duplicated rather than imported because
    the merge-base tree has no `specflow` package to import it from -- which is
    the whole point of this arm."""
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        out[key.strip()] = value
    return out


def scorer_language_flag(task_dir: Path | None) -> str:
    """Which iverilog dialect the SCORER will actually hold this task to.

    Not a blanket choice, because the scorer's routing is not blanket. A task
    that ships a testbench is scored by SIMULATING it, and the deciding compile
    is the scorer's no-language-flag retry (formal_equivalence.py:1456) --
    iverilog 12's default, `-g2005`, which rejects `logic` in a port list. A
    task with NO testbench never reaches iverilog: it goes to yosys
    equivalence, which accepts SystemVerilog, so port dialect costs it nothing.

    Measured in both directions, on real generated RTL:

      * `alu` ships alu_tb_0.v. A design our transactional testbench passed
        40/40 against golden was scored `function_fail` purely for declaring
        `input logic [15:0] a`; rewriting the four port lines moved it to
        `pass`.
      * `or1200_gmultp2_32x32` ships no testbench. A design with those SAME
        `input logic` ports was scored `pass` by temporal induction (k=16).

    So holding every task to `-g2005` would reject correct work -- the gate
    would fail gmult, which the benchmark passes. The routing decision is taken
    from the scorer's own `classify_module_dir`, so the gate cannot drift away
    from the authority it is mirroring. If that cannot be consulted we fall
    back to the permissive flag: a gate that wrongly rejects sends the repair
    loop after a correct design, which is worse than one that wrongly admits.
    """
    if task_dir is None:
        return "-g2012"
    try:
        from benchmarks.chipverilog.tools.formal_equivalence import (
            classify_module_dir,
            discover_reference_file,
        )

        reference = discover_reference_file(Path(task_dir))
        tb_info, _ = classify_module_dir(Path(task_dir), reference)
    except Exception:  # noqa: BLE001 -- vendored tool absent or restructured
        return "-g2012"
    return "-g2005" if tb_info is not None else "-g2012"


def compile_gate(
    rtl: Path, top: str, extra: list[Path], task_dir: Path | None = None
) -> dict:
    """ChipVerilog's first gate: iverilog must elaborate `top` by its own name.

    Verilog-2005, NOT `-g2012`, and the difference decides scores. The scorer
    compiles the task's shipped testbench against the candidate at `-g2012`
    first and, when that fails, retries with NO language flag
    (`formal_equivalence.py:1456`) -- which for iverilog 12 is `-g2005`. On the
    `alu` task the shipped testbench itself fails the `-g2012` attempt, so the
    plain retry is the path that actually decides, and a candidate that only
    compiles at `-g2012` never reaches simulation at all: it is diverted to
    formal equivalence and scored `function_fail`.

    Gating at `-g2012` therefore passed designs the scorer could not admit. A
    generated `alu` scoring 40/40 against golden through our own transactional
    testbench was scored `function_fail` for declaring `input logic [15:0] a`;
    rewriting only the four port declarations, body byte-identical, moved the
    same design to `pass`.

    `-g2005` constrains exactly that and nothing more. It rejects `logic` in a
    PORT LIST while still accepting `logic`, `always_comb` and the rest inside
    the module body, which is why the RTL prompt asks only for portable ports
    and leaves the body alone. Measured on iverilog 12.0:

        flag         logic in body    logic in ports
        <default>    accept           reject
        -g2005       accept           reject
        -g2005-sv    accept           accept
        -g2012       accept           accept
    """
    if not rtl.exists() or not rtl.stat().st_size:
        return {"status": "fail", "reason": "no candidate RTL was produced"}
    cmd = ["iverilog", scorer_language_flag(task_dir), "-s", top, "-o", "/dev/null", str(rtl), *map(str, extra)]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    return {
        "status": "pass" if proc.returncode == 0 else "fail",
        "exit_code": proc.returncode,
        "stderr": proc.stderr[-4000:],
    }


async def run(args: argparse.Namespace) -> dict:
    from eda_agent.config import load_openai_config
    from eda_agent.top_agent import TopAgent, TopAgentConfig

    task_dir = Path(args.task_dir).resolve()
    top = task_dir.name
    spec = (task_dir / "description.txt").read_text(encoding="utf-8")
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)

    # temperature deliberately not passed: see the module docstring.
    cfg = load_openai_config(max_completion_tokens=args.max_tokens,
                             timeout_s=args.timeout)
    record: dict = {
        "arm": "A",
        "description": "pre-specflow SystemVerilog testbench path (merge-base + transport fixes)",
        "task": top,
        "model": cfg.model,
        "reasoning_effort": cfg.reasoning_effort,
        "api_flavor": cfg.api_flavor,
        "spec_bytes": len(spec),
    }

    agent = TopAgent(
        cfg,
        config=TopAgentConfig(
            sim_max_retry=args.sim_max_retry,
            debug_max_trials=args.debug_max_trials,
        ),
    )
    try:
        result = await agent.run(spec=spec, output_dir_per_run=out)
        record["is_sim_pass"] = bool(getattr(result, "is_sim_pass", False))
        record["rtl_bytes"] = len(getattr(result, "rtl_code", "") or "")
        # Cost belongs in a baseline: two arms that score the same are not
        # equivalent if one spent several times the tokens. TopAgentResult
        # already carries this and both runners were dropping it.
        record["tokens"] = {
            "eda_agent_input": int(getattr(result, "input_tokens", 0) or 0),
            "eda_agent_output": int(getattr(result, "output_tokens", 0) or 0),
            "breakdown": getattr(result, "usage_breakdown", None),
        }
    except Exception as exc:  # noqa: BLE001
        record["is_sim_pass"] = False
        record["exception"] = f"{type(exc).__name__}: {exc}"
        record["traceback"] = traceback.format_exc()[-4000:]

    # The SV path's own artifacts, so the two arms can be compared on what each
    # actually produced rather than on the verdict alone.
    record["artifacts_present"] = sorted(p.name for p in out.glob("*"))
    tb = out / "tb.sv"
    record["tb_bytes"] = tb.stat().st_size if tb.exists() else 0

    extra = [task_dir / f"{k}.v" for k in args.submodule or []]
    extra = [p for p in extra if p.exists()]
    record["compile_gate"] = compile_gate(out / "rtl.sv", top, extra, task_dir)

    (out / "baseline.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return record


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="chipverilog_arm_a")
    p.add_argument("--task-dir", required=True, help="ChipVerilog Des/<family>/<module> dir")
    p.add_argument("--out", required=True)
    p.add_argument("--submodule", action="append", help="submodule name to supply at compile time")
    # THE TWO BOUNDS THAT DECIDE WHETHER A LONG GENERATION SURVIVES, and both
    # are switches so a run can report what it used rather than what the
    # environment happened to hold.
    #
    # 40000 was measured to be the binding one at xhigh: four or1200_dc_fsm
    # runs at that ceiling produced no testbench at all, and one at 128000
    # produced a complete 40 KB testbench before dying elsewhere.
    p.add_argument("--max-tokens", type=int, default=40000,
                   help="per-call output budget (reasoning AND content "
                        "together, so it must exceed the reasoning budget "
                        "the effort asks for)")
    # And 600s was the next one. Instrumented on the same task at 128000: the
    # stream dropped at 662.4s having emitted 10,082 events with a largest gap
    # of 9.9s and first content at 312.4s -- nothing idle, nothing truncated,
    # just past the client's own bound. specflow never meets this because
    # chunking bounds each call's duration; an unchunked caller does not.
    p.add_argument("--timeout", type=float, default=1800.0,
                   help="per-attempt client timeout in seconds")
    p.add_argument("--sim-max-retry", type=int, default=2)
    p.add_argument("--debug-max-trials", type=int, default=6)
    p.add_argument("--env-file", required=True)
    args = p.parse_args(argv)

    os.environ.update(load_env_file(Path(args.env_file)))
    record = asyncio.run(run(args))
    print(json.dumps({k: v for k, v in record.items() if k != "traceback"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
