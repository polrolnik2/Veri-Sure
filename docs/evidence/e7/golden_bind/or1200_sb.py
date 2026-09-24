"""Audit-only binding of or1200_sb's contract probes to the known-good design.
Read ONLY by docs/evidence/e7_bind_golden.py. Never seen by any pipeline stage or model.

Reference: benchmarks/chipverilog/Des/or1200/or1200_sb/or1200_sb.v, compiled with
benchmarks/chipverilog/Des/or1200/or1200_defines.v as shipped.

THE STORE BUFFER IS NOT COMPILED IN. Every one of this contract's probes names something
declared only inside `ifdef OR1200_SB_IMPLEMENTED (or1200_sb.v:55-125), and
or1200_defines.v:1396 has that define commented out ("//`define OR1200_SB_IMPLEMENTED").
Nothing in the replay (e6_replay_corpus.py / specflow.run) adds a +define, so the design that
is actually simulated is the `else branch (or1200_sb.v:126-137): a pure combinational
pass-through DC<->BIU with no FIFO, no or1200_sb_fifo instance, no sel_sb, no
outstanding_store and no fifo_wr_ack. (Even with the define on, or1200_sb_fifo is not in
benchmarks/chipverilog/Des and would have to be supplied with --extra.)

The contract records the OPPOSITE build hypothesis for all nine probes -- config_gated
{"key": "OR1200_SB_IMPLEMENTED", "value": true} -- so this reference is not the configuration
the contract describes. Every probe is therefore UNBOUND, and nothing is recorded.
"""
#: Reference-design signals the testbench records per clock edge. Exact identifiers as
#: declared in the reference (case-sensitive), module-level regs/wires of the top module;
#: use a dotted path "inst.sig" only for a signal inside a child instance. Parameters /
#: `define constants CANNOT be recorded -- hard-code their values below.
INTERNALS = []

#: probe name -> function(s) -> int, where s maps each INTERNALS entry to its integer
#: value on that edge (or None if unreadable). Return None if any input is None.
PROBES = {}

_GATE = ("exists only under `ifdef OR1200_SB_IMPLEMENTED (or1200_sb.v:55-125), which "
         "or1200_defines.v:1396 leaves commented out, so the compiled reference is the "
         "pass-through at or1200_sb.v:126-137 and has no such signal")

#: probe name -> one-sentence reason it has NO counterpart in the reference.
UNBOUND = {
    # Would-be binding if enabled: wire [67:0] fifo_dat_i (:60), = {dcsb_sel_i, dcsb_dat_i, dcsb_adr_i} (:73).
    "fifo_dat_i": f"wire [4+dw+aw-1:0] fifo_dat_i (or1200_sb.v:60) {_GATE}.",
    # Would-be binding if enabled: wire [67:0] fifo_dat_o (:61), driven by or1200_sb_fifo.dat_o (:99).
    "fifo_dat_o": f"wire [4+dw+aw-1:0] fifo_dat_o (or1200_sb.v:61) {_GATE}.",
    # Would-be binding if enabled: wire fifo_wr (:62), assigned :79.
    "fifo_wr": f"wire fifo_wr (or1200_sb.v:62, assigned :79) {_GATE}.",
    # Would-be binding if enabled: wire fifo_rd (:63), = ~outstanding_store (:80).
    "fifo_rd": f"wire fifo_rd (or1200_sb.v:63, assigned :80) {_GATE}.",
    # Would-be binding if enabled: wire fifo_full (:64), driven by or1200_sb_fifo.full_o (:100).
    "fifo_full": f"wire fifo_full (or1200_sb.v:64) {_GATE}.",
    # Would-be binding if enabled: wire fifo_empty (:65), driven by or1200_sb_fifo.empty_o (:101).
    "fifo_empty": f"wire fifo_empty (or1200_sb.v:65) {_GATE}.",
    # Would-be binding if enabled: wire sel_sb (:66), assigned :88.
    "sel_sb": f"wire sel_sb (or1200_sb.v:66, assigned :88) {_GATE}.",
    # Would-be binding if enabled: reg outstanding_store (:67), always block :107-113.
    "outstanding_store": f"reg outstanding_store (or1200_sb.v:67, updated :107-113) {_GATE}.",
    # Would-be binding if enabled: reg fifo_wr_ack (:68), always block :118-124.
    "fifo_wr_ack": f"reg fifo_wr_ack (or1200_sb.v:68, updated :118-124) {_GATE}.",
}
