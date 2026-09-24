"""Audit-only binding of i2c_master_bit_ctrl's contract probes to the known-good design.
Read ONLY by docs/evidence/e7_bind_golden.py. Never seen by any pipeline stage or model."""
#
# Reference: benchmarks/chipverilog/Des/i2c/i2c_master_bit_ctrl/i2c_master_bit_ctrl.v
# (line numbers below cite that file). Every binding reads the reference's own
# signal AS IT HAS IT on the sampled edge -- registered where the reference
# registers it -- with no time shift to line it up with the spec's wording.

#: Reference-design signals the testbench records per clock edge. Exact identifiers as
#: declared in the reference (case-sensitive), module-level regs/wires of the top module;
#: use a dotted path "inst.sig" only for a signal inside a child instance. Parameters /
#: localparams / `define constants CANNOT be recorded -- hard-code their values below.
INTERNALS = [
    "c_state",        # reg [17:0], L185 -- the command FSM state register
    "cSCL", "cSDA",   # reg [1:0],  L172 -- two-stage input capture
    "fSCL", "fSDA",   # reg [2:0],  L173 -- three-sample filter histories
    "sSCL", "sSDA",   # reg,        L174 -- filtered (majority) bus lines
    "dSCL", "dSDA",   # reg,        L175 -- one-clk-delayed sSCL / sSDA
    "sta_condition",  # reg,        L308 -- registered START detect
    "sto_condition",  # reg,        L309 -- registered STOP detect
    "clk_en",         # reg,        L178 -- registered timing tick
    "cnt",            # reg [15:0], L180 -- bit-timing counter
    "filter_cnt",     # reg [13:0], L181 -- input-filter sampling counter
    "slave_wait",     # reg,        L179 -- clock-stretch wait flag
    "scl_sync",       # wire,       L204 -- multi-master clock-sync detect
    "sda_chk",        # reg,        L177 -- SDA arbitration-check enable
]

# ---------------------------------------------------------------------------
# c_state encoding, hard-coded from the `parameter [17:0]` list at L365-L382.
# ONE-HOT with idle = all-zero. Each literal is 17 binary digits zero-extended
# to 18 bits, so bit 17 is never used; wr_d (L382) is bit 16.
# ---------------------------------------------------------------------------
IDLE = 0x00000                                        # L365 idle
START_A, START_B, START_C, START_D, START_E = (
    1 << 0, 1 << 1, 1 << 2, 1 << 3, 1 << 4)           # L366-L370
STOP_A, STOP_B, STOP_C, STOP_D = (
    1 << 5, 1 << 6, 1 << 7, 1 << 8)                   # L371-L374
RD_A, RD_B, RD_C, RD_D = (
    1 << 9, 1 << 10, 1 << 11, 1 << 12)                # L375-L378
WR_A, WR_B, WR_C, WR_D = (
    1 << 13, 1 << 14, 1 << 15, 1 << 16)               # L379-L382

START_STATES = frozenset({START_A, START_B, START_C, START_D, START_E})
STOP_STATES = frozenset({STOP_A, STOP_B, STOP_C, STOP_D})
READ_STATES = frozenset({RD_A, RD_B, RD_C, RD_D})
WRITE_STATES = frozenset({WR_A, WR_B, WR_C, WR_D})


def _bind(fn, *names):
    """Apply `fn` to the recorded values of `names`; None if any is unreadable."""
    def probe(s):
        vals = [s.get(n) for n in names]
        if any(v is None for v in vals):
            return None
        return int(fn(*(int(v) for v in vals)))
    return probe


