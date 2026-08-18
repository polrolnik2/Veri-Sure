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


def compile_gate(rtl: Path, top: str, extra: list[Path]) -> dict:
    """ChipVerilog's first gate: iverilog must elaborate `top` by its own name."""
    if not rtl.exists() or not rtl.stat().st_size:
        return {"status": "fail", "reason": "no candidate RTL was produced"}
    cmd = ["iverilog", "-g2012", "-s", top, "-o", "/dev/null", str(rtl), *map(str, extra)]
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
    cfg = load_openai_config(max_completion_tokens=args.max_tokens)
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
    record["compile_gate"] = compile_gate(out / "rtl.sv", top, extra)

    (out / "baseline.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return record


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="chipverilog_arm_a")
    p.add_argument("--task-dir", required=True, help="ChipVerilog Des/<family>/<module> dir")
    p.add_argument("--out", required=True)
    p.add_argument("--submodule", action="append", help="submodule name to supply at compile time")
    p.add_argument("--max-tokens", type=int, default=40000)
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
