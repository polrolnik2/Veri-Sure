module fpu_exceptions__probed (
    input clk,
    input rst,
    input enable,
    input [1:0] rmode,
    input [63:0] opa,
    input [63:0] opb,
    input [63:0] in_except,
    input [11:0] exponent_in,
    input [1:0] mantissa_in,
    input [2:0] fpu_op,
    output reg [63:0] out,
    output reg ex_enable,
    output reg underflow,
    output reg overflow,
    output reg inexact,
    output reg exception,
    output reg invalid,

    output in_et_zero,
    output opa_et_zero,
    output opb_et_zero,
    output input_et_zero,
    output add,
    output subtract,
    output multiply,
    output divide,
    output opa_qnan,
    output opb_qnan,
    output opa_snan,
    output opb_snan,
    output opa_pos_inf,
    output opb_pos_inf,
    output opa_neg_inf,
    output opb_neg_inf,
    output opa_inf,
    output opb_inf,
    output nan_input,
    output snan_input,
    output a_nan,
    output div_by_0,
    output div_0_by_0,
    output div_inf_by_inf,
    output div_by_inf,
    output mul_0_by_inf,
    output mul_inf,
    output div_inf,
    output add_inf,
    output sub_inf,
    output addsub_inf_invalid,
    output addsub_inf,
    output out_inf_trigger,
    output out_pos_inf,
    output out_neg_inf,
    output round_nearest,
    output round_to_zero,
    output round_to_pos_inf,
    output round_to_neg_inf,
    output inf_round_down_trigger,
    output mul_uf,
    output div_uf,
    output underflow_trigger,
    output invalid_trigger,
    output overflow_trigger,
    output inexact_trigger,
    output except_trigger,
    output enable_trigger,
    output nan_out_trigger,
    output snan_trigger,
    output [10:0] exp_2047,
    output [10:0] exp_2046,
    output [62:0] nan_output_0,
    output [62:0] nan_output,
    output [51:0] mantissa_max,
    output [62:0] inf_round_down,
    output [62:0] out_inf,
    output [63:0] out_0,
    output [63:0] out_1,
    output [63:0] out_2
);

    localparam [10:0] EXP_2047_C = 11'h7ff;
    localparam [10:0] EXP_2046_C = 11'h7fe;
    localparam [51:0] MANTISSA_MAX_C = 52'hfffffffffffff;

    wire [62:0] INF_VALUE_C = {EXP_2047_C, 52'b0};
    wire [62:0] MAX_FINITE_C = {EXP_2046_C, MANTISSA_MAX_C};

    wire in_et_zero_d = (in_except[62:0] == 63'b0);
    wire input_et_zero_d = (in_except[62:0] == 63'b0);
    wire opa_et_zero_d = (opa[62:0] == 63'b0);
    wire opb_et_zero_d = (opb[62:0] == 63'b0);

    wire add_d      = (fpu_op == 3'b000);
    wire subtract_d = (fpu_op == 3'b001);
    wire multiply_d = (fpu_op == 3'b010);
    wire divide_d   = (fpu_op == 3'b011);

    wire opa_nan_d = (&opa[62:52]) && (|opa[51:0]);
    wire opb_nan_d = (&opb[62:52]) && (|opb[51:0]);
    wire opa_qnan_d = opa_nan_d && opa[51];
    wire opb_qnan_d = opb_nan_d && opb[51];
    wire opa_snan_d = opa_nan_d && !opa[51];
    wire opb_snan_d = opb_nan_d && !opb[51];

    wire opa_inf_d = (&opa[62:52]) && !(|opa[51:0]);
    wire opb_inf_d = (&opb[62:52]) && !(|opb[51:0]);
    wire opa_pos_inf_d = opa_inf_d && !opa[63];
    wire opb_pos_inf_d = opb_inf_d && !opb[63];
    wire opa_neg_inf_d = opa_inf_d && opa[63];
    wire opb_neg_inf_d = opb_inf_d && opb[63];

    wire nan_input_d = opa_nan_d || opb_nan_d;
    wire snan_input_d = opa_snan_d || opb_snan_d;

    wire div_by_0_d = divide_d && opb_et_zero_d &&
                      !opa_et_zero_d && !opa_inf_d && !opa_nan_d;
    wire div_0_by_0_d = divide_d && opa_et_zero_d && opb_et_zero_d;
    wire div_inf_by_inf_d = divide_d && opa_inf_d && opb_inf_d;
    wire div_by_inf_d = divide_d && opb_inf_d && !opa_inf_d && !opa_nan_d;

    wire mul_0_by_inf_d = multiply_d &&
                          ((opa_et_zero_d && opb_inf_d) ||
                           (opb_et_zero_d && opa_inf_d));
    wire mul_inf_d = multiply_d && (opa_inf_d || opb_inf_d);

    wire div_inf_d = divide_d && opa_inf_d && !opb_inf_d &&
                     !opb_et_zero_d && !opb_nan_d;

    wire add_inf_d = add_d && (opa_inf_d || opb_inf_d);
    wire sub_inf_d = subtract_d && (opa_inf_d || opb_inf_d);
    wire addsub_inf_invalid_d =
        (add_d &&
         ((opa_pos_inf_d && opb_neg_inf_d) ||
          (opa_neg_inf_d && opb_pos_inf_d))) ||
        (subtract_d &&
         ((opa_pos_inf_d && opb_pos_inf_d) ||
          (opa_neg_inf_d && opb_neg_inf_d)));
    wire addsub_inf_d = add_inf_d || sub_inf_d;

    wire addsub_valid_inf_d = addsub_inf_d &&
                              !addsub_inf_invalid_d && !nan_input_d;
    wire mul_valid_inf_d = mul_inf_d && !mul_0_by_inf_d && !nan_input_d;
    wire div_valid_inf_d = div_inf_d && !nan_input_d;

    wire out_inf_trigger_d = mul_valid_inf_d || div_valid_inf_d ||
                             div_by_0_d || addsub_valid_inf_d ||
                             (exponent_in > 12'd2046);

    wire out_pos_inf_d = out_inf_trigger_d && !in_except[63];
    wire out_neg_inf_d = out_inf_trigger_d && in_except[63];

    wire round_nearest_d = (rmode == 2'b00);
    wire round_to_zero_d = (rmode == 2'b01);
    wire round_to_pos_inf_d = (rmode == 2'b10);
    wire round_to_neg_inf_d = (rmode == 2'b11);

    wire inf_round_down_trigger_d =
        (out_pos_inf_d && (round_to_zero_d || round_to_neg_inf_d)) ||
        (out_neg_inf_d && (round_to_zero_d || round_to_pos_inf_d));

    wire mul_uf_d = multiply_d && !opa_et_zero_d && !opb_et_zero_d &&
                    !opa_inf_d && !opb_inf_d && in_et_zero_d;
    wire div_uf_d = div_by_inf_d ||
                    (divide_d && !opa_et_zero_d && !opb_et_zero_d &&
                     !opa_inf_d && !opb_inf_d && in_et_zero_d);
    wire underflow_trigger_d = mul_uf_d || div_uf_d;

    wire invalid_trigger_d = snan_input_d || addsub_inf_invalid_d ||
                             mul_0_by_inf_d || div_0_by_0_d ||
                             div_inf_by_inf_d;
    wire overflow_trigger_d = out_inf_trigger_d && !nan_input_d;
    wire inexact_trigger_d = !nan_input_d &&
                             ((|mantissa_in) || out_inf_trigger_d ||
                              underflow_trigger_d);
    wire except_trigger_d = invalid_trigger_d || overflow_trigger_d ||
                            underflow_trigger_d || inexact_trigger_d;

    wire nan_out_trigger_d = nan_input_d || invalid_trigger_d;
    wire a_nan_d = nan_out_trigger_d;
    wire enable_trigger_d = nan_out_trigger_d || out_inf_trigger_d ||
                            underflow_trigger_d || inexact_trigger_d;

    wire [51:0] selected_nan_fraction_d =
        opa_nan_d ? opa[51:0] :
        opb_nan_d ? opb[51:0] :
                    opa[51:0];
    wire [62:0] nan_payload_d =
        {EXP_2047_C, (selected_nan_fraction_d | 52'h8000000000000)};

    wire [63:0] stage0_d =
        (underflow_trigger_d && in_et_zero_d)
            ? {in_except[63], 63'b0}
            : in_except;
    wire [62:0] infinity_magnitude_d =
        inf_round_down_trigger_d ? MAX_FINITE_C : INF_VALUE_C;
    wire [63:0] stage1_d =
        out_inf_trigger_d ? {in_except[63], infinity_magnitude_d} : stage0_d;


assign stage0_d = underflow_trigger_d ? {in_except[63], 63'b0} : in_except;


wire [63:0] stage2_d = nan_out_trigger_d ? {in_except[63], nan_payload_d} : stage1_d;

    reg in_et_zero_r, opa_et_zero_r, opb_et_zero_r, input_et_zero_r;
    reg add_r, subtract_r, multiply_r, divide_r;
    reg opa_qnan_r, opb_qnan_r, opa_snan_r, opb_snan_r;
    reg opa_pos_inf_r, opb_pos_inf_r, opa_neg_inf_r, opb_neg_inf_r;
    reg opa_inf_r, opb_inf_r;
    reg nan_input_r, snan_input_r, a_nan_r;
    reg div_by_0_r, div_0_by_0_r, div_inf_by_inf_r, div_by_inf_r;
    reg mul_0_by_inf_r, mul_inf_r, div_inf_r;
    reg add_inf_r, sub_inf_r, addsub_inf_invalid_r, addsub_inf_r;
    reg out_inf_trigger_r, out_pos_inf_r, out_neg_inf_r;
    reg round_nearest_r, round_to_zero_r;
    reg round_to_pos_inf_r, round_to_neg_inf_r;
    reg inf_round_down_trigger_r;
    reg mul_uf_r, div_uf_r, underflow_trigger_r;
    reg invalid_trigger_r, overflow_trigger_r, inexact_trigger_r;
    reg except_trigger_r, enable_trigger_r, nan_out_trigger_r, snan_trigger_r;

    reg [62:0] nan_output_0_r, nan_output_r;
    reg [63:0] out_0_r, out_1_r, out_2_r;

    assign in_et_zero = in_et_zero_r;
    assign opa_et_zero = opa_et_zero_r;
    assign opb_et_zero = opb_et_zero_r;
    assign input_et_zero = input_et_zero_r;

    assign add = add_r;
    assign subtract = subtract_r;
    assign multiply = multiply_r;
    assign divide = divide_r;

    assign opa_qnan = opa_qnan_r;
    assign opb_qnan = opb_qnan_r;
    assign opa_snan = opa_snan_r;
    assign opb_snan = opb_snan_r;
    assign opa_pos_inf = opa_pos_inf_r;
    assign opb_pos_inf = opb_pos_inf_r;
    assign opa_neg_inf = opa_neg_inf_r;
    assign opb_neg_inf = opb_neg_inf_r;
    assign opa_inf = opa_inf_r;
    assign opb_inf = opb_inf_r;

    assign nan_input = nan_input_r;
    assign snan_input = snan_input_r;
    assign a_nan = a_nan_r;
    assign div_by_0 = div_by_0_r;
    assign div_0_by_0 = div_0_by_0_r;
    assign div_inf_by_inf = div_inf_by_inf_r;
    assign div_by_inf = div_by_inf_r;
    assign mul_0_by_inf = mul_0_by_inf_r;
    assign mul_inf = mul_inf_r;
    assign div_inf = div_inf_r;
    assign add_inf = add_inf_r;
    assign sub_inf = sub_inf_r;
    assign addsub_inf_invalid = addsub_inf_invalid_r;
    assign addsub_inf = addsub_inf_r;

    assign out_inf_trigger = out_inf_trigger_r;
    assign out_pos_inf = out_pos_inf_r;
    assign out_neg_inf = out_neg_inf_r;
    assign round_nearest = round_nearest_r;
    assign round_to_zero = round_to_zero_r;
    assign round_to_pos_inf = round_to_pos_inf_r;
    assign round_to_neg_inf = round_to_neg_inf_r;
    assign inf_round_down_trigger = inf_round_down_trigger_r;
    assign mul_uf = mul_uf_r;
    assign div_uf = div_uf_r;
    assign underflow_trigger = underflow_trigger_r;
    assign invalid_trigger = invalid_trigger_r;
    assign overflow_trigger = overflow_trigger_r;
    assign inexact_trigger = inexact_trigger_r;
    assign except_trigger = except_trigger_r;
    assign enable_trigger = enable_trigger_r;
    assign nan_out_trigger = nan_out_trigger_r;
    assign snan_trigger = snan_trigger_r;

    assign exp_2047 = EXP_2047_C;
    assign exp_2046 = EXP_2046_C;
    assign mantissa_max = MANTISSA_MAX_C;
    assign inf_round_down = MAX_FINITE_C;
    assign out_inf = INF_VALUE_C;

    assign nan_output_0 = nan_output_0_r;
    assign nan_output = nan_output_r;
    assign out_0 = out_0_r;
    assign out_1 = out_1_r;
    assign out_2 = out_2_r;

    always @(posedge clk) begin
        if (rst) begin
            out <= 64'b0;
            ex_enable <= 1'b0;
            underflow <= 1'b0;
            overflow <= 1'b0;
            inexact <= 1'b0;
            exception <= 1'b0;
            invalid <= 1'b0;

            in_et_zero_r <= 1'b0;
            opa_et_zero_r <= 1'b0;
            opb_et_zero_r <= 1'b0;
            input_et_zero_r <= 1'b0;
            add_r <= 1'b0;
            subtract_r <= 1'b0;
            multiply_r <= 1'b0;
            divide_r <= 1'b0;

            opa_qnan_r <= 1'b0;
            opb_qnan_r <= 1'b0;
            opa_snan_r <= 1'b0;
            opb_snan_r <= 1'b0;
            opa_pos_inf_r <= 1'b0;
            opb_pos_inf_r <= 1'b0;
            opa_neg_inf_r <= 1'b0;
            opb_neg_inf_r <= 1'b0;
            opa_inf_r <= 1'b0;
            opb_inf_r <= 1'b0;

            nan_input_r <= 1'b0;
            snan_input_r <= 1'b0;
            a_nan_r <= 1'b0;
            div_by_0_r <= 1'b0;
            div_0_by_0_r <= 1'b0;
            div_inf_by_inf_r <= 1'b0;
            div_by_inf_r <= 1'b0;
            mul_0_by_inf_r <= 1'b0;
            mul_inf_r <= 1'b0;
            div_inf_r <= 1'b0;
            add_inf_r <= 1'b0;
            sub_inf_r <= 1'b0;
            addsub_inf_invalid_r <= 1'b0;
            addsub_inf_r <= 1'b0;

            out_inf_trigger_r <= 1'b0;
            out_pos_inf_r <= 1'b0;
            out_neg_inf_r <= 1'b0;
            round_nearest_r <= 1'b0;
            round_to_zero_r <= 1'b0;
            round_to_pos_inf_r <= 1'b0;
            round_to_neg_inf_r <= 1'b0;
            inf_round_down_trigger_r <= 1'b0;

            mul_uf_r <= 1'b0;
            div_uf_r <= 1'b0;
            underflow_trigger_r <= 1'b0;
            invalid_trigger_r <= 1'b0;
            overflow_trigger_r <= 1'b0;
            inexact_trigger_r <= 1'b0;
            except_trigger_r <= 1'b0;
            enable_trigger_r <= 1'b0;
            nan_out_trigger_r <= 1'b0;
            snan_trigger_r <= 1'b0;

            nan_output_0_r <= 63'b0;
            nan_output_r <= 63'b0;
            out_0_r <= 64'b0;
            out_1_r <= 64'b0;
            out_2_r <= 64'b0;
        end else if (enable) begin
            in_et_zero_r <= in_et_zero_d;
            opa_et_zero_r <= opa_et_zero_d;
            opb_et_zero_r <= opb_et_zero_d;
            input_et_zero_r <= input_et_zero_d;

            add_r <= add_d;
            subtract_r <= subtract_d;
            multiply_r <= multiply_d;
            divide_r <= divide_d;

            opa_qnan_r <= opa_qnan_d;
            opb_qnan_r <= opb_qnan_d;
            opa_snan_r <= opa_snan_d;
            opb_snan_r <= opb_snan_d;
            opa_pos_inf_r <= opa_pos_inf_d;
            opb_pos_inf_r <= opb_pos_inf_d;
            opa_neg_inf_r <= opa_neg_inf_d;
            opb_neg_inf_r <= opb_neg_inf_d;
            opa_inf_r <= opa_inf_d;
            opb_inf_r <= opb_inf_d;

            nan_input_r <= nan_input_d;
            snan_input_r <= snan_input_d;
            a_nan_r <= a_nan_d;
            div_by_0_r <= div_by_0_d;
            div_0_by_0_r <= div_0_by_0_d;
            div_inf_by_inf_r <= div_inf_by_inf_d;
            div_by_inf_r <= div_by_inf_d;
            mul_0_by_inf_r <= mul_0_by_inf_d;
            mul_inf_r <= mul_inf_d;
            div_inf_r <= div_inf_d;
            add_inf_r <= add_inf_d;
            sub_inf_r <= sub_inf_d;
            addsub_inf_invalid_r <= addsub_inf_invalid_d;
            addsub_inf_r <= addsub_inf_d;

            out_inf_trigger_r <= out_inf_trigger_d;
            out_pos_inf_r <= out_pos_inf_d;
            out_neg_inf_r <= out_neg_inf_d;
            round_nearest_r <= round_nearest_d;
            round_to_zero_r <= round_to_zero_d;
            round_to_pos_inf_r <= round_to_pos_inf_d;
            round_to_neg_inf_r <= round_to_neg_inf_d;
            inf_round_down_trigger_r <= inf_round_down_trigger_d;

            mul_uf_r <= mul_uf_d;
            div_uf_r <= div_uf_d;
            underflow_trigger_r <= underflow_trigger_d;
            invalid_trigger_r <= invalid_trigger_d;
            overflow_trigger_r <= overflow_trigger_d;
            inexact_trigger_r <= inexact_trigger_d;
            except_trigger_r <= except_trigger_d;
            enable_trigger_r <= enable_trigger_d;
            nan_out_trigger_r <= nan_out_trigger_d;
            snan_trigger_r <= snan_input_d;

            underflow <= underflow_trigger_d;
            overflow <= overflow_trigger_d;
            inexact <= inexact_trigger_d;
            invalid <= invalid_trigger_d;
            exception <= except_trigger_d;
            ex_enable <= enable_trigger_d;

            nan_output_0_r <= nan_payload_d;
            nan_output_r <= nan_output_0_r;
            out_0_r <= stage0_d;
            out_1_r <= stage1_d;
            out_2_r <= stage2_d;
            out <= stage2_d;
        end
    end

endmodule

// Shipped interface: the contract's ports, probes left unconnected.
module fpu_exceptions (
    input wire clk,
    input wire rst,
    input wire enable,
    input wire [1:0] rmode,
    input wire [63:0] opa,
    input wire [63:0] opb,
    input wire [63:0] in_except,
    input wire [11:0] exponent_in,
    input wire [1:0] mantissa_in,
    input wire [2:0] fpu_op,
    output wire [63:0] out,
    output wire ex_enable,
    output wire underflow,
    output wire overflow,
    output wire inexact,
    output wire exception,
    output wire invalid
);
    fpu_exceptions__probed u_probed (
        .clk(clk),
        .rst(rst),
        .enable(enable),
        .rmode(rmode),
        .opa(opa),
        .opb(opb),
        .in_except(in_except),
        .exponent_in(exponent_in),
        .mantissa_in(mantissa_in),
        .fpu_op(fpu_op),
        .out(out),
        .ex_enable(ex_enable),
        .underflow(underflow),
        .overflow(overflow),
        .inexact(inexact),
        .exception(exception),
        .invalid(invalid)
    );
endmodule
