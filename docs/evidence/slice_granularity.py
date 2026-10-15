"""The slice is real, and it cannot narrow: one block is two thirds of the design.

`focus(req_uid)` calls `dynamic_slice`, a genuine backward walk from the failing
signals through the driver map. §6.2(b) argued that slicing from ONE
requirement's ports is what "keeps the slice a slice" once many requirements
fail. On this design that argument does not survive contact, and the reason is
not the algorithm.

MEASURED on the ChipVerilog i2c candidate and on the golden design:

    candidate t1   15 blocks,  7285 chars   largest block 4713 (65%)
    golden         15 blocks, 10542 chars   largest block 7159 (68%)

Both are one bit-controller FSM plus fourteen small helpers. The FSM writes
cmd_ack, scl_oen, sda_chk, sda_oen and state, so a backward slice from ANY of
those pulls it in at depth 1 -- and from its reads, nearly everything else
within two more hops:

    slice from                     d=1   d=2   d=3   chars at d=3
    REQ-0090 ports_read (all)        2     9    12       99% of the design
      ... its output alone           1     3     7       75%
    REQ-0114 ports_read              2     4     8       75%
    REQ-0003 ports_read              1     3     7       75%

Even the tightest case -- one output, depth 1, a single block -- is 65% of the
design's text, because that single block IS 65% of the design.

WHY THIS MATTERS MORE THAN THE SLICE WIDTH. The unit of EDIT is the block. To
change one state's `scl_oen` assignment the agent must call
`replace_block("A4")` and retype all 4713 characters, and any transcription slip
anywhere in them breaks the commit. Across four live sessions the agent
repeatedly staged a full-FSM replacement, failed a check, discarded, and staged
another -- and while a splice bug was welding its last token to `endmodule`, the
edit surface would have been wrong even without it.

So `add_block` and `remove_block` do not close the gap the plan thought they
did: §7.1 added them because "a repair needing new declarations, or one whose
fix is removal, is unreachable". The unreachable repair on this design is the
SMALL one -- change a single assignment inside a large sequential block -- and
nothing in the editor expresses it. Statement- or case-arm granularity, or a
patch-shaped edit against a block's interior, is the missing capability.

Reproduce: this file, against any run directory `loop_run.py` built.
"""

import sys
from pathlib import Path

sys.path.insert(0, "/home/user/Veri-Sure")

from eda_agent.trace_slicer import (build_driver_map,  # noqa: E402
                                    dynamic_slice, parse_rtl_blocks)

DESIGNS = {
    "candidate t1": Path("/tmp/claude-0/-home-user-Veri-Sure"
                         "/12bb865e-7a51-5506-b55a-e5ac7cf72a4a/scratchpad/asrt"
                         "/run5/rtl.sv"),
    "golden": Path("/home/user/Veri-Sure/benchmarks/chipverilog/Des/i2c"
                   "/i2c_master_bit_ctrl/i2c_master_bit_ctrl.v"),
}
SLICES = {
    "REQ-0090 ports_read": ["scl_oen", "al", "cmd", "ena", "nReset", "rst",
                            "clk_cnt"],
    "  its output alone": ["scl_oen"],
    "REQ-0114 ports_read": ["sda_oen", "sda_o", "cmd", "ena"],
    "REQ-0003 ports_read": ["scl_oen", "sda_oen", "cmd_ack", "cmd", "din",
                            "ena"],
}


def main() -> int:
    for name, path in DESIGNS.items():
        if not path.exists():
            print(f"{name}: {path} not present, skipped")
            continue
        blocks = sorted(parse_rtl_blocks(path.read_text()),
                        key=lambda b: -len(b.code))
        total = sum(len(b.code) for b in blocks)
        big = blocks[0]
        print(f"{name:<14}{len(blocks):>3} blocks, {total:>6} chars   "
              f"largest {len(big.code)} ({100 * len(big.code) / total:.0f}%) "
              f"writes {list(big.writes)[:5]}")

    path = DESIGNS["candidate t1"]
    if not path.exists():
        return 0
    blocks = parse_rtl_blocks(path.read_text())
    total = sum(len(b.code) for b in blocks)
    drivers = build_driver_map(blocks)
    print(f"\n{'slice from':<24}{'d=1':>5}{'d=2':>5}{'d=3':>5}{'chars at d=3':>14}")
    for label, ports in SLICES.items():
        counts = [len(dynamic_slice(fail_signals=ports, drivers=drivers,
                                    max_depth=d)) for d in (1, 2, 3)]
        chars = sum(len(b.code) for b in dynamic_slice(
            fail_signals=ports, drivers=drivers, max_depth=3))
        print(f"{label:<24}{counts[0]:>5}{counts[1]:>5}{counts[2]:>5}"
              f"{100 * chars / total:>13.0f}%")
    return 0


if __name__ == "__main__":
    sys.exit(main())
