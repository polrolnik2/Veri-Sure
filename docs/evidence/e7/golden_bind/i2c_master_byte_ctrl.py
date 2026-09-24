"""Audit-only binding of i2c_master_byte_ctrl's contract probes to the known-good design.
Read ONLY by docs/evidence/e7_bind_golden.py. Never seen by any pipeline stage or model."""
#: Reference-design signals the testbench records per clock edge. Exact identifiers as
#: declared in the reference (case-sensitive), module-level regs/wires of the top module;
#: use a dotted path "inst.sig" only for a signal inside a child instance. Parameters /
#: localparams / `define constants CANNOT be recorded -- hard-code their values below.
INTERNALS = [
    "c_state",   # reg [4:0], i2c_master_byte_ctrl.v:199
    "core_cmd",  # reg [3:0], :128
    "go",        # wire, :137 / :167
    "ld",        # reg, :134
    "shift",     # reg, :134
    "cnt_done",  # wire, :139 / :194
    "dcnt",      # reg [2:0], :138
    "core_ack",  # wire, :130 (bit_controller.cmd_ack, :153)
    "core_rxd",  # wire, :130 (bit_controller.dout, :157)
    "core_txd",  # reg, :129
]

# FSM encoding, i2c_master_byte_ctrl.v:120-125 (IDLE is all-zero, the rest one-hot).
ST_IDLE = 0b0_0000
ST_START = 0b0_0001
ST_READ = 0b0_0010
ST_WRITE = 0b0_0100
ST_ACK = 0b0_1000
ST_STOP = 0b1_0000

# Bit-controller commands, i2c_master_defines.v:55-59.
I2C_CMD_NOP = 0b0000
I2C_CMD_START = 0b0001
I2C_CMD_STOP = 0b0010
I2C_CMD_WRITE = 0b0100
I2C_CMD_READ = 0b1000


def _eq(sig, const):
    """1 when recorded `sig` equals `const`, None when it could not be read."""
    return lambda s: None if s.get(sig) is None else int(s[sig] == const)


def _bit(sig):
    """The recorded 1-bit signal itself, None when it could not be read."""
    return lambda s: None if s.get(sig) is None else int(s[sig]) & 1


#: probe name -> function(s) -> int, where s maps each INTERNALS entry to its integer
#: value on that edge (or None if unreadable). Return None if any input is None.
PROBES = {
    # State predicates: c_state == ST_* (reg c_state, :199; updated :209/:219/:236-:335).
    "st_idle": _eq("c_state", ST_IDLE),    # ST_IDLE  = 5'b0_0000, :120
    "st_start": _eq("c_state", ST_START),  # ST_START = 5'b0_0001, :121
    "st_read": _eq("c_state", ST_READ),    # ST_READ  = 5'b0_0010, :122
    "st_write": _eq("c_state", ST_WRITE),  # ST_WRITE = 5'b0_0100, :123
    "st_ack": _eq("c_state", ST_ACK),      # ST_ACK   = 5'b0_1000, :124
    "st_stop": _eq("c_state", ST_STOP),    # ST_STOP  = 5'b1_0000, :125
    # Launch condition: assign go = (read | write | stop) & ~cmd_ack;  (:167, combinational)
    "go": _bit("go"),
    # Load control: registered, pulsed with each command accept (:207/:217/:227/:255/:272)
    "ld": _bit("ld"),
    # Shift control: registered, pulsed after each completed data bit (:206/:216/:226/:286/:303)
    "shift": _bit("shift"),
    # Terminal count: assign cnt_done = ~(|dcnt);  (:194, combinational)
    "cnt_done": _bit("cnt_done"),
    # Bit counter at 7: dcnt == 3'h7 (reg dcnt :138, loaded with 3'h7 on ld at :189-:190)
    "dcnt_is_7": _eq("dcnt", 7),
    # Bit-controller completion ack: wire core_ack <- bit_controller.cmd_ack (:130, :153)
    "core_ack": _bit("core_ack"),
    # Sampled bit from bit controller: wire core_rxd <- bit_controller.dout (:130, :157)
    "core_rxd": _bit("core_rxd"),
    # Transmit bit to bit controller: reg core_txd (:129; <= sr[7] default :225, ack_in :304/:330, 1 :327)
    "core_txd": _bit("core_txd"),
    # Command selection: reg core_cmd (:128; assigned :204-:336) vs `I2C_CMD_* (defines :55-:59)
    "core_cmd_start": _eq("core_cmd", I2C_CMD_START),  # 4'b0001
    "core_cmd_read": _eq("core_cmd", I2C_CMD_READ),    # 4'b1000
    "core_cmd_write": _eq("core_cmd", I2C_CMD_WRITE),  # 4'b0100
    "core_cmd_stop": _eq("core_cmd", I2C_CMD_STOP),    # 4'b0010
    "core_cmd_nop": _eq("core_cmd", I2C_CMD_NOP),      # 4'b0000
}

#: probe name -> one-sentence reason it has NO counterpart in the reference.
UNBOUND = {}
