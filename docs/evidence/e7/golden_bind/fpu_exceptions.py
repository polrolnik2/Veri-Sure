"""Audit-only binding of fpu_exceptions's contract probes to the known-good design.
Read ONLY by docs/evidence/e7_bind_golden.py. Never seen by any pipeline stage or model.

Reference: benchmarks/chipverilog/Des/double_fpu/fpu_exceptions/fpu_exceptions.v

Every one of the 50 contract probes is a 1-bit flag that the reference declares as a
module-level `reg` (L24-L73) of the same name (the reference spells `QNaN`/`SNaN`/`NaN`
with capitals; the probes are lower-cased). ALL of them are REGISTERED: each is
assigned with `<=` inside the single `always @(posedge clk)` block (L87-L213),
cleared by synchronous `rst` (L89-L147) and updated only when `enable` is high
(L148-L212); they hold otherwise. So each probe below reads the reference's
register as it stands on the recorded edge -- no time shift is applied.

Note on pipeline skew (reference behaviour, preserved as-is): the flags form a
chain of dependent registers, so a derived flag reflects the stimulus one or more
enabled edges later than the flags it is built from (e.g. NaN_input (L167) is the
OR of the opa_/opb_ QNaN/SNaN registers as they stood on the previous edge, so it
lags them by one enabled edge; addsub_inf (L181) lags add_inf/sub_inf by one;
out_inf_trigger (L182) mixes exponent_in (current input) with registers of
different depths). Nothing here compensates for that.
"""

#: Reference-design signals the testbench records per clock edge. Exact identifiers as
#: declared in the reference (case-sensitive), module-level regs/wires. Parameters /
#: localparams CANNOT be recorded -- hard-code their values below.
INTERNALS = [
    "in_et_zero",              # L24
    "opa_et_zero",             # L25
    "opb_et_zero",             # L26
    "input_et_zero",           # L27
    "add",                     # L28
    "subtract",                # L29
    "multiply",                # L30
    "divide",                  # L31
    "opa_QNaN",                # L32
    "opb_QNaN",                # L33
    "opa_SNaN",                # L34
    "opb_SNaN",                # L35
    "opa_pos_inf",             # L36
    "opb_pos_inf",             # L37
    "opa_neg_inf",             # L38
    "opb_neg_inf",             # L39
    "opa_inf",                 # L40
    "opb_inf",                 # L41
    "NaN_input",               # L42
    "SNaN_input",              # L43
    "a_NaN",                   # L44
    "div_by_0",                # L45
    "div_0_by_0",              # L46
    "div_inf_by_inf",          # L47
    "div_by_inf",              # L48
    "mul_0_by_inf",            # L49
    "mul_inf",                 # L50
    "div_inf",                 # L51
    "add_inf",                 # L52
    "sub_inf",                 # L53
    "addsub_inf_invalid",      # L54
    "addsub_inf",              # L55
    "out_inf_trigger",         # L56
    "out_pos_inf",             # L57
    "out_neg_inf",             # L58
    "round_nearest",           # L59
    "round_to_zero",           # L60
    "round_to_pos_inf",        # L61
    "round_to_neg_inf",        # L62
    "inf_round_down_trigger",  # L63
    "mul_uf",                  # L64
    "div_uf",                  # L65
    "underflow_trigger",       # L66
    "invalid_trigger",         # L67
    "overflow_trigger",        # L68
    "inexact_trigger",         # L69
    "except_trigger",          # L70
    "enable_trigger",          # L71
    "NaN_out_trigger",         # L72
    "SNaN_trigger",            # L73
    # Wide registers named by later runs' probe sets (L78-L85).
    "NaN_output_0",            # L78  reg [62:0]
    "NaN_output",              # L79  reg [62:0]
    "inf_round_down",          # L81  reg [62:0]
    "out_inf",                 # L82  reg [62:0]
    "out_0", "out_1", "out_2", # L83-L85 reg [63:0]
]


def _reg(name):
    """Read one recorded reference register as-is (None if it was unreadable)."""
    return lambda s: s.get(name)


