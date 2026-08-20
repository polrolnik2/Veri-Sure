#!/usr/bin/env python3
"""Does the harness actually exercise each ChipVerilog design? No model calls.

The expensive question -- "is the oracle right?" -- needs a per-design reference
model and costs a full specflow run. This asks the cheap one that has to be true
first: given a design and a stimulus, does the testbench clock it, reset it, and
make its outputs move at all?

A design whose outputs never change was not verified, whatever its suite
reported. That failure mode is not hypothetical: `runtime.py` looked the clock up
as `getattr(dut, "clk")`, so on the 22 of 64 task modules that name it `clock`,
`Clock`, `CLK` or `clk_i` there was no clock, `Env.start` never called `reset()`,
nothing drove the reset either, and the design sat frozen while every check
compared two constants and passed.

Costs nothing but Verilator time, so it runs over the whole benchmark rather
than a sample -- which is the point, since the bug it looks for is exactly the
kind that hides on the one design you happened to test.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

DES = REPO / "benchmarks" / "chipverilog" / "Des"

from specflow.ports import classify, idle_values, input_names  # noqa: E402

_PORT_RE = re.compile(r"module\s+(\w+)\s*\((.*?)\);", re.S)
_DECL_RE = re.compile(
    r"\b(input|output|inout)\b\s*(?:wire|reg|logic)?\s*(?:signed\s*)?"
    r"(?:\[\s*([^\]]+?)\s*:\s*([^\]]+?)\s*\])?\s*([A-Za-z_]\w*)"
)


def contract_from_rtl(path: Path) -> dict | None:
    """Recover a contract from the reference RTL's port list.

    The real pipeline gets this from the Architect. Here the RTL is the source of
    truth on purpose: this probe tests the HARNESS, so introducing a generated
    contract would let a contract error masquerade as a harness error.
    """
    text = path.read_text(errors="replace")
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    text = re.sub(r"//[^\n]*", "", text)
    m = _PORT_RE.search(text)
    if not m:
        return None
    top = m.group(1)
    io, seen = [], set()
    for direction, hi, lo, name in _DECL_RE.findall(text):
        if name in seen:
            continue
        seen.add(name)
        width = 1
        if hi is not None and hi != "":
            try:
                width = abs(int(hi) - int(lo)) + 1
            except (TypeError, ValueError):
                width = 1        # a parameterised width; 1 is enough to drive
        io.append({"name": name, "dir": direction, "width": min(width, 32)})
    if not io:
        return None
    return {"module_name": top, "io": io,
            "clocking": {"is_sequential": bool(re.search(r"posedge|negedge", text))},
            "timing": {}}


def probe(task_dir: Path, work: Path, cycles: int = 64) -> dict:
    """Clock the design, wiggle its inputs, and report whether anything moved."""
    from cocotb_tools.runner import get_runner

    name = task_dir.name
    rtl = task_dir / f"{name}.v"
    contract = contract_from_rtl(rtl)
    if contract is None:
        return {"task": name, "status": "no_ports"}

    clocks, resets, functional = classify(contract)
    outs = [p["name"] for p in contract["io"] if p["dir"] == "output"]
    if not outs:
        return {"task": name, "status": "no_outputs"}

    tests = work / "tests"
    tests.mkdir(parents=True, exist_ok=True)
    (tests / "__init__.py").write_text("", encoding="utf-8")
    (tests / "probe.py").write_text(_TEST.format(
        outs=outs, functional=functional, resets=resets,
        idle=idle_values(contract), inputs=input_names(contract),
        cycles=cycles, out=str(work / "result.json"),
    ), encoding="utf-8")

    # The family directory and the task directory, exactly as
    # `run_chipverilog.py` supplies them: several designs `include` a shared
    # defines header that lives one level up (i2c's command encodings, or1200's
    # register map), and without it they do not elaborate at all.
    includes = [str(task_dir), str(task_dir.parent)]
    runner = get_runner("verilator")
    try:
        runner.build(
            sources=[str(rtl)], hdl_toplevel=contract["module_name"],
            includes=includes,
            build_args=["--no-timing", "-Wno-fatal"],
            build_dir=str(work / "build"), always=True,
        )
    except Exception as exc:  # noqa: BLE001
        return {"task": name, "status": "build_fail", "reason": str(exc)[:200]}

    try:
        runner.test(test_module=["probe"], hdl_toplevel=contract["module_name"],
                    test_dir=str(tests), results_xml=str(work / "r.xml"))
    except SystemExit:
        pass
    res = work / "result.json"
    if not res.exists():
        return {"task": name, "status": "no_record"}
    rec = json.loads(res.read_text(encoding="utf-8"))
    rec["task"] = name
    rec["clock"] = clocks[0] if clocks else None
    rec["status"] = "live" if rec.get("moved") else "frozen"
    return rec


_TEST = '''"""Generated liveness probe. Do not edit."""
import json
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer

OUTS = {outs!r}
FUNCTIONAL = {functional!r}
RESETS = {resets!r}
IDLE = {idle!r}
CYCLES = {cycles}


def _read(dut, n):
    try:
        return int(getattr(dut, n).value)
    except Exception:
        return None


@cocotb.test()
async def liveness(dut):
    from specflow.ports import is_clock
    clk = None
    for name in {inputs!r}:
        if is_clock(name):
            clk = getattr(dut, name, None)
            if clk is not None:
                break
    seen = {{o: set() for o in OUTS}}
    if clk is None:
        # Combinational: no edges to wait for, but the inputs still have to be
        # driven. Reading the outputs once without touching the inputs reports
        # every combinational design as "frozen", which says nothing about the
        # harness and everything about the probe.
        for n in {inputs!r}:
            h = getattr(dut, n, None)
            if h is not None:
                h.value = int(IDLE.get(n, 0))
        for c in range(CYCLES):
            for i, n in enumerate(FUNCTIONAL):
                h = getattr(dut, n, None)
                if h is not None:
                    h.value = (c >> (i % 5)) & 1 if c % 2 else (c + i) & 1
            await Timer(1, unit="ns")
            for o in OUTS:
                v = _read(dut, o)
                if v is not None:
                    seen[o].add(v)
    else:
        cocotb.start_soon(Clock(clk, 10, unit="ns").start())
        for n in {inputs!r}:
            h = getattr(dut, n, None)
            if h is not None and not is_clock(n):
                h.value = int(IDLE.get(n, 0))
        for n in RESETS:
            h = getattr(dut, n, None)
            if h is not None:
                h.value = 1 - int(IDLE.get(n, 0))
        for _ in range(3):
            await RisingEdge(clk)
        for n in RESETS:
            h = getattr(dut, n, None)
            if h is not None:
                h.value = int(IDLE.get(n, 0))
        for c in range(CYCLES):
            for i, n in enumerate(FUNCTIONAL):
                h = getattr(dut, n, None)
                if h is not None:
                    h.value = (c >> (i % 5)) & 1 if c % 2 else (c + i) & 1
            await RisingEdge(clk)
            await Timer(1, unit="step")
            for o in OUTS:
                v = _read(dut, o)
                if v is not None:
                    seen[o].add(v)
    moved = sorted(o for o, vs in seen.items() if len(vs) > 1)
    json.dump({{"moved": moved, "outputs": OUTS,
               "constant": sorted(set(OUTS) - set(moved)),
               "clocked": clk is not None}}, open({out!r}, "w"))
'''


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="harness_liveness")
    ap.add_argument("--out", default=str(REPO / "benchmarks" / "liveness.json"))
    ap.add_argument("--work", default="/tmp/liveness")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--task", default="")
    args = ap.parse_args(argv)

    tasks = sorted({p.parent for p in DES.rglob("description.txt")})
    if args.task:
        tasks = [t for t in tasks if t.name == args.task]
    if args.limit:
        tasks = tasks[: args.limit]

    work_root = Path(args.work)
    if work_root.exists():
        shutil.rmtree(work_root)
    rows = []
    for i, t in enumerate(tasks, 1):
        try:
            row = probe(t, work_root / t.name)
        except Exception as exc:  # noqa: BLE001
            row = {"task": t.name, "status": "probe_error", "reason": str(exc)[:200]}
        rows.append(row)
        print(f"[{i}/{len(tasks)}] {row['task']:<26} {row['status']:<12} "
              f"clock={row.get('clock')} constant={len(row.get('constant') or [])}"
              f"/{len(row.get('outputs') or [])}", flush=True)
    Path(args.out).write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")
    live = sum(1 for r in rows if r["status"] == "live")
    print(f"\nlive {live}/{len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
