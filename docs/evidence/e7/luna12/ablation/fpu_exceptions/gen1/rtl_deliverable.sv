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
    output [63:0] out,
    output ex_enable,
    output underflow,
    output overflow,
    output inexact,
    output exception,
    output invalid,

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

    localparam [51:0] QUIET_BIT = 52'h8000000000000;
    localparam [62:0] INF_MAG = {11'h7ff, 52'b0};
    localparam [62:0] MAX_FINITE_MAG = {11'h7fe, 52'hfffffffffffff};

    wire add_d       = (fpu_op == 3'b000);
    wire subtract_d  = (fpu_op == 3'b001);
    wire multiply_d  = (fpu_op == 3'b010);
    wire divide_d    = (fpu_op == 3'b011);

    wire opa_zero_d = (opa[62:0] == 63'b0);
    wire opb_zero_d = (opb[62:0] == 63'b0);
    wire in_zero_d  = (in_except[62:0] == 63'b0);

    wire opa_nan_d = (opa[62:52] == 11'h7ff) && (opa[51:0] != 52'b0);
    wire opb_nan_d = (opb[62:52] == 11'h7ff) && (opb[51:0] != 52'b0);
    wire opa_qnan_d = opa_nan_d && opa[51];
    wire opb_qnan_d = opb_nan_d && opb[51];
    wire opa_snan_d = opa_nan_d && !opa[51];
    wire opb_snan_d = opb_nan_d && !opb[51];
    wire nan_input_d = opa_nan_d || opb_nan_d;
    wire snan_input_d = opa_snan_d || opb_snan_d;

    wire opa_inf_d = (opa[62:52] == 11'h7ff) && (opa[51:0] == 52'b0);
    wire opb_inf_d = (opb[62:52] == 11'h7ff) && (opb[51:0] == 52'b0);
    wire opa_pos_inf_d = opa_inf_d && !opa[63];
    wire opb_pos_inf_d = opb_inf_d && !opb[63];
    wire opa_neg_inf_d = opa_inf_d && opa[63];
    wire opb_neg_inf_d = opb_inf_d && opb[63];

    wire div_by_0_d =
        divide_d && opb_zero_d && !opa_zero_d && !opa_inf_d && !nan_input_d;
    wire div_0_by_0_d = divide_d && opa_zero_d && opb_zero_d;
    wire div_inf_by_inf_d = divide_d && opa_inf_d && opb_inf_d;
    wire div_by_inf_d = divide_d && opb_inf_d && !opa_inf_d && !nan_input_d;

    wire mul_0_by_inf_d =
        multiply_d && ((opa_zero_d && opb_inf_d) || (opb_zero_d && opa_inf_d));
    wire mul_inf_d = multiply_d && (opa_inf_d || opb_inf_d);
    wire div_inf_d = divide_d && (opa_inf_d || opb_inf_d);

    wire add_inf_d = add_d && (opa_inf_d || opb_inf_d);
    wire sub_inf_d = subtract_d && (opa_inf_d || opb_inf_d);
    wire addsub_inf_invalid_d =
        (add_d &&
         ((opa_pos_inf_d && opb_neg_inf_d) ||
          (opa_neg_inf_d && opb_pos_inf_d))) ||
        (subtract_d &&
         ((opa_pos_inf_d && opb_pos_inf_d) ||
          (opa_neg_inf_d && opb_neg_inf_d)));
    wire addsub_inf_d =
        (add_inf_d || sub_inf_d) && !addsub_inf_invalid_d;

    wire out_inf_trigger_d =
        addsub_inf_d ||
        (mul_inf_d && !mul_0_by_inf_d) ||
        (divide_d && ((opa_inf_d && !opb_inf_d) || div_by_0_d)) ||
        div_by_0_d ||
        (exponent_in > 12'd2046);

    wire out_pos_inf_d = out_inf_trigger_d && !in_except[63];
    wire out_neg_inf_d = out_inf_trigger_d && in_except[63];

    wire round_nearest_d    = (rmode == 2'b00);
    wire round_to_zero_d    = (rmode == 2'b01);
    wire round_to_pos_inf_d = (rmode == 2'b10);
    wire round_to_neg_inf_d = (rmode == 2'b11);

    wire inf_round_down_trigger_d =
        out_inf_trigger_d &&
        ((out_pos_inf_d && (round_to_zero_d || round_to_neg_inf_d)) ||
         (out_neg_inf_d && (round_to_zero_d || round_to_pos_inf_d)));

    wire mul_uf_d =
        multiply_d && !opa_zero_d && !opb_zero_d &&
        !opa_inf_d && !opb_inf_d && !nan_input_d && in_zero_d;

    wire div_uf_d =
        divide_d && !nan_input_d &&
        ((opb_inf_d && !opa_inf_d && !opa_zero_d) ||
         (!opa_zero_d && !opb_zero_d && !opa_inf_d && !opb_inf_d && in_zero_d));

    wire underflow_trigger_d = mul_uf_d || div_uf_d;

    wire invalid_trigger_d =
        snan_input_d || addsub_inf_invalid_d || mul_0_by_inf_d ||
        div_0_by_0_d || div_inf_by_inf_d;

    wire overflow_trigger_d = out_inf_trigger_d && !nan_input_d;
    wire inexact_trigger_d =
        ((|mantissa_in) || out_inf_trigger_d || underflow_trigger_d) &&
        !nan_input_d;
    wire except_trigger_d =
        invalid_trigger_d || overflow_trigger_d ||
        (underflow_trigger_d && !nan_input_d) || inexact_trigger_d;
    wire enable_trigger_d = except_trigger_d;
    wire nan_out_trigger_d = nan_input_d || invalid_trigger_d;

    wire [51:0] nan_fraction_d =
        opa_nan_d ? (opa[51:0] | QUIET_BIT) :
        opb_nan_d ? (opb[51:0] | QUIET_BIT) :
                    (opa[51:0] | QUIET_BIT);
    wire [62:0] nan_magnitude_d = {11'h7ff, nan_fraction_d};

    wire [62:0] selected_inf_magnitude_d =
        inf_round_down_trigger_d ? MAX_FINITE_MAG : INF_MAG;
    wire [63:0] normal_or_zero_d =
        underflow_trigger_d ? {in_except[63], 63'b0} : in_except;
    wire [63:0] normal_or_inf_d =
        out_inf_trigger_d ? {in_except[63], selected_inf_magnitude_d} :
                            normal_or_zero_d;
    wire [63:0] selected_result_d =
        nan_out_trigger_d ? {in_except[63], nan_magnitude_d} :
                            normal_or_inf_d;

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
    reg round_nearest_r, round_to_zero_r, round_to_pos_inf_r, round_to_neg_inf_r;
    reg inf_round_down_trigger_r;
    reg mul_uf_r, div_uf_r, underflow_trigger_r;
    reg invalid_trigger_r, overflow_trigger_r, inexact_trigger_r;
    reg except_trigger_r, enable_trigger_r, nan_out_trigger_r, snan_trigger_r;

    reg [62:0] nan_output_0_r, nan_output_r;
    reg [63:0] out_0_r, out_1_r, out_2_r;

    reg underflow_p0, underflow_p1, underflow_p2;
    reg overflow_p0, overflow_p1, overflow_p2;
    reg inexact_p0, inexact_p1, inexact_p2;
    reg exception_p0, exception_p1, exception_p2;
    reg invalid_p0, invalid_p1, invalid_p2;
    reg ex_enable_p0, ex_enable_p1, ex_enable_p2;

    assign exp_2047 = 11'b11111111111;
    assign exp_2046 = 11'b11111111110;
    assign mantissa_max = 52'hfffffffffffff;
    assign inf_round_down = MAX_FINITE_MAG;
    assign out_inf = INF_MAG;

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
    assign snan_trigger = snan_input_r;
    assign nan_output_0 = nan_output_0_r;
    assign nan_output = nan_output_r;
    assign out_0 = out_0_r;
    assign out_1 = out_1_r;
    assign out_2 = out_2_r;

    assign out = out_2_r;
    assign underflow = underflow_p2;
    assign overflow = overflow_p2;
    assign inexact = inexact_p2;
    assign exception = exception_p2;
    assign invalid = invalid_p2;
    assign ex_enable = ex_enable_p2;

    always @(posedge clk) begin
        if (rst) begin
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
            nan_output_0_r <= 63'b0;
            nan_output_r <= 63'b0;
            out_0_r <= 64'b0;
            out_1_r <= 64'b0;
            out_2_r <= 64'b0;
            underflow_p0 <= 1'b0;
            underflow_p1 <= 1'b0;
            underflow_p2 <= 1'b0;
            overflow_p0 <= 1'b0;
            overflow_p1 <= 1'b0;
            overflow_p2 <= 1'b0;
            inexact_p0 <= 1'b0;
            inexact_p1 <= 1'b0;
            inexact_p2 <= 1'b0;
            exception_p0 <= 1'b0;
            exception_p1 <= 1'b0;
            exception_p2 <= 1'b0;
            invalid_p0 <= 1'b0;
            invalid_p1 <= 1'b0;
            invalid_p2 <= 1'b0;
            ex_enable_p0 <= 1'b0;
            ex_enable_p1 <= 1'b0;
            ex_enable_p2 <= 1'b0;
        end else if (enable) begin
            in_et_zero_r <= in_zero_d;
            opa_et_zero_r <= opa_zero_d;
            opb_et_zero_r <= opb_zero_d;
            input_et_zero_r <= in_zero_d;
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
            a_nan_r <= opa_nan_d;
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
            nan_output_0_r <= nan_magnitude_d;
            nan_output_r <= nan_output_0_r;
            out_0_r <= selected_result_d;
            out_1_r <= out_0_r;
            out_2_r <= out_1_r;

            underflow_p0 <= underflow_trigger_d && !nan_input_d;
            underflow_p1 <= underflow_p0;
            underflow_p2 <= underflow_p1;
            overflow_p0 <= overflow_trigger_d;
            overflow_p1 <= overflow_p0;
            overflow_p2 <= overflow_p1;
            inexact_p0 <= inexact_trigger_d;
            inexact_p1 <= inexact_p0;
            inexact_p2 <= inexact_p1;
            exception_p0 <= except_trigger_d;
            exception_p1 <= exception_p0;
            exception_p2 <= exception_p1;
            invalid_p0 <= invalid_trigger_d;
            invalid_p1 <= invalid_p0;
            invalid_p2 <= invalid_p1;
            ex_enable_p0 <= enable_trigger_d;
            ex_enable_p1 <= ex_enable_p0;
            ex_enable_p2 <= ex_enable_p1;
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
