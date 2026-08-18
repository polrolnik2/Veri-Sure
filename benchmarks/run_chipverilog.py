#!/usr/bin/env python3
"""Run one ChipVerilog task through Veri-Sure and record what happened.

Separate from `run_verilog_eval_v2.py` because the two benchmarks judge
differently. VerilogEval ships a golden testbench per problem and scores by
running it. ChipVerilog is *level-aware*: an iverilog compile gate first (the
top module must carry the reference name), then either a self-checking
simulation testbench or a Yosys equivalence proof -- and only 16 of its 64 tasks
ship a testbench at all, so formal equivalence carries the suite.

This runner does not re-implement that flow. It produces the candidate RTL and
records, stage by stage, where Veri-Sure got to; scoring is left to the vendored
`tools/formal_equivalence.py`, which is the only thing whose verdicts are
comparable with the published numbers.

The point is a *baseline*: a reproducible record of a task the loop does not
pass, precise enough to tell which stage gave way and why.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
import traceback
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from eda_agent.config import load_openai_config  # noqa: E402
from eda_agent.top_agent import TopAgent, TopAgentConfig  # noqa: E402
from specflow.model_io import load_env_file  # noqa: E402

DES = REPO_ROOT / "benchmarks" / "chipverilog" / "Des"


def find_task(name: str) -> Path:
    """Locate a task directory by module name, e.g. `i2c_master_top`."""
    hits = [p.parent for p in DES.rglob("description.txt") if p.parent.name == name]
    if not hits:
        raise SystemExit(f"no ChipVerilog task named {name!r} under {DES}")
    return hits[0]


def submodules(task_dir: Path, top: str) -> list[str]:
    """Modules this task's reference instantiates but does not define.

    A task with any is *hierarchical*, which matters here because specflow is
    scoped to leaf nodes: its reference model is a single Python class derived
    from one module's requirements, with no notion of a child instance. Whether
    that limit is what stops a given task is exactly the thing a baseline should
    record rather than assume.
    """
    import re

    def strip(text: str) -> str:
        text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
        return re.sub(r"//[^\n]*", "", text)

    defined = set()
    for path in DES.rglob("*.v"):
        defined |= set(re.findall(r"^\s*module\s+(\w+)", strip(path.read_text(errors="ignore")), re.M))

    src = strip((task_dir / f"{top}.v").read_text(errors="ignore"))
    own = set(re.findall(r"^\s*module\s+(\w+)", src, re.M))
    keywords = {
        "if", "else", "for", "while", "case", "begin", "end", "assign", "always",
        "module", "endmodule", "input", "output", "inout", "wire", "reg",
        "parameter", "localparam", "initial", "posedge", "negedge", "function",
        "task", "generate", "endgenerate", "defparam",
    }
    found = re.findall(r"^[ \t]*(\w+)[ \t]+(?:#\s*\([^;]*?\)[ \t\n]*)?(\w+)[ \t]*\(", src, re.M)
    return sorted({m for m, _ in found if m in defined and m not in own and m not in keywords})


def compile_gate(rtl: Path, top: str, extra: list[Path]) -> dict:
    """ChipVerilog's first gate: iverilog must elaborate `top` by its own name.

    Reproduced here (rather than invoked from the vendored tool) only so the
    baseline records the same first-order fact the suite would; the vendored
    flow remains the authority for a comparable verdict.
    """
    if not rtl.exists() or not rtl.stat().st_size:
        return {"status": "fail", "reason": "no candidate RTL was produced"}
    cmd = ["iverilog", "-g2012", "-s", top, "-o", "/dev/null", str(rtl), *map(str, extra)]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    return {
        "status": "pass" if proc.returncode == 0 else "fail",
        "exit_code": proc.returncode,
        "stderr": proc.stderr[-4000:],
        "command": " ".join(cmd),
    }


async def run(args: argparse.Namespace) -> dict:
    task_dir = find_task(args.task)
    top = task_dir.name
    spec = (task_dir / "description.txt").read_text(encoding="utf-8")
    kids = submodules(task_dir, top)

    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)

    cfg = load_openai_config(max_completion_tokens=args.max_tokens)
    record: dict = {
        "task": top,
        "family": task_dir.parent.name,
        "hierarchical": bool(kids),
        "instantiates": kids,
        "spec_bytes": len(spec),
        "reference_lines": len((task_dir / f"{top}.v").read_text(errors="ignore").splitlines()),
        "model": cfg.model,
        "reasoning_effort": cfg.reasoning_effort,
        "api_flavor": cfg.api_flavor,
        "tb_backend": "specflow",
    }

    agent = TopAgent(
        cfg,
        config=TopAgentConfig(
            tb_backend="specflow",
            specflow_model_port="api",
            sim_max_retry=args.sim_max_retry,
            debug_max_trials=args.debug_max_trials,
        ),
    )
    try:
        result = await agent.run(spec=spec, output_dir_per_run=out)
        record["is_sim_pass"] = bool(getattr(result, "is_sim_pass", False))
        record["rtl_bytes"] = len(getattr(result, "rtl_code", "") or "")
    except Exception as exc:  # noqa: BLE001
        # A crash is a legitimate baseline outcome and must be recorded as one
        # rather than lost -- it says the loop cannot reach a verdict at all,
        # which is a different failure from reaching one and being wrong.
        record["is_sim_pass"] = False
        record["exception"] = f"{type(exc).__name__}: {exc}"
        record["traceback"] = traceback.format_exc()[-4000:]

    # Which specflow stage gave way, from what it left on disk.
    sf = out / "specflow"
    record["stages"] = {
        name: json.loads((sf / f"{name}_gate.json").read_text())
        if (sf / f"{name}_gate.json").exists() else None
        for name in ("s1", "s2", "s3", "refmodel")
    }
    record["artifacts_present"] = sorted(p.name for p in sf.glob("*")) if sf.exists() else []

    extra = [task_dir / f"{k}.v" for k in kids if (task_dir / f"{k}.v").exists()]
    record["compile_gate"] = compile_gate(out / "rtl.sv", top, extra)
    record["submodule_sources_supplied"] = [p.name for p in extra]

    (out / "baseline.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return record


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="run_chipverilog")
    p.add_argument("--task", required=True, help="module name, e.g. i2c_master_top")
    p.add_argument("--out", required=True, help="run directory")
    p.add_argument("--max-tokens", type=int, default=40000)
    p.add_argument("--sim-max-retry", type=int, default=2)
    p.add_argument("--debug-max-trials", type=int, default=6)
    p.add_argument("--env-file", default=str(REPO_ROOT / ".env.local"))
    args = p.parse_args(argv)

    # A running container cannot re-read its own environment, so credentials
    # rotated after start only arrive through a file. See specflow.model_io.
    os.environ.update(load_env_file(Path(args.env_file)))

    record = asyncio.run(run(args))
    print(json.dumps({k: v for k, v in record.items() if k != "traceback"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