#: probe name -> function(s) -> int, where s maps each INTERNALS entry to its integer
#: value on that edge (or None if unreadable). Return None if any input is None.
PROBES = {
    # c_state == idle. Reset to idle at L387/L395; returns to idle from
    # start_e/stop_d/rd_d/wr_d at L458/L492/L526/L561; decodes cmd in idle L408-L416.
    "idle": _bind(lambda c: c == IDLE, "c_state"),

    # Any non-idle state. The reference itself uses `|c_state` for exactly
    # "FSM active in a command" in the unexpected-STOP arbitration term, L354.
    "fsm_active": _bind(lambda c: c != IDLE, "c_state"),

    # START sequence = {start_a, start_b, start_c, start_d, start_e}: the five
    # states entered from idle on I2C_CMD_START (L411) and walked L424-L463
    # until start_e returns to idle with cmd_ack (L458-L459).
    "in_start_sequence": _bind(lambda c: c in START_STATES, "c_state"),

    # STOP sequence = {stop_a, stop_b, stop_c, stop_d}: entered on I2C_CMD_STOP
    # (L412), walked L466-L497, stop_d returns to idle with cmd_ack (L492-L493).
    "in_stop_sequence": _bind(lambda c: c in STOP_STATES, "c_state"),

    # READ sequence = {rd_a, rd_b, rd_c, rd_d}: entered on I2C_CMD_READ (L414),
    # walked L500-L531, rd_d returns to idle with cmd_ack (L526-L527).
    "in_read_sequence": _bind(lambda c: c in READ_STATES, "c_state"),

    # WRITE sequence = {wr_a, wr_b, wr_c, wr_d}: entered on I2C_CMD_WRITE (L413),
    # walked L534-L566, wr_d returns to idle with cmd_ack (L561-L562).
    "in_write_sequence": _bind(lambda c: c in WRITE_STATES, "c_state"),

    # Stable high phase of a WRITE bit = {wr_d}. The wr_b arm releases SCL
    # (scl_oen<=1, L545) and says "allow some time for SDA and SCL to settle"
    # (L547-L548), so the register holds wr_c while SCL settles; the wr_c arm
    # enables checking (sda_chk<=1, L556), so the register holds wr_d with SCL
    # still released and sda_chk=1; the wr_d arm pulls SCL low and clears
    # sda_chk (L563-L565). wr_d is therefore the one state whose period is the
    # settled SCL-high window with arbitration checking on.
    "in_write_stable_high_phase": _bind(lambda c: c == WR_D, "c_state"),

    # cSCL is reg [1:0] (L172) shifted {cSCL[0], scl_i} (L248); the value the
    # two-stage synchronizer delivers downstream is its second stage cSCL[1]
    # (the bit fed into fSCL at L274).
    "cscl": _bind(lambda c: (c >> 1) & 1, "cSCL"),

    # Same for SDA: second stage cSDA[1] (L172, L249, fed to fSDA at L275).
    "csda": _bind(lambda c: (c >> 1) & 1, "cSDA"),

    # 3-bit history reg [2:0] fSCL (L173), shifted at L274; returned whole.
    "fscl": _bind(lambda f: f & 0b111, "fSCL"),

    # 3-bit history reg [2:0] fSDA (L173), shifted at L275; returned whole.
    "fsda": _bind(lambda f: f & 0b111, "fSDA"),

    # Filtered SCL: registered majority of fSCL (L174, L299).
    "sscl": _bind(lambda v: v & 1, "sSCL"),

    # Filtered SDA: registered majority of fSDA (L174, L300).
    "ssda": _bind(lambda v: v & 1, "sSDA"),

    # Delayed filtered SCL: dSCL <= sSCL (L175, L302).
    "dscl": _bind(lambda v: v & 1, "dSCL"),

    # Delayed filtered SDA: dSDA <= sSDA (L175, L303).
    "dsda": _bind(lambda v: v & 1, "dSDA"),

    # START detect. REGISTERED in the reference: sta_condition <= ~sSDA & dSDA
    # & sSCL (L308, L323), i.e. one clk after the combinational expression.
    "sta_condition": _bind(lambda v: v & 1, "sta_condition"),

    # STOP detect. REGISTERED in the reference: sto_condition <= sSDA & ~dSDA
    # & sSCL (L309, L324), i.e. one clk after the combinational expression.
    "sto_condition": _bind(lambda v: v & 1, "sto_condition"),

    # Rising edge of filtered SCL: the reference's own `sSCL & ~dSCL`, the
    # condition that captures dout (L359). Combinational over registers.
    "sscl_rising": _bind(lambda s_, d_: (s_ & 1) & (~d_ & 1), "sSCL", "dSCL"),

    # Timing tick: reg clk_en (L178), set 1 on reload / cleared otherwise
    # (L208-L228). Registered: high the clk AFTER cnt was zero.
    "clk_en": _bind(lambda v: v & 1, "clk_en"),

    # Counter reached zero: the reference's own `~|cnt` reload condition (L214).
    "cnt_zero": _bind(lambda c: c == 0, "cnt"),

    # Filter counter expired: the reference's own `~|filter_cnt`, which reloads
    # it (L257) and shifts fSCL/fSDA (L272).
    "filter_cnt_expired": _bind(lambda c: c == 0, "filter_cnt"),

    # Clock-stretch wait: reg slave_wait (L179), L198-L200.
    "slave_wait": _bind(lambda v: v & 1, "slave_wait"),

    # Multi-master clock sync: wire scl_sync = dSCL & ~sSCL & scl_oen (L204).
    "scl_sync": _bind(lambda v: v & 1, "scl_sync"),

    # SDA arbitration-check enable: reg sda_chk (L177), driven by the FSM
    # (1 only from the wr_c arm, L556; cleared L391/L399 and in every other arm).
    "sda_chk": _bind(lambda v: v & 1, "sda_chk"),
}

#: probe name -> one-sentence reason it has NO counterpart in the reference.
UNBOUND = {}
