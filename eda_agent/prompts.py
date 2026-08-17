RTL_4_SHOT_EXAMPLES = """
Here are some examples of RTL SystemVerilog code:
Example 1:
<example>
    <input_spec>
        Implement the SystemVerilog module based on the following description.
        Assume that sigals are positive clock/clk triggered unless otherwise stated.

        The module should implement a XOR gate.
    </input_spec>
    <module>
        module TopModule(
            input  logic in0,
            input  logic in1,
            output logic out
        );

            assign out = in0 ^ in1;

        endmodule
    </module>
</example>
Example 2:
<example>
    <input_spec>
        Implement the SystemVerilog module based on the following description.
        Assume that sigals are positive clock/clk triggered unless otherwise stated.

        The module should implement an 8-bit registered incrementer.
        The 8-bit input is first registered and then incremented by one on the next cycle.
        The reset input is active high synchronous and should reset the output to zero.
    </input_spec>
    <module>
        module TopModule(
            input  logic       clk,
            input  logic       reset,
            input  logic [7:0] in_,
            output logic [7:0] out
        );

            // Sequential logic
            logic [7:0] reg_out;
            always @( posedge clk ) begin
                if ( reset )
                reg_out <= 0;
                else
                reg_out <= in_;
            end

            // Combinational logic
            logic [7:0] temp_wire;
            always @(*) begin
                temp_wire = reg_out + 1;
            end

            // Structural connections
            assign out = temp_wire;

        endmodule
    </module>
</example>
Example 3:
<example>
    <input_spec>
        Implement the SystemVerilog module based on the following description.
        Assume that sigals are positive clock/clk triggered unless otherwise stated.

        The module should implement an n-bit registered incrementer where the bitwidth is specified by the parameter nbits.
        The n-bit input is first registered and then incremented by one on the next cycle.
        The reset input is active high synchronous and should reset the output to zero.
    </input_spec>
    <module>
        module TopModule #(
            parameter nbits
        )(
            input  logic             clk,
            input  logic             reset,
            input  logic [nbits-1:0] in_,
            output logic [nbits-1:0] out
        );

            // Sequential logic
            logic [nbits-1:0] reg_out;
            always @( posedge clk ) begin
                if ( reset )
                reg_out <= 0;
                else
                reg_out <= in_;
            end

            // Combinational logic
            logic [nbits-1:0] temp_wire;
            always @(*) begin
                temp_wire = reg_out + 1;
            end

            // Structural connections
            assign out = temp_wire;

        endmodule
    </module>
</example>
Example 4:
<example>
    <input_spec>
        Implement the SystemVerilog module based on the following description.
        Assume that sigals are positive clock/clk triggered unless otherwise stated.

        Build a finite-state machine that takes as input a serial bit stream,
            and outputs a one whenever the bit stream contains two consecutive one's.
        The output is one on the cycle _after_ there are two consecutive one's.
        The reset input is active high synchronous,
            and should reset the finite-state machine to an appropriate initial state.
    </input_spec>
    <module>
        module TopModule(
            input  logic clk,
            input  logic reset,
            input  logic in_,
            output logic out
        );

            // One-cycle delayed "11" detector:
            // out is asserted on the cycle AFTER two consecutive ones occur.
            logic prev_in;
            logic det_11;

            always @(posedge clk) begin
                if (reset) begin
                    prev_in <= 1'b0;
                    det_11 <= 1'b0;
                    out <= 1'b0;
                end else begin
                    out <= det_11;
                    det_11 <= prev_in & in_;
                    prev_in <= in_;
                end
            end

        endmodule
    </module>
</example>
"""


FAILED_TRIAL_PROMPT = r"""
There was a generation trial that failed simulation:
<failed_sim_log>
{failed_sim_log}
</failed_sim_log>
<previous_code>
{previous_code}
</previous_code>
<previous_tb>
{previous_tb}
</previous_tb>
"""

ORDER_PROMPT = r"""
Your response will be processed by a program, not human.
So, please STRICTLY FOLLOW the output format given as XML tag content below to generate a VALID JSON OBJECT:
<output_format>
{output_format}
</output_format>
DO NOT include any other information in your response, like 'json', 'reasoning' or '<output_format>'.
"""

