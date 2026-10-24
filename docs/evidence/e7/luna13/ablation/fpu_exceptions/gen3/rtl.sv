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

    localparam [10:0] EXP_INF = 11'h7ff;
    localparam [10:0] EXP_MAX = 11'h7fe;
    localparam [51:0] FRAC_MAX = 52'hfffffffffffff;
    localparam [51:0] QUIET_BIT = 52'h8000000000000;

    wire [62:0] INF_MAG = {EXP_INF, 52'b0};
    wire [62:0] MAX_MAG = {EXP_MAX, FRAC_MAX};

    wire d_in_et_zero;
    wire d_input_et_zero;
    wire d_opa_et_zero;
    wire d_opb_et_zero;

    wire d_add;
    wire d_subtract;
    wire d_multiply;
    wire d_divide;

    wire d_opa_nan;
    wire d_opb_nan;
    wire d_opa_qnan;
    wire d_opb_qnan;
    wire d_opa_snan;
    wire d_opb_snan;
    wire d_opa_pos_inf;
    wire d_opb_pos_inf;
    wire d_opa_neg_inf;
    wire d_opb_neg_inf;
    wire d_opa_inf;
    wire d_opb_inf;

    wire d_nan_input;
    wire d_snan_input;
    wire d_a_nan;
    wire d_div_by_0;
    wire d_div_0_by_0;
    wire d_div_inf_by_inf;
    wire d_div_by_inf;
    wire d_mul_0_by_inf;
    wire d_mul_inf;
    wire d_div_inf;
    wire d_add_inf;
    wire d_sub_inf;
    wire d_addsub_inf_invalid;
    wire d_addsub_inf;
    wire d_out_inf_trigger;
    wire d_out_pos_inf;
    wire d_out_neg_inf;
    wire d_round_nearest;
    wire d_round_to_zero;
    wire d_round_to_pos_inf;
    wire d_round_to_neg_inf;
    wire d_inf_round_down_trigger;
    wire d_mul_uf;
    wire d_div_uf;
    wire d_underflow_trigger;
    wire d_invalid_trigger;
    wire d_overflow_trigger;
    wire d_inexact_trigger;
    wire d_except_trigger;
    wire d_enable_trigger;
    wire d_nan_out_trigger;
    wire d_snan_trigger;

    wire [51:0] nan_frac;
    wire [62:0] nan_payload;
    wire [63:0] output_stage0;
    wire [63:0] output_stage1;
    wire [63:0] output_stage2;

    assign d_in_et_zero    = (in_except[62:0] == 63'b0);
    assign d_input_et_zero = (in_except == 64'b0);
    assign d_opa_et_zero   = (opa[62:0] == 63'b0);
    assign d_opb_et_zero   = (opb[62:0] == 63'b0);

    assign d_add      = (fpu_op == 3'b000);
    assign d_subtract = (fpu_op == 3'b001);
    assign d_multiply = (fpu_op == 3'b010);
    assign d_divide   = (fpu_op == 3'b011);

    assign d_opa_nan = (opa[62:52] == 11'h7ff) && (opa[51:0] != 52'b0);
    assign d_opb_nan = (opb[62:52] == 11'h7ff) && (opb[51:0] != 52'b0);
    assign d_opa_qnan = d_opa_nan && opa[51];
    assign d_opb_qnan = d_opb_nan && opb[51];
    assign d_opa_snan = d_opa_nan && !opa[51];
    assign d_opb_snan = d_opb_nan && !opb[51];

    assign d_opa_inf = (opa[62:52] == 11'h7ff) && (opa[51:0] == 52'b0);
    assign d_opb_inf = (opb[62:52] == 11'h7ff) && (opb[51:0] == 52'b0);
    assign d_opa_pos_inf = d_opa_inf && !opa[63];
    assign d_opb_pos_inf = d_opb_inf && !opb[63];
    assign d_opa_neg_inf = d_opa_inf && opa[63];
    assign d_opb_neg_inf = d_opb_inf && opb[63];

    assign d_nan_input = d_opa_nan || d_opb_nan;
    assign d_snan_input = d_opa_snan || d_opb_snan;

    assign d_div_0_by_0 = d_divide && d_opa_et_zero && d_opb_et_zero;
    assign d_div_inf_by_inf = d_divide && d_opa_inf && d_opb_inf;
    assign d_div_by_0 = d_divide && d_opb_et_zero && !d_opa_et_zero
                      && !d_nan_input;
    assign d_div_by_inf = d_divide && d_opb_inf && !d_opa_inf;

    assign d_mul_0_by_inf = d_multiply &&
                           ((d_opa_et_zero && d_opb_inf) ||
                            (d_opb_et_zero && d_opa_inf));
    assign d_mul_inf = d_multiply && (d_opa_inf || d_opb_inf)
                     && !d_mul_0_by_inf;

    assign d_div_inf = d_divide && !d_div_0_by_0 && !d_div_inf_by_inf &&
                      ((d_opa_inf && !d_opb_inf) || d_div_by_0);

    assign d_addsub_inf_invalid =
        (d_add &&
         ((d_opa_pos_inf && d_opb_neg_inf) ||
          (d_opa_neg_inf && d_opb_pos_inf))) ||
        (d_subtract &&
         ((d_opa_pos_inf && d_opb_pos_inf) ||
          (d_opa_neg_inf && d_opb_neg_inf)));

    assign d_add_inf = d_add && (d_opa_inf || d_opb_inf)
                     && !d_addsub_inf_invalid;
    assign d_sub_inf = d_subtract && (d_opa_inf || d_opb_inf)
                     && !d_addsub_inf_invalid;
    assign d_addsub_inf = d_add_inf || d_sub_inf;

    assign d_out_inf_trigger = d_mul_inf || d_div_inf || d_addsub_inf ||
                               d_div_by_0 || (exponent_in > 12'd2046);
    assign d_out_pos_inf = d_out_inf_trigger && !in_except[63];
    assign d_out_neg_inf = d_out_inf_trigger && in_except[63];

    assign d_round_nearest   = (rmode == 2'b00);
    assign d_round_to_zero   = (rmode == 2'b01);
    assign d_round_to_pos_inf = (rmode == 2'b10);
    assign d_round_to_neg_inf = (rmode == 2'b11);

    assign d_inf_round_down_trigger =
        (d_out_pos_inf && (d_round_to_zero || d_round_to_neg_inf)) ||
        (d_out_neg_inf && (d_round_to_zero || d_round_to_pos_inf));

    assign d_mul_uf = d_multiply && !d_opa_et_zero && !d_opb_et_zero &&
                      !d_opa_inf && !d_opb_inf && d_in_et_zero &&
                      !d_nan_input;

    assign d_div_uf = !d_nan_input &&
                      ((d_div_by_inf && !d_opa_et_zero) ||
                       (d_divide && !d_opa_et_zero && !d_opb_et_zero &&
                        !d_opa_inf && !d_opb_inf && d_in_et_zero));

    assign d_underflow_trigger = d_mul_uf || d_div_uf;

    assign d_invalid_trigger = d_snan_input || d_addsub_inf_invalid ||
                               d_mul_0_by_inf || d_div_0_by_0 ||
                               d_div_inf_by_inf;
    assign d_overflow_trigger = d_out_inf_trigger && !d_nan_input;
    assign d_inexact_trigger = !d_nan_input &&
                              ((|mantissa_in) || d_out_inf_trigger ||
                               d_underflow_trigger);
    assign d_except_trigger = d_invalid_trigger || d_overflow_trigger ||
                              d_underflow_trigger || d_inexact_trigger;
    assign d_nan_out_trigger = d_nan_input || d_invalid_trigger;
    assign d_a_nan = d_nan_out_trigger;
    assign d_snan_trigger = d_snan_input;
    assign d_enable_trigger = d_nan_out_trigger || d_out_inf_trigger ||
                              d_underflow_trigger || d_inexact_trigger;

    assign nan_frac = d_opa_nan ? (opa[51:0] | QUIET_BIT) :
                      d_opb_nan ? (opb[51:0] | QUIET_BIT) :
                                  (opa[51:0] | QUIET_BIT);
    assign nan_payload = {EXP_INF, nan_frac};

    assign output_stage0 = (d_underflow_trigger && d_in_et_zero) ?
                           {in_except[63], 63'b0} : in_except;

    assign output_stage1 = d_out_inf_trigger ?
                           {in_except[63],
                            (d_inf_round_down_trigger ? MAX_MAG : INF_MAG)} :
                           output_stage0;

    assign output_stage2 = d_nan_out_trigger ?
                           {in_except[63], nan_payload} : output_stage1;

    reg in_et_zero_r;
    reg opa_et_zero_r;
    reg opb_et_zero_r;
    reg input_et_zero_r;
    reg add_r;
    reg subtract_r;
    reg multiply_r;
    reg divide_r;
    reg opa_qnan_r;
    reg opb_qnan_r;
    reg opa_snan_r;
    reg opb_snan_r;
    reg opa_pos_inf_r;
    reg opb_pos_inf_r;
    reg opa_neg_inf_r;
    reg opb_neg_inf_r;
    reg opa_inf_r;
    reg opb_inf_r;
    reg nan_input_r;
    reg snan_input_r;
    reg a_nan_r;
    reg div_by_0_r;
    reg div_0_by_0_r;
    reg div_inf_by_inf_r;
    reg div_by_inf_r;
    reg mul_0_by_inf_r;
    reg mul_inf_r;
    reg div_inf_r;
    reg add_inf_r;
    reg sub_inf_r;
    reg addsub_inf_invalid_r;
    reg addsub_inf_r;
    reg out_inf_trigger_r;
    reg out_pos_inf_r;
    reg out_neg_inf_r;
    reg round_nearest_r;
    reg round_to_zero_r;
    reg round_to_pos_inf_r;
    reg round_to_neg_inf_r;
    reg inf_round_down_trigger_r;
    reg mul_uf_r;
    reg div_uf_r;
    reg underflow_trigger_r;
    reg invalid_trigger_r;
    reg overflow_trigger_r;
    reg inexact_trigger_r;
    reg except_trigger_r;
    reg enable_trigger_r;
    reg nan_out_trigger_r;
    reg snan_trigger_r;
    reg [62:0] nan_output_0_r;
    reg [62:0] nan_output_r;
    reg [63:0] out_0_r;
    reg [63:0] out_1_r;
    reg [63:0] out_2_r;

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

    assign exp_2047 = EXP_INF;
    assign exp_2046 = EXP_MAX;
    assign mantissa_max = FRAC_MAX;
    assign inf_round_down = MAX_MAG;
    assign out_inf = INF_MAG;
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
            in_et_zero_r <= d_in_et_zero;
            opa_et_zero_r <= d_opa_et_zero;
            opb_et_zero_r <= d_opb_et_zero;
            input_et_zero_r <= d_input_et_zero;
            add_r <= d_add;
            subtract_r <= d_subtract;
            multiply_r <= d_multiply;
            divide_r <= d_divide;
            opa_qnan_r <= d_opa_qnan;
            opb_qnan_r <= d_opb_qnan;
            opa_snan_r <= d_opa_snan;
            opb_snan_r <= d_opb_snan;
            opa_pos_inf_r <= d_opa_pos_inf;
            opb_pos_inf_r <= d_opb_pos_inf;
            opa_neg_inf_r <= d_opa_neg_inf;
            opb_neg_inf_r <= d_opb_neg_inf;
            opa_inf_r <= d_opa_inf;
            opb_inf_r <= d_opb_inf;
            nan_input_r <= d_nan_input;
            snan_input_r <= d_snan_input;
            a_nan_r <= d_a_nan;
            div_by_0_r <= d_div_by_0;
            div_0_by_0_r <= d_div_0_by_0;
            div_inf_by_inf_r <= d_div_inf_by_inf;
            div_by_inf_r <= d_div_by_inf;
            mul_0_by_inf_r <= d_mul_0_by_inf;
            mul_inf_r <= d_mul_inf;
            div_inf_r <= d_div_inf;
            add_inf_r <= d_add_inf;
            sub_inf_r <= d_sub_inf;
            addsub_inf_invalid_r <= d_addsub_inf_invalid;
            addsub_inf_r <= d_addsub_inf;
            out_inf_trigger_r <= d_out_inf_trigger;
            out_pos_inf_r <= d_out_pos_inf;
            out_neg_inf_r <= d_out_neg_inf;
            round_nearest_r <= d_round_nearest;
            round_to_zero_r <= d_round_to_zero;
            round_to_pos_inf_r <= d_round_to_pos_inf;
            round_to_neg_inf_r <= d_round_to_neg_inf;
            inf_round_down_trigger_r <= d_inf_round_down_trigger;
            mul_uf_r <= d_mul_uf;
            div_uf_r <= d_div_uf;
            underflow_trigger_r <= d_underflow_trigger;
            invalid_trigger_r <= d_invalid_trigger;
            overflow_trigger_r <= d_overflow_trigger;
            inexact_trigger_r <= d_inexact_trigger;
            except_trigger_r <= d_except_trigger;
            enable_trigger_r <= d_enable_trigger;
            nan_out_trigger_r <= d_nan_out_trigger;
            snan_trigger_r <= d_snan_trigger;

            underflow <= d_underflow_trigger;
            overflow <= d_overflow_trigger;
            inexact <= d_inexact_trigger;
            invalid <= d_invalid_trigger;
            exception <= d_except_trigger;
            ex_enable <= d_enable_trigger;

            nan_output_0_r <= nan_payload;
            nan_output_r <= nan_payload;
            out_0_r <= output_stage0;
            out_1_r <= output_stage1;
            out_2_r <= output_stage2;
            out <= output_stage2;
        end
    end

endmodule