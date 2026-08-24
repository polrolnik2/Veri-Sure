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


def child_sources(kids: list[str]) -> list[Path]:
    """Locate each child's reference .v in the Des tree.

    ChipVerilog supplies these to the candidate itself -- both the compile gate
    and the Yosys miter read `<candidate>.v` alongside the children -- so a
    candidate is expected to instantiate them rather than reimplement them.
    Supplying the same files to the simulator is what lets a hierarchical DUT
    elaborate here too.
    """
    out = []
    for k in kids:
        # A child that is itself a task comes first -- that file is the one the
        # benchmark scores against. Failing that, ANY definition in the tree:
        # `or1200_rf` instantiates `rf_sub`, which is not a task and lives
        # inside another module's file, so requiring a task directory left 20
        # of the 64 references unable to elaborate at all.
        hits = [p for p in DES.rglob(f"{k}.v") if p.parent.name == k]
        if not hits:
            hits = sorted(DES.rglob(f"{k}.v"))
        if not hits:
            hits = sorted((REPO_ROOT / "benchmarks" / "chipverilog" / "Src").rglob(f"{k}.v"))
        out.extend(hits[:1])
    return out


def submodules(task_dir: Path, top: str) -> list[str]:
    """Modules this task's reference instantiates but does not define.

    A task with any is *hierarchical*. The children are supplied to the
    simulator as libraries, never to the oracle: the reference model still has
    to derive the composed behaviour from the specification.
    """
    import re

    def strip(text: str) -> str:
        text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
        return re.sub(r"//[^\n]*", "", text)

    defined = set()
    for path in DES.rglob("*.v"):
        defined |= set(re.findall(r"^\s*module\s+(\w+)", strip(path.read_text(errors="ignore")), re.M))

    keywords = {
        "if", "else", "for", "while", "case", "begin", "end", "assign", "always",
        "module", "endmodule", "input", "output", "inout", "wire", "reg",
        "parameter", "localparam", "initial", "posedge", "negedge", "function",
        "task", "generate", "endgenerate", "defparam",
    }

    def instantiated(path: Path) -> tuple[set[str], set[str]]:
        src = strip(path.read_text(errors="ignore"))
        own = set(re.findall(r"^\s*module\s+(\w+)", src, re.M))
        found = re.findall(
            r"^[ \t]*(\w+)[ \t]+(?:#\s*\([^;]*?\)[ \t\n]*)?(\w+)[ \t]*\(", src, re.M)
        return {m for m, _ in found if m in defined and m not in keywords}, own

    # TRANSITIVE. A child's own children are needed too, and stopping at depth
    # one left 15 of the 64 references unable to elaborate: `i2c_master_top`
    # instantiates `i2c_master_byte_ctrl`, which instantiates
    # `i2c_master_bit_ctrl` -- and the grandchild was never supplied, so
    # Verilator stopped with MODMISSING on a design whose whole subtree is in
    # the tree.
    seen: set[str] = set()
    queue = [(task_dir / f"{top}.v", {top})]
    while queue:
        path, defined_here = queue.pop()
        kids, own = instantiated(path)
        for kid in sorted(kids - own - defined_here - seen):
            seen.add(kid)
            for child in child_sources([kid]):
                queue.append((child, defined_here | own | {kid}))
    return sorted(seen)


def control_model(top: str) -> str | None:
    """A hand-written reference model known to be right, if this design has one.

    Trust gate 3 discards oracles that a correct model fails, and it is the only
    gate that can: gate 1 asks an oracle to agree with its author about the
    GENERATED model, which an oracle overfitted to that model satisfies by
    construction. Measured on a-i2c with no control supplied, the generated
    model passed 35 of 54 trusted oracles while the control passed 25 -- the
    oracles preferred the model they were written against to the one that is
    actually correct.

    Only i2c_master_bit_ctrl has one today, so most runs still get None and gate
    3 still does not run. That is a gap in coverage, not a silent pass: it is
    why `Screened.rates()` reports `over_strict` separately rather than folding
    it into a single trust number.
    """
    path = Path(__file__).parent / "controls" / top / "ref_model.py"
    return str(path) if path.is_file() else None


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
        "command": " ".join(cmd),
        "language_flag": cmd[1],
    }