TAG_ORDER_PROMPT = r"""
Your response will be processed by a program, not human.
So, please STRICTLY FOLLOW the output format given as XML tag content below:
<output_format>
{output_format}
</output_format>

Rules:
- Output ONLY the tags shown in output_format (once each) and nothing else.
- Do NOT output JSON.
- Do NOT wrap code in Markdown code fences (```).
"""


# ---------------------------------------------------------------------------
# GLUE (composition-node) few-shot examples.
#
# RTL_4_SHOT_EXAMPLES demonstrates four monolithic `TopModule` leaves. Measured
# on a real composition prompt (booth/fp_adder, 2026-07-26): the assembled glue
# coder prompt was 85,795 chars with FOUR leaf exemplars and ELEVEN total
# mentions of glue guidance. Instructions said "you are a COMPOSITION NODE, do
# not reimplement the children"; every worked example showed a self-contained
# module implementing a spec end-to-end. Demonstrations win, and the observed
# failure was exactly that: VESTIGIAL GLUE -- the module declares child-output
# ports and never reads them, having recomputed the children's function inline.
#
# These exemplars demonstrate the opposite discipline: EVERY child output port
# is consumed, and no child's function is recomputed.
# ---------------------------------------------------------------------------
GLUE_4_SHOT_EXAMPLES = r"""
Here are worked examples of GLUE (composition) modules. Study what they do NOT
do: they never recompute a child's function, and every child-facing OUTPUT port
appears on the right-hand side of an assignment.

<example_1>
Contract: parent `acc_unit` composes child `adder` (child_assumes: adder).
Child-facing ports: adder_a, adder_b (parent->child), adder_sum (child->parent).
External: clk, rst, in_val, out_acc.

<answer>
module acc_unit (
  input  logic        clk,
  input  logic        rst,
  input  logic [7:0]  in_val,
  output logic [15:0] out_acc,
  // child-facing
  output logic [7:0]  adder_a,
  output logic [7:0]  adder_b,
  input  logic [15:0] adder_sum
);
  logic [15:0] acc_q;
  // Drive the child's inputs.
  assign adder_a = in_val;
  assign adder_b = acc_q[7:0];
  // CONSUME the child's output. The sum is NOT recomputed here.
  always_ff @(posedge clk) begin
    if (rst) acc_q <= '0;
    else     acc_q <= adder_sum;
  end
  assign out_acc = acc_q;
endmodule
</answer>
Note: `out_acc` is derived from `adder_sum`. Writing `acc_q <= acc_q + in_val`
would be VESTIGIAL GLUE -- correct-looking, but the child is unused.
</example_1>

<example_2>
Contract: parent `ctrl_dp` composes children `ctrl` and `dp`.
Child-facing: ctrl_start, ctrl_done (child->parent), dp_en, dp_result (child->parent).
External: clk, rst, start, done, result.

<answer>
module ctrl_dp (
  input  logic        clk,
  input  logic        rst,
  input  logic        start,
  output logic        done,
  output logic [15:0] result,
  // child-facing
  output logic        ctrl_start,
  input  logic        ctrl_done,
  output logic        dp_en,
  input  logic [15:0] dp_result
);
  // Route external control INTO the controller child.
  assign ctrl_start = start;
  // Sibling wiring: one child's output drives another child's input.
  assign dp_en      = ctrl_done ? 1'b0 : ctrl_start;
  // CONSUME both children's outputs on the external interface.
  assign done       = ctrl_done;
  assign result     = dp_result;
endmodule
</answer>
Note: every child-facing INPUT (ctrl_done, dp_result) is read. A glue module
that implemented its own FSM and its own datapath would leave them dangling.
</example_2>

<example_3>
Contract: parent `gated_out` composes child `core`, and must suppress the
child's output for one cycle after reset (a guarantee the child does not make).
Child-facing: core_valid, core_data (child->parent).

<answer>
module gated_out (
  input  logic        clk,
  input  logic        rst,
  output logic        valid,
  output logic [7:0]  data,
  // child-facing
  input  logic        core_valid,
  input  logic [7:0]  core_data
);
  logic started_q;
  always_ff @(posedge clk) begin
    if (rst) started_q <= 1'b0;
    else     started_q <= 1'b1;
  end
  // Glue adds ONLY the missing guarantee (post-reset suppression) and
  // otherwise passes the child's results straight through.
  assign valid = core_valid & started_q;
  assign data  = core_data;
endmodule
</answer>
Note: the glue's job here is a one-bit qualifier. It does not re-derive `data`.
</example_3>
"""