#: probe name -> function(s) -> int, where s maps each INTERNALS entry to its integer
#: value on that edge (or None if unreadable). Return None if any input is None.
PROBES = {
    # --- operand / result zero decode (registered) -------------------------------
    # L149: in_et_zero <= !(|in_except[62:0]);   -- rounded result magnitude is zero
    "in_et_zero": _reg("in_et_zero"),
    # L150: opa_et_zero <= !(|opa[62:0]);
    "opa_et_zero": _reg("opa_et_zero"),
    # L151: opb_et_zero <= !(|opb[62:0]);
    "opb_et_zero": _reg("opb_et_zero"),
    # L152: input_et_zero <= !(|in_except[62:0]);  -- same equation as in_et_zero (L149);
    # the reference never reads it, but it is its own register.
    "input_et_zero": _reg("input_et_zero"),

    # --- operation decode (registered) ---------------------------------------------
    # L153: add <= fpu_op == 3'b000;
    "add": _reg("add"),
    # L154: subtract <= fpu_op == 3'b001;
    "subtract": _reg("subtract"),
    # L155: multiply <= fpu_op == 3'b010;
    "multiply": _reg("multiply"),
    # L156: divide <= fpu_op == 3'b011;
    "divide": _reg("divide"),

    # --- operand class decode (registered) -----------------------------------------
    # L157: opa_QNaN <= (opa[62:52] == 2047) & |opa[51:0] & opa[51];
    "opa_qnan": _reg("opa_QNaN"),
    # L158: opb_QNaN <= (opb[62:52] == 2047) & |opb[51:0] & opb[51];
    "opb_qnan": _reg("opb_QNaN"),
    # L159: opa_SNaN <= (opa[62:52] == 2047) & |opa[51:0] & !opa[51];
    "opa_snan": _reg("opa_SNaN"),
    # L160: opb_SNaN <= (opb[62:52] == 2047) & |opb[51:0] & !opb[51];
    "opb_snan": _reg("opb_SNaN"),
    # L161: opa_pos_inf <= !opa[63] & (opa[62:52] == 2047) & !(|opa[51:0]);
    "opa_pos_inf": _reg("opa_pos_inf"),
    # L162: opb_pos_inf <= !opb[63] & (opb[62:52] == 2047) & !(|opb[51:0]);
    "opb_pos_inf": _reg("opb_pos_inf"),
    # L163: opa_neg_inf <= opa[63] & (opa[62:52] == 2047) & !(|opa[51:0]);
    "opa_neg_inf": _reg("opa_neg_inf"),
    # L164: opb_neg_inf <= opb[63] & (opb[62:52] == 2047) & !(|opb[51:0]);
    "opb_neg_inf": _reg("opb_neg_inf"),
    # L165: opa_inf <= (opa[62:52] == 2047) & !(|opa[51:0]);
    "opa_inf": _reg("opa_inf"),
    # L166: opb_inf <= (opb[62:52] == 2047) & !(|opb[51:0]);
    "opb_inf": _reg("opb_inf"),

    # --- NaN aggregation (registered, one stage after the operand flags) -----------
    # L167: NaN_input <= opa_QNaN | opb_QNaN | opa_SNaN | opb_SNaN;
    "nan_input": _reg("NaN_input"),
    # L168: SNaN_input <= opa_SNaN | opb_SNaN;
    "snan_input": _reg("SNaN_input"),
    # L169: a_NaN <= opa_QNaN | opa_SNaN;  -- selects opa's payload for the NaN
    # output (consumed at L205: NaN_output_0 <= a_NaN ? {..opa..} : {..opb..}).
    "a_nan": _reg("a_NaN"),

    # --- divide / multiply special cases (registered) ------------------------------
    # L170: div_by_0 <= divide & opb_et_zero & !opa_et_zero;  -- zero divisor, 0/0 excluded
    "div_by_0": _reg("div_by_0"),
    # L171: div_0_by_0 <= divide & opb_et_zero & opa_et_zero;
    "div_0_by_0": _reg("div_0_by_0"),
    # L172: div_inf_by_inf <= divide & opa_inf & opb_inf;
    "div_inf_by_inf": _reg("div_inf_by_inf"),
    # L173: div_by_inf <= divide & !opa_inf & opb_inf;
    "div_by_inf": _reg("div_by_inf"),
    # L174: mul_0_by_inf <= multiply & ((opa_inf & opb_et_zero) | (opa_et_zero & opb_inf));
    "mul_0_by_inf": _reg("mul_0_by_inf"),
    # L175: mul_inf <= multiply & (opa_inf | opb_inf) & !mul_0_by_inf;
    #       (reads the mul_0_by_inf REGISTER, i.e. its previous-edge value)
    "mul_inf": _reg("mul_inf"),
    # L176: div_inf <= divide & opa_inf & !opb_inf;  -- inf / non-inf only
    "div_inf": _reg("div_inf"),

    # --- add / subtract infinity cases (registered) --------------------------------
    # L177: add_inf <= (add & (opa_inf | opb_inf));
    "add_inf": _reg("add_inf"),
    # L178: sub_inf <= (subtract & (opa_inf | opb_inf));
    "sub_inf": _reg("sub_inf"),
    # L179-180: addsub_inf_invalid <= (add & opa_pos_inf & opb_neg_inf) |
    #   (add & opa_neg_inf & opb_pos_inf) | (subtract & opa_pos_inf & opb_pos_inf) |
    #   (subtract & opa_neg_inf & opb_neg_inf);
    "addsub_inf_invalid": _reg("addsub_inf_invalid"),
    # L181: addsub_inf <= (add_inf | sub_inf) & !addsub_inf_invalid;
    "addsub_inf": _reg("addsub_inf"),

    # --- infinity output generation (registered) -----------------------------------
    # L182: out_inf_trigger <= addsub_inf | mul_inf | div_inf | div_by_0 | (exponent_in > 2046);
    "out_inf_trigger": _reg("out_inf_trigger"),
    # L183: out_pos_inf <= out_inf_trigger & !in_except[63];
    "out_pos_inf": _reg("out_pos_inf"),
    # L184: out_neg_inf <= out_inf_trigger & in_except[63];
    "out_neg_inf": _reg("out_neg_inf"),

    # --- rounding-mode decode (registered) -----------------------------------------
    # L185: round_nearest <= (rmode == 2'b00);
    "round_nearest": _reg("round_nearest"),
    # L186: round_to_zero <= (rmode == 2'b01);
    "round_to_zero": _reg("round_to_zero"),
    # L187: round_to_pos_inf <= (rmode == 2'b10);
    "round_to_pos_inf": _reg("round_to_pos_inf"),
    # L188: round_to_neg_inf <= (rmode == 2'b11);
    "round_to_neg_inf": _reg("round_to_neg_inf"),
    # L189-191: inf_round_down_trigger <= (out_pos_inf & round_to_neg_inf) |
    #   (out_neg_inf & round_to_pos_inf) | (out_inf_trigger & round_to_zero);
    "inf_round_down_trigger": _reg("inf_round_down_trigger"),

    # --- underflow (registered) ----------------------------------------------------
    # L192: mul_uf <= multiply & !opa_et_zero & !opb_et_zero & in_et_zero;
    "mul_uf": _reg("mul_uf"),
    # L193: div_uf <= divide & !opa_et_zero & in_et_zero;
    "div_uf": _reg("div_uf"),
    # L194: underflow_trigger <= div_by_inf | mul_uf | div_uf;
    "underflow_trigger": _reg("underflow_trigger"),

    # --- flag triggers (registered; the output flags at L228-L232 are these, one edge later)
    # L195-196: invalid_trigger <= SNaN_input | addsub_inf_invalid | mul_0_by_inf |
    #   div_0_by_0 | div_inf_by_inf;
    "invalid_trigger": _reg("invalid_trigger"),
    # L197: overflow_trigger <= out_inf_trigger & !NaN_input;
    "overflow_trigger": _reg("overflow_trigger"),
    # L198-199: inexact_trigger <= (|mantissa_in[1:0] | out_inf_trigger | underflow_trigger)
    #   & !NaN_input;
    "inexact_trigger": _reg("inexact_trigger"),
    # L200-201: except_trigger <= invalid_trigger | overflow_trigger | underflow_trigger |
    #   inexact_trigger;
    "except_trigger": _reg("except_trigger"),
    # L202: enable_trigger <= except_trigger | out_inf_trigger | NaN_input;
    #   (feeds ex_enable at L227)
    "enable_trigger": _reg("enable_trigger"),
    # L203: NaN_out_trigger <= NaN_input | invalid_trigger;
    #   (selects the NaN result at L211)
    "nan_out_trigger": _reg("NaN_out_trigger"),
    # L204: SNaN_trigger <= invalid_trigger & !SNaN_input;
    #   NB: in the reference this is "invalid operation NOT caused by an SNaN input";
    #   it selects the generated quiet NaN {exp_2047, 2'b01, opa[49:0]} at L206.
    #   It is NOT "an SNaN is present" (that is SNaN_input, L168).
    "snan_trigger": _reg("SNaN_trigger"),

    # --- constants and wide pipeline registers (later runs' probe sets) --------
    # L76-L77, L80: `wire` constants, hard-coded rather than recorded (a constant
    # wire may be optimised out of the simulation).
    "exp_2047": lambda s: 0b11111111111,          # L76  11'b11111111111
    "exp_2046": lambda s: 0b11111111110,          # L77  11'b11111111110
    "mantissa_max": lambda s: (1 << 52) - 1,      # L80  52'b1...1
    # L205: NaN_output_0 <= a_NaN ? {exp_2047,1'b1,opa[50:0]} : {exp_2047,1'b1,opb[50:0]}
    "nan_output_0": _reg("NaN_output_0"),
    # L206: NaN_output <= SNaN_trigger ? {exp_2047,2'b01,opa[49:0]} : NaN_output_0
    "nan_output": _reg("NaN_output"),
    # L207: inf_round_down <= {exp_2046, mantissa_max}
    "inf_round_down": _reg("inf_round_down"),
    # L208: out_inf <= inf_round_down_trigger ? inf_round_down : {exp_2047, 52'b0}
    "out_inf": _reg("out_inf"),
    # L209-L211: the three output pipeline copies; `out <= out_2` at L233.
    "out_0": _reg("out_0"),
    "out_1": _reg("out_1"),
    "out_2": _reg("out_2"),
}

#: probe name -> one-sentence reason it has NO counterpart in the reference.
UNBOUND = {}
