"""byte_ctrl_codes.py -- what byte_ctrl's command encoding (and a held command) is worth, measured.

Every i2c_master_byte_ctrl design in the study -- the three generations made with the real child
(`<run>/editor-cf-gen`) and all six repaired finals -- codes the bit-level commands READ=0100,
WRITE=1000. The header both the child and golden use (`i2c_master_defines.v`) defines them the
other way round, and the specification gives no numeric codes, so no generator, check or
reference model could derive them. With the child stand-in gone they decide what the child does.

For each run's real-child start this applies ONE small text edit at a time and re-simulates it
with the e7_behaviour testbench on the run's own stimulus (iverilog, the real child, golden as the
reference, golden's x cells don't-care -- the same scoring as `metrics.py`):

  start        the design as generated
  codes        READ=1000, WRITE=0100 -- the two constants only
  hold         (luna14 only) core_cmd held until the FSM returns to idle instead of falling to NOP
               every cycle
  hold+codes   (luna14 only) both

and reports, per design: g = % of edges whose outputs all equal golden's; al = % of edges with
i2c_al high and the testpoints it appears in; unk = % of output cells that are x/z in this
four-state simulation. The same three figures are given for golden, for scale -- `i2c_al` is high
on about 1% of golden's own edges (the stimulus provokes arbitration loss), so a design whose
al activity matches golden's has no spurious arbitration loss. luna12's model-feedback final is
included only for its unknown cells (its multiply-driven overrides resolve to x here).

Needs `sim.py` to have run first (it writes the testbench and stimulus text this reuses).
-> docs/evidence/e7/BYTE-CTRL-CODES.json, and a markdown table on stdout.

    E7_BEHAVIOUR_WORK=/path/to/work python byte_ctrl_codes.py
"""

import json
import os
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
EQ = Path(os.environ.get("E7_BEHAVIOUR_WORK", "/tmp/e7_behaviour"))
E = ROOT / "docs" / "evidence" / "e7"
TASK = ROOT / "benchmarks" / "chipverilog" / "Des" / "i2c" / "i2c_master_byte_ctrl"
CHILD = ROOT / "benchmarks" / "chipverilog" / "Des" / "i2c" / "i2c_master_bit_ctrl" / "i2c_master_bit_ctrl.v"
M = "i2c_master_byte_ctrl"

CODES = [
    ("    localparam [3:0] I2C_CMD_READ  = 4'b0100;", "    localparam [3:0] I2C_CMD_READ  = 4'b1000;"),
    ("    localparam [3:0] I2C_CMD_WRITE = 4'b1000;", "    localparam [3:0] I2C_CMD_WRITE = 4'b0100;"),
]
#: luna14's start clears core_cmd every cycle; the specification names NOP as an action only on the
#: two returns to idle, and the child samples cmd only on clk_en, so a pulse is lost.
HOLD = [
    ("            core_cmd_r <= I2C_CMD_NOP;\n            cmd_ack <= 1'b0;\n\n            case (state_r)",
     "            cmd_ack <= 1'b0;\n\n            case (state_r)"),
    ("                            state_r <= ST_IDLE;\n                            cmd_ack <= 1'b1;",
     "                            state_r <= ST_IDLE;\n                            core_cmd_r <= I2C_CMD_NOP;\n                            cmd_ack <= 1'b1;"),
    ("                        state_r <= ST_IDLE;\n                        cmd_ack <= 1'b1;",
     "                        state_r <= ST_IDLE;\n                        core_cmd_r <= I2C_CMD_NOP;\n                        cmd_ack <= 1'b1;"),
]
JOBS = [
    ("luna12", "editor-cf-gen", [("start", []), ("codes", CODES)]),
    ("luna13", "editor-cf-gen", [("start", []), ("codes", CODES)]),
    ("luna14", "editor-cf-gen", [("start", []), ("codes", CODES), ("hold", HOLD), ("hold+codes", HOLD + CODES)]),
    ("luna12", "editor-cf-model", [("model final", [])]),
]


