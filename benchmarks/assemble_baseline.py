#!/usr/bin/env python3
"""Assemble a committed ChipVerilog baseline from the two arms.

A baseline is only worth committing if it can be read correctly a month later by
someone who was not here. So this records not just the verdicts but the three
things that bound what they mean:

1. **Which oracle decided.** ChipVerilog is level-aware, and only 16 of its 64
   tasks ship a testbench. For the rest the number is a Yosys equivalence
   result, not a testbench pass rate.
2. **How this environment differs from the published one.** Re-verifying the
   five published `claude` candidates for `i2c_master_top` here reproduces 3 of
   5; both disagreements move `compile_fail` -> `function_fail` because this
   iverilog is more permissive. The pass count reproduces exactly, so pass/fail
   is comparable and failure *category* is not.
3. **What arm A is.** The pre-hardening tree plus transport and hierarchy
   plumbing only -- see `make_arm_a.sh`, which reconstructs and re-checks it.

Emits a directory of Veri-Sure's own outputs plus a README. It deliberately does
not copy the vendored spec: `benchmarks/chipverilog/` carries third-party
licensing (LGPL for OR1200/MIPS/FPU, BSD for I2C) and `VENDORED.md` warns that
copies drift from the notice governing them. Derived artifacts quote spec
fragments verbatim by design, which the README states rather than leaves
implicit.
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _load(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _arm_summary(run_dir: Path) -> dict:
    return {
        "run": _load(run_dir / "baseline.json"),
        "score": _load(run_dir / "score.json"),
        "node": _load(run_dir / "specflow_node.json"),
        "produced_rtl": (run_dir / "rtl.sv").exists()
        and bool((run_dir / "rtl.sv").stat().st_size),
    }


def _copy_artifacts(run_dir: Path, dest: Path, arm: str) -> list[str]:
    """Veri-Sure's own outputs only; never the vendored reference or spec."""
    out = dest / f"arm_{arm}"
    out.mkdir(parents=True, exist_ok=True)
    kept: list[str] = []
    for name in ("rtl.sv", "tb.sv", "contract.json", "baseline.json",
                 "score.json", "specflow_node.json"):
        src = run_dir / name
        if src.exists():
            shutil.copy(src, out / name)
            kept.append(name)
    sf = run_dir / "specflow"
    if sf.exists():
        for name in ("requirements.json", "testplan.json", "coverage_model.json",
                     "ref_model.py", "s1_gate.json", "s2_gate.json", "s3_gate.json",
                     "refmodel_gate.json"):
            src = sf / name
            if src.exists():
                shutil.copy(src, out / name)
                kept.append(f"specflow/{name}")
    return kept


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="assemble_baseline")
    p.add_argument("--task", required=True)
    p.add_argument("--arm-a", required=True, help="arm A run directory")
    p.add_argument("--arm-b", required=True, help="arm B run directory")
    p.add_argument("--dest", default=None)
    args = p.parse_args(argv)

    dest = Path(args.dest or REPO_ROOT / "benchmarks" / "baselines" / args.task)
    dest.mkdir(parents=True, exist_ok=True)

    a, b = Path(args.arm_a), Path(args.arm_b)
    summary = {
        "task": args.task,
        "arm_a": _arm_summary(a),
        "arm_b": _arm_summary(b),
        "arm_a_artifacts": _copy_artifacts(a, dest, "a"),
        "arm_b_artifacts": _copy_artifacts(b, dest, "b"),
    }
    (dest / "baseline.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    def verdict(arm: dict) -> str:
        s = arm.get("score") or {}
        if not s:
            return "not scored"
        return f"{s.get('status')} (flow={s.get('flow')}, proof={s.get('proof_type')})"

    (dest / "README.md").write_text(f"""# ChipVerilog baseline: `{args.task}`

Two arms of Veri-Sure on the same task, same model, same reasoning effort.

| | arm A | arm B |
| --- | --- | --- |
| what | pre-hardening SystemVerilog testbench path | specflow spec-grounded chain |
| verdict | {verdict(summary['arm_a'])} | {verdict(summary['arm_b'])} |
| produced RTL | {summary['arm_a']['produced_rtl']} | {summary['arm_b']['produced_rtl']} |

## How to read these numbers

**Which oracle decided.** ChipVerilog is level-aware: an iverilog compile gate,
then a self-checking simulation testbench where the task ships one, otherwise a
Yosys equivalence proof. Only 6 task directories ship a testbench and only 11
tasks were ever decided by one, so for most tasks -- including this one unless
`flow` says `simulation_tb` -- the verdict is an equivalence result and **not** a
testbench pass rate.

**This environment is not the published one.** Re-verifying the five published
`claude` candidates for `i2c_master_top` reproduces 3 of 5. Both disagreements
move `compile_fail` to `function_fail`, because this iverilog accepts candidates
the published environment rejected. The pass count reproduces exactly (0 of 5
both ways), so pass/fail is comparable with published numbers while the failure
*category* is environment-local. Both arms are scored by one invocation, so they
remain comparable with each other regardless.

**What arm A is.** The merge-base tree with the agent hardening absent --
`specflow/` gone, `tb_generator.py`, `_run_instance` and `TB_4_SHOT_EXAMPLES`
present -- plus two things that are not hardening: transport (that tree cannot
reach this model at all) and hierarchy plumbing (inert on a leaf task).
`make_arm_a.sh` reconstructs it and re-checks those properties.

**Neither arm receives golden RTL.** The two are comparable to each other; they
are not directly comparable to ChipVerilog's published table, whose flow
prechecks a reference design.

## Contents

Veri-Sure's own outputs only. The vendored task under
`benchmarks/chipverilog/Des/` is referenced, not copied: that tree carries
third-party licensing (LGPL for OR1200/MIPS/FPU, BSD for I2C) and `VENDORED.md`
warns that copies drift from the notice governing them. Derived artifacts here
-- `requirements.json` above all -- quote spec fragments verbatim by design.
""", encoding="utf-8")

    print(json.dumps(summary, indent=2)[:1500])
    print(f"\nwritten to {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
