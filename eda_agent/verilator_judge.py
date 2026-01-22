from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
import re
import shutil
import subprocess
import time


@dataclass(frozen=True)
class VerilatorRunResult:
    passed: bool
    mismatches: int | None
    timed_out: bool
    compile_returncode: int
    run_returncode: int | None
    log: str
    run_dir: str


def _require_executable(name: str) -> None:
    if shutil.which(name) is None:
        raise FileNotFoundError(f"Required executable '{name}' not found in PATH.")


_MISMATCH_RE = re.compile(r"^\s*Mismatches:\s*(\d+)\s*in\s*(\d+)\s*samples\s*$", re.MULTILINE)


def run_verilator_testbench_sync(
    *,
    run_dir: Path,
    top: str,
    verilog_files: list[Path],
    timeout_s: float = 30.0,
    compile_args: list[str] | None = None,
) -> VerilatorRunResult:
    """Compile and run a Verilog/SystemVerilog testbench with Verilator.

    Args:
        run_dir:
            Directory to place build artifacts and run the simulation in.
        top:
            Top-level module name (passed to `verilator --top-module`).
        verilog_files:
            List of Verilog/SystemVerilog source file paths.
        timeout_s:
            Simulation timeout in seconds.
        compile_args:
            Extra args appended to the `verilator` command.
    """
    _require_executable("verilator")

    run_dir = run_dir.expanduser().resolve()
    run_dir.mkdir(parents=True, exist_ok=True)

    compile_args = compile_args or []
    sim_bin = run_dir / "sim.bin"
    obj_dir = run_dir / "obj_dir"

    verilog_files = [p.expanduser().resolve() for p in verilog_files]

    cmd_compile = [
        "verilator",
        "--binary",
        "-j",
        "0",
        "--sv",
        "--timing",
        "--trace",
        "--assert",
        "-Wall",
        "-Wno-fatal",
        "--top-module",
        top,
        "--Mdir",
        str(obj_dir),
        "-o",
        str(sim_bin),
        *compile_args,
        *[str(p) for p in verilog_files],
    ]

    log_lines: list[str] = []
    log_lines.append(f"INFO: Running command: {' '.join(cmd_compile)}\n")

    cp = subprocess.run(
        cmd_compile,
        cwd=str(run_dir),
        capture_output=True,
        text=True,
    )
    if cp.stdout:
        log_lines.append(cp.stdout)
    if cp.stderr:
        log_lines.append(cp.stderr)

    if cp.returncode != 0:
        log = "".join(log_lines)
        return VerilatorRunResult(
            passed=False,
            mismatches=None,
            timed_out=False,
            compile_returncode=cp.returncode,
            run_returncode=None,
            log=log,
            run_dir=str(run_dir),
        )

    cmd_run = [str(sim_bin)]
    log_lines.append(f"INFO: Running command: {' '.join(cmd_run)}\n")
    timed_out = False
    run_returncode: int | None = None
    try:
        rp = subprocess.run(
            cmd_run,
            cwd=str(run_dir),
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
        run_returncode = rp.returncode
        if rp.stdout:
            log_lines.append(rp.stdout)
        if rp.stderr:
            log_lines.append(rp.stderr)

    except subprocess.TimeoutExpired as e:
        timed_out = True
        if e.stdout:
            log_lines.append(e.stdout)
        if e.stderr:
            log_lines.append(e.stderr)
        log_lines.append("TIMEOUT\n")

    log = "".join(log_lines)
    mismatches: int | None = None

    m = _MISMATCH_RE.search(log)
    if m:
        mismatches = int(m.group(1))

    passed_by_log = ("SIMULATION PASSED" in log) or (mismatches == 0 if mismatches is not None else False)
    passed = passed_by_log and not timed_out and (run_returncode == 0)

    return VerilatorRunResult(
        passed=passed,
        mismatches=mismatches,
        timed_out=timed_out,
        compile_returncode=cp.returncode,
        run_returncode=run_returncode,
        log=log,
        run_dir=str(run_dir),
    )


def write_verilator_result_json(run_dir: Path, result: VerilatorRunResult) -> None:
    run_dir = run_dir.expanduser().resolve()
    (run_dir / "verilator_result.json").write_text(
        json.dumps(asdict(result), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def make_timestamped_dir(parent: Path, prefix: str) -> Path:
    ts = time.strftime("%Y%m%d-%H%M%S")
    parent.mkdir(parents=True, exist_ok=True)
    return parent / f"{prefix}_{ts}_{int(time.time() * 1e6)}"
