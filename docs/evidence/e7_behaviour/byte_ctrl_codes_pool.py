"""byte_ctrl_codes_pool.py -- the checks-vs-ablation comparison for byte_ctrl with the command codes fixed.

byte_ctrl_codes.py showed that the bit-level command codes decide most of what a real-child
byte_ctrl does: the designs swap READ and WRITE relative to `i2c_master_defines.v`, and the
specification gives no values. This asks whether repair would look better had the generator
known them: every design of the byte_ctrl comparison (the real-child start `cfg`, the samples
`acg1..3`, the checks final `cfc`) gets the header's codes and nothing else, and is re-scored like
metrics.py (golden X don't-care):
  g_edge    edges equal to golden on every run's stimulus
  own_edge  the same on the design's own run's stimulus
  g_tp      whole testpoints equal, every run's stimulus
The edit: READ = 4'b1000, WRITE = 4'b0100. One sample (luna14 acg2) encodes the commands in three
bits (READ 3'b100, WRITE 3'b101); it gets the header's four-bit codes and a four-bit command register.
Needs sim.py's testbench, stimulus text and golden traces.
-> docs/evidence/e7/BYTE-CTRL-CODES-POOL.json
"""

import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
EQ = Path(os.environ.get("E7_BEHAVIOUR_WORK", "/tmp/e7_behaviour"))
E = ROOT / "docs" / "evidence" / "e7"
TASK = ROOT / "benchmarks" / "chipverilog" / "Des" / "i2c" / "i2c_master_byte_ctrl"
CHILD = TASK.parent / "i2c_master_bit_ctrl" / "i2c_master_bit_ctrl.v"
M = "i2c_master_byte_ctrl"
RUNS = ("luna12", "luna13", "luna14")
KINDS = {"cfg": "cf-gen", "acg1": "abl-child-gen1", "acg2": "abl-child-gen2", "acg3": "abl-child-gen3",
         "cfc": "cf-checks", "vc": "val-cons"}
THREE_BIT = [
    ("    localparam [2:0] I2C_CMD_NOP   = 3'b000,\n                     I2C_CMD_START = 3'b001,\n"
     "                     I2C_CMD_STOP  = 3'b010,\n                     I2C_CMD_READ  = 3'b100,\n"
     "                     I2C_CMD_WRITE = 3'b101;",
     "    localparam [3:0] I2C_CMD_NOP   = 4'b0000,\n                     I2C_CMD_START = 4'b0001,\n"
     "                     I2C_CMD_STOP  = 4'b0010,\n                     I2C_CMD_READ  = 4'b1000,\n"
     "                     I2C_CMD_WRITE = 4'b0100;"),
    ("    reg [2:0] core_cmd_r;", "    reg [3:0] core_cmd_r;"),
]


def fix_codes(txt: str) -> str:
    if "I2C_CMD_WRITE = 3'b101" in txt:
        for old, new in THREE_BIT:
            assert txt.count(old) == 1, old[:40]
            txt = txt.replace(old, new)
        return txt
    rd = re.compile(r"(I2C_CMD_READ\s*=\s*)4'b0100")
    wr = re.compile(r"(I2C_CMD_WRITE\s*=\s*)4'b1000")
    assert len(rd.findall(txt)) == 1 and len(wr.findall(txt)) == 1, "codes not found exactly once"
    return wr.sub(r"\g<1>4'b0100", rd.sub(r"\g<1>4'b1000", txt))


def simulate(rtl: str) -> dict:
    with tempfile.TemporaryDirectory() as td:
        src, vvp = Path(td, "d.sv"), Path(td, "d.vvp")
        src.write_text(rtl)
        c = subprocess.run(["iverilog", "-g2012", "-s", "tb", "-o", str(vvp), f"-I{TASK}", f"-I{TASK.parent}",
                            str(EQ / "work" / M / "tb.v"), str(src), str(CHILD)], capture_output=True, text=True)
        if c.returncode:
            raise SystemExit("compile failed: " + c.stderr[-600:])
        res = {}
        for run in RUNS:
            out = Path(td, f"{run}.out")
            subprocess.run(["vvp", "-n", str(vvp), f"+in={EQ / 'stimtxt' / run / (M + '.txt')}", f"+out={out}"],
                           capture_output=True, text=True, timeout=3600)
            tps = sorted(json.loads((EQ / "stim" / run / f"{M}.json").read_text())["tps"])
            per, cur = {tp: [] for tp in tps}, -1
            for line in out.read_text().splitlines():
                if line == "#":
                    cur += 1
                else:
                    per[tps[cur]].append(line.split())
            res[run] = per
        return res


def score(x, golden, runs):
    e = et = t = tt = 0
    for r in runs:
        for tp, g in golden[r].items():
            d = x[r][tp]
            ok = [all(any(c in gv for c in "xXzZ") or gv == dv for gv, dv in zip(gr, dr)) for gr, dr in zip(g, d)]
            e += sum(ok)
            et += max(len(g), len(d))
            t += len(g) == len(d) and all(ok)
            tt += 1
    return e / et, t / tt


def main():
    golden = json.loads((EQ / "out" / M / "golden.json").read_text())
    rows = []
    for run in RUNS:
        for kind, tag in KINDS.items():
            f = E / run / f"editor-{tag}" / M / "rtl_deliverable.sv"
            if not f.is_file():
                continue
            x = simulate(fix_codes(f.read_text()))
            g_edge, g_tp = score(x, golden, RUNS)
            own_edge, _ = score(x, golden, [run])
            rows.append({"run": run, "kind": kind, "g_edge": g_edge, "own_edge": own_edge, "g_tp": g_tp})
            print(json.dumps(rows[-1]), flush=True)
    (E / "BYTE-CTRL-CODES-POOL.json").write_text(json.dumps(rows, indent=1) + "\n")


main()
