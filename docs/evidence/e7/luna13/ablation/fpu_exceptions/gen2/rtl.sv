module fpu_exceptions (
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
    reg mul_uf_r, div_uf_r, underflow_trigger_r, invalid_trigger_r;
    reg overflow_trigger_r, inexact_trigger_r, except_trigger_r;
    reg enable_trigger_r, nan_out_trigger_r, snan_trigger_r;

    reg [62:0] nan_output_0_r, nan_output_r;
    reg [63:0] out_0_r, out_1_r, out_2_r;

    reg inf_select_d0, inf_down_d0, inf_sign_d0;
    reg nan_select_d0, nan_select_d1, nan_sign_d0, nan_sign_d1;

    wire opa_zero_c, opb_zero_c, input_zero_c;
    wire opa_nan_c, opb_nan_c, opa_qnan_c, opb_qnan_c;
    wire opa_snan_c, opb_snan_c;
    wire opa_inf_c, opb_inf_c;
    wire opa_pos_inf_c, opb_pos_inf_c, opa_neg_inf_c, opb_neg_inf_c;
    wire add_c, subtract_c, multiply_c, divide_c;
    wire nan_input_c, snan_input_c;
    wire div_by_0_c, div_0_by_0_c, div_inf_by_inf_c, div_by_inf_c;
    wire mul_0_by_inf_c, mul_inf_c, div_inf_c;
    wire addsub_inf_invalid_c, add_inf_c, sub_inf_c, addsub_inf_c;
    wire out_inf_trigger_c, out_pos_inf_c, out_neg_inf_c;
    wire round_nearest_c, round_to_zero_c, round_to_pos_inf_c, round_to_neg_inf_c;
    wire inf_round_down_trigger_c;
    wire mul_uf_c, div_uf_c, underflow_trigger_c, invalid_trigger_c;
    wire overflow_trigger_c, inexact_trigger_c, except_trigger_c;
    wire enable_trigger_c, nan_out_trigger_c, a_nan_c;
    wire [62:0] nan_payload_c;
    wire [62:0] inf_mag_c, max_finite_mag_c;

    assign opa_zero_c = (opa[62:0] == 63'b0);
    assign opb_zero_c = (opb[62:0] == 63'b0);
    assign input_zero_c = (in_except[62:0] == 63'b0);

    assign opa_nan_c = (&opa[62:52]) && (|opa[51:0]);
    assign opb_nan_c = (&opb[62:52]) && (|opb[51:0]);
    assign opa_qnan_c = opa_nan_c && opa[51];
    assign opb_qnan_c = opb_nan_c && opb[51];
    assign opa_snan_c = opa_nan_c && !opa[51];
    assign opb_snan_c = opb_nan_c && !opb[51];

    assign opa_inf_c = (&opa[62:52]) && (opa[51:0] == 52'b0);
    assign opb_inf_c = (&opb[62:52]) && (opb[51:0] == 52'b0);
    assign opa_pos_inf_c = opa_inf_c && !opa[63];
    assign opa_neg_inf_c = opa_inf_c && opa[63];
    assign opb_pos_inf_c = opb_inf_c && !opb[63];
    assign opb_neg_inf_c = opb_inf_c && opb[63];

    assign add_c      = (fpu_op == 3'b000);
    assign subtract_c = (fpu_op == 3'b001);
    assign multiply_c = (fpu_op == 3'b010);
    assign divide_c   = (fpu_op == 3'b011);

    assign nan_input_c = opa_nan_c || opb_nan_c;
    assign snan_input_c = opa_snan_c || opb_snan_c;

    assign div_0_by_0_c = divide_c && opa_zero_c && opb_zero_c;
    assign div_inf_by_inf_c = divide_c && opa_inf_c && opb_inf_c;
    assign div_by_0_c = divide_c && opb_zero_c && !opa_zero_c && !nan_input_c;
    assign div_by_inf_c = divide_c && opb_inf_c && !opa_inf_c && !opa_nan_c;

    assign mul_0_by_inf_c = multiply_c &&
                             ((opa_zero_c && opb_inf_c) ||
                              (opa_inf_c && opb_zero_c));
    assign mul_inf_c = multiply_c && (opa_inf_c || opb_inf_c) &&
                       !mul_0_by_inf_c && !nan_input_c;
    assign div_inf_c = divide_c && opa_inf_c && !opb_inf_c && !nan_input_c;

    assign addsub_inf_invalid_c =
        (add_c &&
         ((opa_pos_inf_c && opb_neg_inf_c) ||
          (opa_neg_inf_c && opb_pos_inf_c))) ||
        (subtract_c &&
         ((opa_pos_inf_c && opb_pos_inf_c) ||
          (opa_neg_inf_c && opb_neg_inf_c)));

    assign add_inf_c = add_c && (opa_inf_c || opb_inf_c) &&
                       !addsub_inf_invalid_c && !nan_input_c;
    assign sub_inf_c = subtract_c && (opa_inf_c || opb_inf_c) &&
                       !addsub_inf_invalid_c && !nan_input_c;
    assign addsub_inf_c = add_inf_c || sub_inf_c;

    assign out_inf_trigger_c = mul_inf_c || div_inf_c || addsub_inf_c ||
                               div_by_0_c || (exponent_in > 12'd2046);

    assign round_nearest_c = (rmode == 2'b00);
    assign round_to_zero_c = (rmode == 2'b01);
    assign round_to_pos_inf_c = (rmode == 2'b10);
    assign round_to_neg_inf_c = (rmode == 2'b11);

    assign nan_out_trigger_c = nan_input_c || snan_input_c ||
                               addsub_inf_invalid_c || mul_0_by_inf_c ||
                               div_0_by_0_c || div_inf_by_inf_c;
    assign a_nan_c = nan_out_trigger_c;

    assign out_pos_inf_c = out_inf_trigger_c && !nan_out_trigger_c &&
                           !in_except[63];
    assign out_neg_inf_c = out_inf_trigger_c && !nan_out_trigger_c &&
                           in_except[63];

    assign inf_round_down_trigger_c =
        out_inf_trigger_c && !nan_out_trigger_c &&
        ((!in_except[63] && (round_to_zero_c || round_to_neg_inf_c)) ||
         ( in_except[63] && (round_to_zero_c || round_to_pos_inf_c)));

    assign mul_uf_c = multiply_c && !opa_zero_c && !opb_zero_c &&
                      !opa_inf_c && !opb_inf_c && !nan_input_c &&
                      input_zero_c;
    assign div_uf_c = divide_c && !nan_input_c &&
                      (div_by_inf_c ||
                       (!opa_zero_c && !opb_zero_c &&
                        !opa_inf_c && !opb_inf_c && input_zero_c));
    assign underflow_trigger_c = (mul_uf_c || div_uf_c) && input_zero_c;

    assign invalid_trigger_c = snan_input_c || addsub_inf_invalid_c ||
                               mul_0_by_inf_c || div_0_by_0_c ||
                               div_inf_by_inf_c;
    assign overflow_trigger_c = out_inf_trigger_c && !nan_input_c;
    assign inexact_trigger_c = ((|mantissa_in) || out_inf_trigger_c ||
                                underflow_trigger_c) && !nan_input_c;
    assign except_trigger_c = invalid_trigger_c || overflow_trigger_c ||
                              underflow_trigger_c || inexact_trigger_c;
    assign enable_trigger_c = nan_out_trigger_c || out_inf_trigger_c ||
                              underflow_trigger_c || inexact_trigger_c;

    assign nan_payload_c = opa_nan_c ? {opa[62:52], 1'b1, opa[50:0]} :
                           opb_nan_c ? {opb[62:52], 1'b1, opb[50:0]} :
                                       {11'h7ff, 1'b1, opa[50:0]};

    assign exp_2047 = 11'h7ff;
    assign exp_2046 = 11'h7fe;
    assign mantissa_max = 52'hfffffffffffff;
    assign inf_mag_c = {11'h7ff, 52'b0};
    assign max_finite_mag_c = {11'h7fe, 52'hfffffffffffff};
    assign out_inf = inf_mag_c;
    assign inf_round_down = max_finite_mag_c;

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
    assign nan_output_0 = nan_output_0_r;
    assign nan_output = nan_output_r;
    assign out_0 = out_0_r;
    assign out_1 = out_1_r;
    assign out_2 = out_2_r;

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
            snan_trigger_r <= 1'b0;

            underflow <= 1'b0;
            overflow <= 1'b0;
            inexact <= 1'b0;
            exception <= 1'b0;
            invalid <= 1'b0;
            ex_enable <= 1'b0;
            out <= 64'b0;

            nan_output_0_r <= 63'b0;
            nan_output_r <= 63'b0;
            out_0_r <= 64'b0;
            out_1_r <= 64'b0;
            out_2_r <= 64'b0;
            inf_select_d0 <= 1'b0;
            inf_down_d0 <= 1'b0;
            inf_sign_d0 <= 1'b0;
            nan_select_d0 <= 1'b0;
            nan_select_d1 <= 1'b0;
            nan_sign_d0 <= 1'b0;
            nan_sign_d1 <= 1'b0;
        end else if (enable) begin
            in_et_zero_r <= input_zero_c;
            opa_et_zero_r <= opa_zero_c;
            opb_et_zero_r <= opb_zero_c;
            input_et_zero_r <= input_zero_c;
            add_r <= add_c;
            subtract_r <= subtract_c;
            multiply_r <= multiply_c;
            divide_r <= divide_c;
            opa_qnan_r <= opa_qnan_c;
            opb_qnan_r <= opb_qnan_c;
            opa_snan_r <= opa_snan_c;
            opb_snan_r <= opb_snan_c;
            opa_pos_inf_r <= opa_pos_inf_c;
            opb_pos_inf_r <= opb_pos_inf_c;
            opa_neg_inf_r <= opa_neg_inf_c;
            opb_neg_inf_r <= opb_neg_inf_c;
            opa_inf_r <= opa_inf_c;
            opb_inf_r <= opb_inf_c;
            nan_input_r <= nan_input_c;
            snan_input_r <= snan_input_c;
            a_nan_r <= a_nan_c;
            div_by_0_r <= div_by_0_c;
            div_0_by_0_r <= div_0_by_0_c;
            div_inf_by_inf_r <= div_inf_by_inf_c;
            div_by_inf_r <= div_by_inf_c;
            mul_0_by_inf_r <= mul_0_by_inf_c;
            mul_inf_r <= mul_inf_c;
            div_inf_r <= div_inf_c;
            add_inf_r <= add_inf_c;
            sub_inf_r <= sub_inf_c;
            addsub_inf_invalid_r <= addsub_inf_invalid_c;
            addsub_inf_r <= addsub_inf_c;
            out_inf_trigger_r <= out_inf_trigger_c;
            out_pos_inf_r <= out_pos_inf_c;
            out_neg_inf_r <= out_neg_inf_c;
            round_nearest_r <= round_nearest_c;
            round_to_zero_r <= round_to_zero_c;
            round_to_pos_inf_r <= round_to_pos_inf_c;
            round_to_neg_inf_r <= round_to_neg_inf_c;
            inf_round_down_trigger_r <= inf_round_down_trigger_c;
            mul_uf_r <= mul_uf_c;
            div_uf_r <= div_uf_c;
            underflow_trigger_r <= underflow_trigger_c;
            invalid_trigger_r <= invalid_trigger_c;
            overflow_trigger_r <= overflow_trigger_c;
            inexact_trigger_r <= inexact_trigger_c;
            except_trigger_r <= except_trigger_c;
            enable_trigger_r <= enable_trigger_c;
            nan_out_trigger_r <= nan_out_trigger_c;
            snan_trigger_r <= snan_input_c;

            underflow <= underflow_trigger_c;
            overflow <= overflow_trigger_c;
            inexact <= inexact_trigger_c;
            exception <= except_trigger_c;
            invalid <= invalid_trigger_c;
            ex_enable <= enable_trigger_c;

            out_0_r <= underflow_trigger_c ?
                       {in_except[63], 63'b0} : in_except;
            inf_select_d0 <= out_inf_trigger_c;
            inf_down_d0 <= inf_round_down_trigger_c;
            inf_sign_d0 <= in_except[63];
            nan_output_0_r <= nan_payload_c;
            nan_select_d0 <= nan_out_trigger_c;
            nan_sign_d0 <= in_except[63];

            out_1_r <= inf_select_d0 ?
                       {inf_sign_d0,
                        (inf_down_d0 ? max_finite_mag_c : inf_mag_c)} :
                       out_0_r;
            nan_output_r <= nan_output_0_r;
            nan_select_d1 <= nan_select_d0;
            nan_sign_d1 <= nan_sign_d0;

            out_2_r <= nan_select_d1 ?
                       {nan_sign_d1, nan_output_r} : out_1_r;
            out <= out_2_r;
        end
    end

endmodule