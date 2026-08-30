"""Does handing the generator the shared defines file change how close it gets?

ChipVerilog ships `i2c_master_defines.v` inside the task package and
auto-prepends it to every compile, so a candidate could write `` `I2C_CMD_START ``
and be right for free. None of its 15 recorded designs does; all re-declare the
constants and every one that declared them guessed wrong, 8 of 9 with READ and
WRITE swapped. This asks whether that is the description's fault by giving half
the generators the file and telling them it is there.

TWO MEASURES, because one of them is the mechanism and the other is the outcome:

  encoding   does the design decode START=1, STOP=2, WRITE=4, READ=8? Direct,
             cheap, and the thing the intervention targets.
  mismatches a differential co-simulation against the golden RTL on shared
             random stimulus -- the outcome. Reported as the edge of the FIRST
             divergence and the count, because a design that diverges at edge 3
             and one that diverges at edge 900 are not equally close, and a
             mismatch total alone hides that.

The generators never saw the golden RTL: they were given a copy of
`description.txt` (and, in arm B, the defines) in an isolated directory and told
to read nothing else.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

S = Path("/tmp/claude-0/-home-user-Veri-Sure/12bb865e-7a51-5506-b55a-e5ac7cf72a4a/scratchpad/ab_defines")
BENCH = Path("/home/user/Veri-Sure/benchmarks/chipverilog/Des/i2c")
GOLDEN = BENCH / "i2c_master_bit_ctrl/i2c_master_bit_ctrl.v"
TRUE = {"START": 1, "STOP": 2, "WRITE": 4, "READ": 8}

OUTS = ["cmd_ack", "busy", "al", "dout", "scl_o", "scl_oen", "sda_o", "sda_oen"]

TB = r"""
`timescale 1ns/10ps
module tb;
  reg clk=0, rst=0, nReset=0, ena=0, din=0, scl_i=1, sda_i=1;
  reg [15:0] clk_cnt = 16'd3;
  reg [3:0] cmd = 4'd0;
  wire %(rw)s;
  integer i, mism = 0, first = -1;
  integer seed = 32'd12345;

  i2c_master_bit_ctrl        REF (.clk(clk),.rst(rst),.nReset(nReset),.ena(ena),
      .clk_cnt(clk_cnt),.cmd(cmd),.din(din),.scl_i(scl_i),.sda_i(sda_i),
      %(refports)s);
  cand_i2c_master_bit_ctrl   DUT (.clk(clk),.rst(rst),.nReset(nReset),.ena(ena),
      .clk_cnt(clk_cnt),.cmd(cmd),.din(din),.scl_i(scl_i),.sda_i(sda_i),
      %(dutports)s);

  always #5 clk = ~clk;

  initial begin
    nReset = 0; rst = 1; ena = 0;
    @(posedge clk); @(posedge clk);
    nReset = 1; rst = 0; ena = 1;
    @(posedge clk);
    for (i = 0; i < 4000; i = i + 1) begin
      @(posedge clk);
      #1;
      if (%(cmp)s) begin
        mism = mism + 1;
        if (first < 0) first = i;
      end
      // Drive a fresh scenario every few edges; the same seed feeds both.
      if (i %% 7 == 0) cmd   = ($random(seed) %% 5 == 0) ? 4'd0 :
                               (1 << ($random(seed) & 2'd3));
      if (i %% 3 == 0) din   = $random(seed);
      if (i %% 2 == 0) scl_i = ($random(seed) & 3) != 0;
      if (i %% 2 == 1) sda_i = ($random(seed) & 3) != 0;
      if (i %% 501 == 500) begin rst = 1; @(posedge clk); rst = 0; end
    end
    $display("MISMATCH %%0d FIRST %%0d", mism, first);
    $finish;
  end
endmodule
"""


def _tb() -> str:
    rw = ", ".join([f"r_{o}" for o in OUTS] + [f"d_{o}" for o in OUTS])
    return TB % {
        "rw": rw,
        "refports": ",".join(f".{o}(r_{o})" for o in OUTS),
        "dutports": ",".join(f".{o}(d_{o})" for o in OUTS),
        "cmp": " || ".join(f"(r_{o} !== d_{o})" for o in OUTS),
    }


def encoding_of(src: str) -> dict[str, int | None]:
    """START/STOP/WRITE/READ as this design declares them, however it declares
    them -- `define, localparam or parameter."""
    out: dict[str, int | None] = {}
    for name in TRUE:
        m = re.search(rf"(?:`define|localparam|parameter)\s*(?:\[[^\]]*\]\s*)?"
                      rf"\w*CMD_{name}\b\s*=?\s*(\d+)'([bodhBODH])([0-9a-fA-F_]+)", src)
        if m:
            base = {"b": 2, "o": 8, "d": 10, "h": 16}[m.group(2).lower()]
            out[name] = int(m.group(3).replace("_", ""), base)
        else:
            out[name] = None
    return out


def run(cand: Path, work: Path) -> dict:
    work.mkdir(parents=True, exist_ok=True)
    src = cand.read_text()
    row: dict = {"name": cand.stem, "encoding": encoding_of(src)}
    row["encoding_correct"] = row["encoding"] == TRUE

    renamed = re.sub(r"\bmodule\s+i2c_master_bit_ctrl\b",
                     "module cand_i2c_master_bit_ctrl", src, count=1)
    (work / "cand.v").write_text(renamed)
    (work / "tb.v").write_text(_tb())
    exe = work / "sim"
    build = subprocess.run(
        ["iverilog", "-g2005", f"-I{BENCH}", f"-I{BENCH / 'i2c_master_bit_ctrl'}",
         "-o", str(exe), str(work / "tb.v"), str(GOLDEN), str(work / "cand.v")],
        capture_output=True, text=True, timeout=180)
    row["compiles"] = build.returncode == 0
    if not row["compiles"]:
        row["error"] = build.stderr.strip().splitlines()[:3]
        return row
    sim = subprocess.run(["vvp", str(exe)], capture_output=True, text=True,
                         timeout=300)
    m = re.search(r"MISMATCH (\d+) FIRST (-?\d+)", sim.stdout)
    if not m:
        row["error"] = ["simulation produced no verdict"] + sim.stdout.splitlines()[-3:]
        return row
    row["mismatches"], row["first_divergence"] = int(m.group(1)), int(m.group(2))
    return row


def main() -> int:
    rows = []
    for cand in sorted((S / "out").glob("*.v")):
        rows.append(run(cand, S / "work" / cand.stem))
    if not rows:
        print("no candidates in", S / "out")
        return 1

    print(f"{'design':<8}{'arm':<5}{'compiles':<10}{'encoding':<34}"
          f"{'ok':<4}{'mismatch':>9}{'first':>7}")
    for r in rows:
        e = r["encoding"]
        enc = " ".join(f"{k[0]}{'.' if e[k] is None else e[k]}" for k in TRUE)
        print(f"{r['name']:<8}{r['name'][0]:<5}{str(r['compiles']):<10}{enc:<34}"
              f"{'Y' if r['encoding_correct'] else 'n':<4}"
              f"{r.get('mismatches', '-'):>9}{r.get('first_divergence', '-'):>7}")

    print()
    for arm in ("A", "B"):
        a = [r for r in rows if r["name"].startswith(arm)]
        if not a:
            continue
        ok = sum(r["encoding_correct"] for r in a)
        comp = sum(r["compiles"] for r in a)
        sims = [r["mismatches"] for r in a if "mismatches" in r]
        label = "description only" if arm == "A" else "description + defines"
        print(f"  arm {arm} ({label:<22}) n={len(a)}  compiles={comp}  "
              f"encoding correct={ok}/{len(a)}  "
              f"mismatches={sorted(sims) if sims else '-'}")
    json.dump(rows, open(S / "score.json", "w"), indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