# Emitted LAST in the glue user message, so the composition obligation is the
# most recent thing in context rather than buried ~21K tokens up. The port
# checklist turns the vestigial-glue rejection into a generation-time
# obligation instead of a post-hoc gate failure.
GLUE_PORT_CHECKLIST_PROMPT = r"""
BEFORE YOU WRITE THE MODULE — composition checklist (this node is GLUE):

1. List every child-facing port whose direction is INPUT to this module
   (these carry a child's RESULTS into your glue).
2. For each one, name the external output or sibling child input it feeds.
   If you cannot name a consumer for a child-facing input, your design is
   WRONG: you have recomputed that child's function instead of using it.
3. You may add registers, muxes, qualifiers and FSM logic to reconcile timing
   or add guarantees the children do not make. You may NOT recompute anything
   a child already produces.
4. Do NOT instantiate child modules. They are connected externally by ports.

5. TIMING — do this per external output, and do not skip it. Child latencies do
   NOT compose by addition, and this is the single most common way a glue that
   looks right fails. For EACH external output, state to yourself:
     (a) which child port sources it;
     (b) the cycle that source is actually valid — a REGISTERED child output is
         valid one cycle AFTER the condition that produced it;
     (c) the cycle the spec requires this output valid, and relative to which
         other signal (e.g. "product valid the same cycle ready rises");
     (d) the realignment the glue must add to close (b) -> (c).
   If (b) != (c) you MUST add the register/hold/gate that closes the gap. Two
   children that each correctly claim "N+1 cycles" compose to N+3 across a
   registered handshake, because each handshake signal costs a cycle that
   neither child's own contract can see.

6. A status/valid output (`ready`, `done`, `valid`) must be qualified by the
   glue's own state, never wired straight through from a child. A child's
   "I am idle" is not the parent's "the requested operation has completed":
   asserting it out of reset, before any operation was requested, is a failure.

7. REPLICATED CHILDREN. If a child's contract carries `replication_count: N`
   with N > 1, the parent instantiates N copies of it and your child-facing
   ports for that child are FLATTENED BUSES, not single values: a port of width
   W becomes a bus of width N*W carrying every instance's copy, low instance in
   the low bits. Drive and read instance `i`'s slice as

       <child>_<port>[(i+1)*W-1 -: W]        // W > 1
       <child>_<port>[i]                     // W == 1

   Wiring such a bus as if it were one scalar connects instance 0 and leaves
   every other instance undriven, which simulates as a partially-correct result
   rather than an error.

A composition whose child-facing inputs are unread is rejected automatically by
the harness before simulation, however plausible the RTL looks.
"""


# ---------------------------------------------------------------------------
# GLUE (composition-node) testbench exemplar.
#
# TB_4_SHOT_EXAMPLES is 16,280 chars demonstrating four LEAF testbenches, with
# zero occurrences of child_assumes, rtl_available, or child instantiation. The
# composition TB task is strictly harder than the leaf one -- it must
# instantiate the REAL child modules and bridge each child's UNPREFIXED ports
# to the DUT's PREFIXED child-facing ports -- and had no worked example at all.
#
# Live consequence (fp_adder stage5_round_pack, 2026-07-26): the generated
# self-TB instantiated a helper module `signed_mult_16` that does not exist,
# so the oracle could not elaborate (%Error-MODMISSING) and the composition
# gate could never pass regardless of the glue.
# ---------------------------------------------------------------------------
