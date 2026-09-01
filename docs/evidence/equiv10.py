"""Differential co-simulation: run 10's design against the golden i2c bit controller.

GROUND TRUTH INDEPENDENT OF THE ORACLE SET. Every number reported so far comes
from the frozen 90 checks, and 12 of those provably convict the golden design --
so "run 10 passes 61" says as much about the checks as about the design. This
asks a question the checks cannot corrupt: driven by the SAME stimulus, do the
two designs produce the SAME outputs?

Both are instantiated side by side and fed identical inputs, so there is no
reference model, no activation, no window, and nothing to abstain. A divergence
is a divergence.

Reported as the FIRST diverging edge as well as the count, because a design that
diverges at edge 3 and one that diverges at edge 900 are not equally close and a
total alone hides that -- the same reason `ab_defines_score.py` reports both.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

BENCH = Path("/home/user/Veri-Sure/benchmarks/chipverilog/Des/i2c")
GOLDEN = BENCH / "i2c_master_bit_ctrl/i2c_master_bit_ctrl.v"
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
  // `n_` and not `d_`: the DUT's output wires are already d_<port>, and a
  // counter sharing that name is a redeclaration iverilog rejects.
  integer n_cmd_ack=0, n_busy=0, n_al=0, n_dout=0, n_scl_o=0, n_scl_oen=0,
          n_sda_o=0, n_sda_oen=0;

  i2c_master_bit_ctrl      REF (.clk(clk),.rst(rst),.nReset(nReset),.ena(ena),
      .clk_cnt(clk_cnt),.cmd(cmd),.din(din),.scl_i(scl_i),.sda_i(sda_i),
      %(refports)s);
  cand_i2c_master_bit_ctrl DUT (.clk(clk),.rst(rst),.nReset(nReset),.ena(ena),
      .clk_cnt(clk_cnt),.cmd(cmd),.din(din),.scl_i(scl_i),.sda_i(sda_i),
      %(dutports)s);

  always #5 clk = ~clk;

  initial begin
    nReset = 0; rst = 1; ena = 0;
    @(posedge clk); @(posedge clk);
    nReset = 1; rst = 0; ena = 1;
    @(posedge clk);
    for (i = 0; i < %(edges)d; i = i + 1) begin
      @(posedge clk);
      #1;
      %(pertally)s
      if (%(cmp)s) begin
        mism = mism + 1;
        if (first < 0) first = i;
      end
      // A fresh scenario every few edges; the same seed feeds both designs.
      if (i %% 7 == 0) cmd   = ($random(seed) %% 5 == 0) ? 4'd0 :
                               (1 << ($random(seed) & 2'd3));
      if (i %% 3 == 0) din   = $random(seed);
      if (i %% 2 == 0) scl_i = ($random(seed) & 3) != 0;
      if (i %% 2 == 1) sda_i = ($random(seed) & 3) != 0;
      if (i %% 501 == 500) begin rst = 1; @(posedge clk); rst = 0; end
    end
    $display("MISMATCH %%0d FIRST %%0d", mism, first);
    $display("PERPORT %(perfmt)s", %(perargs)s);
    $finish;
  end
endmodule
"""


def _tb(edges: int) -> str:
    rw = ", ".join([f"r_{o}" for o in OUTS] + [f"d_{o}" for o in OUTS])
    return TB % {
        "rw": rw,
        "edges": edges,
        "refports": ",".join(f".{o}(r_{o})" for o in OUTS),
        "dutports": ",".join(f".{o}(d_{o})" for o in OUTS),
        # X-TOLERANT. `!==` counts X-vs-0 as a divergence, and the GOLDEN
        # design has an unreset register: `dout` is written by
        # `always @(posedge clk) if (sSCL & ~dSCL) dout <= sSDA;` with no reset
        # branch, so it holds X until the first SCL rise. A candidate that DOES
        # reset dout to 0 -- which is the safer design -- therefore "diverged"
        # at edge 0 against a reference that simply had no value yet.
        #
        # That is not a behavioural disagreement, and reporting it as the first
        # divergence said the designs differ immediately when they in fact agree
        # on every other output for at least the first eight edges. A mismatch
        # is counted only where BOTH sides carry a known value.
        "cmp": " || ".join(
            f"(!(^r_{o} === 1'bx) && !(^d_{o} === 1'bx) && r_{o} !== d_{o})"
            for o in OUTS),
        "pertally": "\n      ".join(
            f"if (!(^r_{o} === 1'bx) && !(^d_{o} === 1'bx) && r_{o} !== d_{o}) "
            f"n_{o} = n_{o} + 1;" for o in OUTS),
        "perfmt": " ".join(f"{o}=%0d" for o in OUTS),
        "perargs": ", ".join(f"n_{o}" for o in OUTS),
    }


def main(cand_path: str, work_dir: str, edges: int = 4000) -> int:
    work = Path(work_dir)
    work.mkdir(parents=True, exist_ok=True)
    src = Path(cand_path).read_text()
    renamed = re.sub(r"\bmodule\s+i2c_master_bit_ctrl\b",
                     "module cand_i2c_master_bit_ctrl", src, count=1)
    (work / "cand.v").write_text(renamed)
    (work / "tb.v").write_text(_tb(edges))
    exe = work / "sim"
    build = subprocess.run(
        ["iverilog", "-g2005", f"-I{BENCH}", f"-I{BENCH / 'i2c_master_bit_ctrl'}",
         "-o", str(exe), str(work / "tb.v"), str(GOLDEN), str(work / "cand.v")],
        capture_output=True, text=True, timeout=300)
    if build.returncode != 0:
        print("BUILD FAILED")
        print("\n".join(build.stderr.strip().splitlines()[:12]))
        return 1
    sim = subprocess.run(["vvp", str(exe)], capture_output=True, text=True,
                         timeout=600)
    m = re.search(r"MISMATCH (\d+) FIRST (-?\d+)", sim.stdout)
    if not m:
        print("no verdict\n" + sim.stdout[-800:])
        return 1
    mism, first = int(m.group(1)), int(m.group(2))
    per = dict(re.findall(r"(\w+)=(\d+)", sim.stdout.split("PERPORT")[-1])) \
        if "PERPORT" in sim.stdout else {}

    print(f"edges compared         : {edges}")
    print(f"edges with a mismatch  : {mism}  ({100*mism/edges:.1f}%)")
    print(f"first divergence at    : edge {first}"
          + ("  (EQUIVALENT over this stimulus)" if first < 0 else ""))
    if per:
        print("per-output mismatches  :")
        for k, v in sorted(per.items(), key=lambda kv: -int(kv[1])):
            print(f"    {k:<9} {v}")
    json.dump({"edges": edges, "mismatches": mism, "first_divergence": first,
               "per_output": per}, open(work / "equiv.json", "w"), indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2],
                  int(sys.argv[3]) if len(sys.argv) > 3 else 4000))
