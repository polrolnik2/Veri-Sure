"""Audit-only binding of or1200_dc_fsm's contract probes to the known-good design.
Read ONLY by docs/evidence/e7_bind_golden.py. Never seen by any pipeline stage or model.

Reference: benchmarks/chipverilog/Des/or1200/or1200_dc_fsm/or1200_dc_fsm.v, compiled with
benchmarks/chipverilog/Des/or1200/or1200_defines.v as shipped. Relevant build facts:
  * The DCFSM state encodings are `define'd in or1200_dc_fsm.v ITSELF (lines 5-9), not in
    or1200_defines.v:  IDLE=3'd0, CLOAD=3'd1, LREFILL3=3'd2, CSTORE=3'd3, SREFILL4=3'd4.
  * or1200_defines.v:1342  `define OR1200_DCLS 4   (so cnt is loaded with 2 on CLOAD->LREFILL3)
  * or1200_defines.v:1345  // `define OR1200_DC_STORE_REFILL   -- COMMENTED OUT, so every
    SREFILL4 construct in the reference (lines 94-96, 189-198, 208-219) is compiled away.
"""
#: Reference-design signals the testbench records per clock edge. Exact identifiers as
#: declared in the reference (case-sensitive), module-level regs/wires of the top module;
#: use a dotted path "inst.sig" only for a signal inside a child instance. Parameters /
#: `define constants CANNOT be recorded -- hard-code their values below.
INTERNALS = [
    "state",                # or1200_dc_fsm.v:55  reg [2:0] state;
    "cnt",                  # or1200_dc_fsm.v:56  reg [2:0] cnt;
    "hitmiss_eval",         # or1200_dc_fsm.v:57  reg hitmiss_eval;
    "store",                # or1200_dc_fsm.v:58  reg store;
    "load",                 # or1200_dc_fsm.v:59  reg load;
    "cache_inhibit",        # or1200_dc_fsm.v:60  reg cache_inhibit;
    "first_store_hit_ack",  # or1200_dc_fsm.v:61  wire first_store_hit_ack; (assigned :85)
]

# `define constants from or1200_dc_fsm.v lines 5-9 (cannot be recorded; hard-coded).
_IDLE = 0       # or1200_dc_fsm.v:5  `define OR1200_DCFSM_IDLE     3'd0
_CLOAD = 1      # or1200_dc_fsm.v:6  `define OR1200_DCFSM_CLOAD    3'd1
_LREFILL3 = 2   # or1200_dc_fsm.v:7  `define OR1200_DCFSM_LREFILL3 3'd2
_CSTORE = 3     # or1200_dc_fsm.v:8  `define OR1200_DCFSM_CSTORE   3'd3


def _state_is(value):
    return lambda s: None if s.get("state") is None else int(s["state"] == value)


def _bit(name):
    return lambda s: None if s.get(name) is None else int(s[name]) & 1


#: probe name -> function(s) -> int, where s maps each INTERNALS entry to its integer
#: value on that edge (or None if unreadable). Return None if any input is None.
PROBES = {
    # state == `OR1200_DCFSM_IDLE (3'd0); the reference's own compare form is used at
    # :84-87 for CLOAD/CSTORE; IDLE is the case arm at :114 and the reset value at :104.
    "idle": _state_is(_IDLE),
    # state == `OR1200_DCFSM_CLOAD (3'd1); reference uses (state == `OR1200_DCFSM_CLOAD)
    # at :84, :86, :87, :92; case arm :137.
    "cload": _state_is(_CLOAD),
    # state == `OR1200_DCFSM_CSTORE (3'd3); reference uses (state == `OR1200_DCFSM_CSTORE)
    # at :85, :86, :87; case arm :176.
    "cstore": _state_is(_CSTORE),
    # state == `OR1200_DCFSM_LREFILL3 (3'd2); reference uses (state == `OR1200_DCFSM_LREFILL3)
    # at :93 (burst); case arm :166.
    "lrefill3": _state_is(_LREFILL3),
    # reg hitmiss_eval (:57); set :118/:126, cleared :106/:132/:146/:153/:159/:164/:185/:202/:206.
    "hitmiss_eval": _bit("hitmiss_eval"),
    # reg store (:58); set :119, cleared :107/:127/:133/:186/:203; drives biu_write at :73.
    "store": _bit("store"),
    # reg load (:59); set :128, cleared :108/:120/:134/:147/:160/:173.
    "load": _bit("load"),
    # reg cache_inhibit (:60); set :139/:178 on dcqmem_cycstb_i & dcqmem_ci_i, cleared on
    # entry (:121/:129) and on exit.
    "cache_inhibit": _bit("cache_inhibit"),
    # reg [2:0] cnt (:56) nonzero -- the reference's own test is |cnt at :167
    # ("biudata_valid && (|cnt)"); loaded with `OR1200_DCLS-2 = 2 at :154, decremented :168.
    "cnt_nonzero": lambda s: None if s.get("cnt") is None else int(s["cnt"] != 0),
    # wire first_store_hit_ack (:61), combinational:
    #   (state == CSTORE) & !tagcomp_miss & biudata_valid & !cache_inhibit & !dcqmem_ci_i  (:85)
    "first_store_hit_ack": _bit("first_store_hit_ack"),
}

#: probe name -> one-sentence reason it has NO counterpart in the reference.
UNBOUND = {
    # If the caller prefers "an absent state reads 0" over abstaining, the binding would be
    # _state_is(4) (`OR1200_DCFSM_SREFILL4 3'd4, :9): provably constant 0 on this build, since
    # no compiled arm assigns 4 and the default arm (:220-221) returns to IDLE.
    "srefill4": (
        "SREFILL4 exists only under `ifdef OR1200_DC_STORE_REFILL (or1200_dc_fsm.v:94-96, "
        ":189-198, :208-219), which or1200_defines.v:1345 leaves commented out, so the "
        "compiled reference has no SREFILL4 state (the contract itself marks this probe "
        "config_gated on OR1200_DC_STORE_REFILL=false)."
    ),
}
