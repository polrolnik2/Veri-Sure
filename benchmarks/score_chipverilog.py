#!/usr/bin/env python3
"""Score a Veri-Sure candidate with ChipVerilog's own verification flow.

Scoring is delegated to the vendored `tools/formal_equivalence.py` rather than
reimplemented, because only its verdicts are comparable with the published
table. This wraps it so a run directory can be scored directly.

Two things it records that a bare verdict would hide.

**Which oracle decided.** ChipVerilog is level-aware: an iverilog compile gate,
then a self-checking simulation testbench if the task ships one, otherwise a
Yosys equivalence proof. Only 16 of 64 tasks ship a testbench at all, so for
most tasks -- `or1200_ctrl` among them -- there is no golden-testbench pass rate
to quote, and the number is an equivalence result. Reporting one as the other
would be a category error, so `flow` and `proof_type` are always printed.

**That this environment is not the published one.** Re-verifying the five
published `claude` candidates for `i2c_master_top` here reproduces 3 of 5: the
two disagreements both move `compile_fail` -> `function_fail`, because this
iverilog accepts candidates the published environment rejected. The pass count
reproduces exactly (0 of 5 both ways), so pass/fail is comparable while the
failure *category* is environment-local. Both arms are scored by this same
invocation, so they remain comparable with each other regardless.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
TOOL = REPO_ROOT / "benchmarks" / "chipverilog" / "tools" / "formal_equivalence.py"


def score(run_dir: Path, task: str, attempt: int = 1, timeout: int = 2400) -> dict:
    """Copy the candidate into the layout the tool expects, then verify it."""
    rtl = Path(run_dir) / "rtl.sv"
    if not rtl.exists() or not rtl.stat().st_size:
        return {"status": "no_candidate", "reason": "the run produced no rtl.sv"}

    work = Path(run_dir) / "score"
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    # The tool derives module and attempt from the filename, so the candidate
    # has to be named the way Result/<model>/<module>/<module>_tN.v is.
    shutil.copy(rtl, work / f"{task}_t{attempt}.v")

    report = work / "report.json"
    cmd = [
        sys.executable, str(TOOL), "check",
        "--module-dir", task,
        "--candidates", str(work),
        "--report", str(report),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        # A timeout proves nothing about the candidate, which is the same reason
        # the upstream flow excludes solver timeouts from function_fail.
        return {"status": "timeout", "reason": f"verification exceeded {timeout}s"}

    if not report.exists():
        return {"status": "tool_error", "reason": proc.stderr[-2000:] or proc.stdout[-2000:]}

    data = json.loads(report.read_text(encoding="utf-8"))
    rows = data.get("results") if isinstance(data, dict) else data
    if not rows:
        return {"status": "tool_error", "reason": "verifier produced no rows"}
    row = rows[0]
    return {
        "status": row.get("status"),
        "flow": row.get("flow"),
        "proof_type": row.get("proof_type"),
        "reason": (row.get("reason") or "")[:600],
        "reference_precheck": row.get("reference_precheck"),
        "interface_status": row.get("interface_status"),
        "formal_status": row.get("formal_status"),
        "compile_gate_status": row.get("compile_gate_status"),
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="score_chipverilog")
    p.add_argument("--run-dir", required=True)
    p.add_argument("--task", required=True)
    p.add_argument("--attempt", type=int, default=1)
    p.add_argument("--timeout", type=int, default=2400)
    p.add_argument("--label", default="")
    args = p.parse_args(argv)

    result = score(Path(args.run_dir), args.task, args.attempt, args.timeout)
    result["task"] = args.task
    if args.label:
        result["label"] = args.label
    out = Path(args.run_dir) / "score.json"
    out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