def stats(rows_by_tp, golden, al):
    """(edges equal to golden, edges compared, al-high edges, testpoints with al, unknown cells, cells)."""
    eq = n = ale = alt = unk = cells = 0
    for tp, rows in rows_by_tp.items():
        g = golden[tp]
        hit = False
        for i, r in enumerate(rows):
            cells += len(r)
            unk += sum(any(c in v for c in "xXzZ") for v in r)
            if r[al] == "1":
                ale += 1
                hit = True
            if i < len(g):
                n += 1
                eq += all(any(c in gv for c in "xXzZ") or gv == dv for gv, dv in zip(g[i], r))
        alt += hit
    return eq, n, ale, alt, unk, cells


def simulate(rtl: Path, run: str, tps: list[str]) -> dict:
    with tempfile.TemporaryDirectory() as td:
        vvp, out = Path(td, "d.vvp"), Path(td, "d.out")
        c = subprocess.run(["iverilog", "-g2012", "-s", "tb", "-o", str(vvp), f"-I{TASK}", f"-I{TASK.parent}",
                            str(EQ / "work" / M / "tb.v"), str(rtl), str(CHILD)], capture_output=True, text=True)
        if c.returncode:
            raise SystemExit("compile failed: " + c.stderr[-600:])
        subprocess.run(["vvp", "-n", str(vvp), f"+in={EQ / 'stimtxt' / run / (M + '.txt')}", f"+out={out}"],
                       capture_output=True, text=True, timeout=3600)
        per, cur = {tp: [] for tp in tps}, -1
        for line in out.read_text().splitlines():
            if line == "#":
                cur += 1
            else:
                per[tps[cur]].append(line.split())
        return per


def main() -> None:
    rows = []
    done_golden = set()
    for run, src, variants in JOBS:
        stim = json.loads((EQ / "stim" / run / f"{M}.json").read_text())
        tps, al = sorted(stim["tps"]), stim["outputs"].index("i2c_al")
        del stim
        golden = json.loads((EQ / "out" / M / "golden.json").read_text())[run]
        if run not in done_golden:
            done_golden.add(run)
            s = stats(golden, golden, al)
            rows.append({"run": run, "design": "golden", "g": 100.0, "al_edges": 100 * s[2] / s[1],
                         "al_tps": f"{s[3]}/{len(tps)}", "unknown_cells": 100 * s[4] / s[5]})
        base = (E / run / src / M / "rtl_deliverable.sv").read_text()
        for name, edits in variants:
            txt = base
            for old, new in edits:
                if old not in txt:
                    raise SystemExit(f"{run} {name}: edit text not found: {old[:60]!r}")
                txt = txt.replace(old, new)
            with tempfile.NamedTemporaryFile("w", suffix=".sv", delete=False) as fh:
                fh.write(txt)
            try:
                s = stats(simulate(Path(fh.name), run, tps), golden, al)
            finally:
                os.unlink(fh.name)
            rows.append({"run": run, "design": name, "g": 100 * s[0] / s[1], "edges": s[1],
                         "al_edges": 100 * s[2] / s[1], "al_tps": f"{s[3]}/{len(tps)}",
                         "unknown_cells": 100 * s[4] / s[5]})
            print(json.dumps(rows[-1]), flush=True)
        del golden
    (E / "BYTE-CTRL-CODES.json").write_text(json.dumps(rows, indent=1) + "\n")
    print("\n| run | design | edges equal to golden | i2c_al high | unknown cells |\n|---|---|---|---|---|")
    for r in rows:
        print(f"| {r['run']} | {r['design']} | {r['g']:.2f}% | {r['al_edges']:.2f}% ({r['al_tps']} testpoints) "
              f"| {r['unknown_cells']:.2f}% |")


main()