async def run(args: argparse.Namespace) -> dict:
    task_dir = find_task(args.task)
    top = task_dir.name
    from specflow.model_io import PortSettings

    port_settings = PortSettings(
        model=args.model,
        effort=args.effort,
        api_flavor=args.api_flavor,
        stream=args.stream,
        small_model=args.small_model,
        small_effort=args.small_effort,
        full_strength_stages=frozenset(
            x.strip() for x in (args.full_strength_stages or "").split(",") if x.strip()
        ),
        max_output_tokens=args.max_output_tokens,
        responses_chunk=args.responses_chunk,
        stream_retries=args.stream_retries,
        max_retries=args.api_max_retries,
        timeout_s=args.api_timeout,
    )

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

    kid_files = child_sources(kids)
    # or1200 children need or1200_defines.v / timescale.v from the family root.
    inc_dirs = sorted({str(p.parent) for p in kid_files} | {str(task_dir.parent), str(task_dir)})
    record["child_sources"] = [p.name for p in kid_files]
    record["include_dirs"] = inc_dirs

    agent = TopAgent(
        cfg,
        config=TopAgentConfig(
            tb_backend="specflow",
            specflow_model_port="api",
            specflow_port_settings=port_settings,
            sim_max_retry=args.sim_max_retry,
            debug_max_trials=args.debug_max_trials,
            specflow_extra_sources=tuple(str(p) for p in kid_files),
            specflow_include_dirs=tuple(inc_dirs),
            specflow_reuse=bool(getattr(args, "reuse", False)),
            specflow_divide_s1=not getattr(args, "generative_s1", False),
            specflow_fanout=not getattr(args, "no_fanout", False),
            specflow_max_repairs=args.max_repairs,
            specflow_refmodel_max_repairs=args.refmodel_max_repairs,
            specflow_refmodel_debug_attempts=args.refmodel_debug_attempts,
            specflow_refmodel_judge_turns=args.refmodel_judge_turns,
            specflow_refmodel_control=control_model(top),
            specflow_compare_oracles=args.compare_oracles,
            specflow_oracle_driven=args.oracle_driven,
            specflow_variants=args.variants,
            specflow_adequacy_rounds=args.adequacy_rounds,
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

    # specflow's ApiPort writes a per-call record, so its share is recoverable
    # from disk and separable from the eda_agent agents' share. Knowing which
    # half of the bill the oracle costs is the point.
    agent_io = out / "agent_io"
    sflow = {"calls": 0, "prompt": 0, "completion": 0, "reasoning": 0}
    for meta in sorted(agent_io.glob("*_meta.json")) if agent_io.exists() else []:
        u = (json.loads(meta.read_text(encoding="utf-8")).get("usage") or {})
        if not u:
            continue
        sflow["calls"] += 1
        sflow["prompt"] += u.get("prompt_tokens", 0)
        sflow["completion"] += u.get("completion_tokens", 0)
        sflow["reasoning"] += (u.get("completion_tokens_details") or {}).get(
            "reasoning_tokens") or 0
    record.setdefault("tokens", {})["specflow"] = sflow

    record["compile_gate"] = compile_gate(out / "rtl.sv", top, kid_files, task_dir)
    record["submodule_sources_supplied"] = [p.name for p in kid_files]

    (out / "baseline.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return record


def build_parser() -> argparse.ArgumentParser:
    """The CLI, built where a test can read it.

    Extracted so the switch list is checkable: every one of these
    replaced an environment variable, and an environment variable is
    settled by whichever file a callee re-reads rather than by the
    caller. A knob reachable only from Python is not a runtime switch.
    """
    p = argparse.ArgumentParser(prog="run_chipverilog")
    p.add_argument("--task", required=True, help="module name, e.g. i2c_master_top")
    p.add_argument("--out", required=True, help="run directory")
    p.add_argument("--max-tokens", type=int, default=40000)
    p.add_argument("--sim-max-retry", type=int, default=2)
    p.add_argument("--debug-max-trials", type=int, default=6)
    p.add_argument("--env-file", default=str(REPO_ROOT / ".env.local"),
                   help="credentials only. Every behavioural knob below is a "
                        "switch, because an env file is read by callees and "
                        "silently overrides what the caller asked for.")
    g = p.add_argument_group("model switches (explicit; never ambient)")
    g.add_argument("--model", help="whole-artifact model; overrides the env file")
    g.add_argument("--effort", help="reasoning effort: low|medium|high|xhigh. "
                                    "`max` is not accepted by every gateway.")
    g.add_argument("--api-flavor", choices=("chat", "responses"))
    g.add_argument("--stream", dest="stream", action="store_true", default=None)
    g.add_argument("--no-stream", dest="stream", action="store_false")
    g.add_argument("--small-model", help="model for the narrow fanned-out stages")
    g.add_argument("--small-effort")
    g.add_argument("--full-strength-stages", default="refmodel",
                   help="comma-separated stages the small model must NOT touch. "
                        "`refmodel` above all: every check compares the design "
                        "against it.")
    g.add_argument("--max-output-tokens", type=int, default=48000)
    g.add_argument("--responses-chunk", type=int, default=9000,
                   help="per-continuation output slice. One long call goes "
                        "silent long enough to be reaped; this bounds it.")
    g.add_argument("--stream-retries", type=int, default=2,
                   help="retries for a DROPPED stream, which is intermittent "
                        "on some gateways. Cheap because work is chunked.")
    g.add_argument("--api-max-retries", type=int, default=8)
    g.add_argument("--api-timeout", type=float, default=600.0)
    p.add_argument(
        "--max-repairs", type=int, default=3,
        help="repair rounds per specflow stage before the node hard-fails.",
    )
    p.add_argument(
        "--refmodel-max-repairs", type=int, default=6,
        help="repair rounds for the reference model, which gets its own budget: "
             "its feedback comes from a per-requirement judge rather than a "
             "script, and it converges. Measured on i2c_master_bit_ctrl, "
             "blocking verdicts fell 8 -> 4 -> 3 -> 2 over four rounds and the "
             "node then hard-failed with the trajectory still descending.",
    )
    p.add_argument(
        "--generative-s1", action="store_true",
        help="use the generative decomposition instead of dividing the spec at "
             "authorial boundaries. For A/B against the committed baselines.",
    )
    p.add_argument(
        "--no-fanout", action="store_true",
        help="run S2, S3 and the reference model as one batched call each "
             "instead of one small call per item.",
    )
    p.add_argument(
        "--refmodel-debug-attempts", type=int, default=6,
        help="edit attempts per reference-model debug turn; 0 disables the "
             "agentic path and repairs by regenerating from the judge's prose, "
             "which is what every run did before it existed",
    )
    p.add_argument(
        "--adequacy-rounds", type=int, default=0,
        help="After the debug loop converges, mutate the SHIPPED model and "
             "re-ask any oracle a mutant got past. 0 measures adequacy and "
             "acts on nothing, which is the default: the rate has to be "
             "known before it is allowed to spend calls.",
    )
    p.add_argument(
        "--variants", action="store_true",
        help="Generate k violating variants per requirement from the "
             "requirement TEXT, and convict an oracle no variant of its own "
             "requirement can fail. Costs k calls per requirement, once. "
             "Implies --compare-oracles.",
    )
    p.add_argument(
        "--oracle-driven", action="store_true",
        help="Let the requirement-only oracles DRIVE the refmodel repair loop. "
             "Blocking verdicts become the outcome of running them, decided "
             "transactionally, and the judge stops deciding. Implies "
             "--compare-oracles.",
    )
    p.add_argument(
        "--compare-oracles", action="store_true",
        help="Also generate an oracle set from the requirements alone, screen "
             "it beside the judge's, and report both in trust.json. Read-only: "
             "the judge's oracles still drive the loop, so the run stays a "
             "valid regression test. Costs one call per requirement, once.",
    )
    p.add_argument(
        "--refmodel-judge-turns", type=int, default=3,
        help="judging passes over the reference model. Each is ~one model call "
             "per requirement and is the expensive budget; the debug attempts "
             "inside a turn are pure Python and near-free",
    )
    p.add_argument(
        "--reuse", action="store_true",
        help="reuse certified specflow artifacts already in --out instead of "
             "regenerating them. The gates are always re-run on what is reused, "
             "so this skips the model calls and none of the checks.",
    )
    p.add_argument(
        "--no-rollback-guard", action="store_true",
        help="keep an RTL edit even when it increases the mismatch count. The "
             "guard is a hill-climber, so a repair that needs several parts to "
             "land together is rejected at every partial step; without it the "
             "search can cross that valley. The best RTL seen is still what the "
             "run returns, so this cannot end worse than it started.",
    )
    p.add_argument(
        "--stall-rounds", type=int, default=None,
        help="consecutive rounds without beating the best mismatch count before "
             "the debug loop gives up (default 2). Worth raising alongside "
             "--no-rollback-guard, which needs several non-improving rounds by "
             "construction.",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    p = build_parser()
    args = p.parse_args(argv)

    # A running container cannot re-read its own environment, so credentials
    # rotated after start only arrive through a file. See specflow.model_io.
    # Both halves, or the flag is a lie. Updating `os.environ` is not enough:
    # every specflow port calls `load_env_file()` itself, which reads
    # `SPECFLOW_ENV_FILE` or falls back to `.env.local` -- and those values
    # OVERRIDE the process environment by design, because a rotated key must be
    # able to reach a running session. So `--env-file other.env` set the
    # environment and was then silently overwritten by `.env.local` inside every
    # stage. Measured: a run launched with an env file naming `high` did its
    # reference-model generation at `xhigh`, and the only reason anyone noticed
    # was that a failure message happened to print the effort it used.
    os.environ["SPECFLOW_ENV_FILE"] = str(Path(args.env_file))
    os.environ.update(load_env_file(Path(args.env_file)))

    # AFTER the env file, so an explicit flag beats a stale value left in
    # .env.local. Read in RTLEditor rather than passed down the call chain,
    # which runs through TopAgent and would mean threading a debug-loop knob
    # through an orchestrator that has no other reason to know about it.
    if args.no_rollback_guard:
        os.environ["EDA_ROLLBACK_GUARD"] = "off"
    if args.stall_rounds is not None:
        os.environ["EDA_STALL_ROUNDS"] = str(args.stall_rounds)

    record = asyncio.run(run(args))
    print(json.dumps({k: v for k, v in record.items() if k != "traceback"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
