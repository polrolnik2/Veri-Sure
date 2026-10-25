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

    wire in_et_zero_w;
    wire opa_et_zero_w;
    wire opb_et_zero_w;
    wire input_et_zero_w;
    wire add_w;
    wire subtract_w;
    wire multiply_w;
    wire divide_w;

    wire opa_qnan_w;
    wire opb_qnan_w;
    wire opa_snan_w;
    wire opb_snan_w;
    wire opa_pos_inf_w;
    wire opb_pos_inf_w;
    wire opa_neg_inf_w;
    wire opb_neg_inf_w;
    wire opa_inf_w;
    wire opb_inf_w;
    wire opa_nan_w;
    wire opb_nan_w;
    wire nan_input_w;
    wire snan_input_w;
    wire a_nan_w;

    wire div_by_0_w;
    wire div_0_by_0_w;
    wire div_inf_by_inf_w;
    wire div_by_inf_w;
    wire mul_0_by_inf_w;
    wire mul_inf_w;
    wire div_inf_w;
    wire add_inf_w;
    wire sub_inf_w;
    wire addsub_inf_invalid_w;
    wire addsub_inf_w;

    wire out_inf_trigger_w;
    wire out_pos_inf_w;
    wire out_neg_inf_w;
    wire round_nearest_w;
    wire round_to_zero_w;
    wire round_to_pos_inf_w;
    wire round_to_neg_inf_w;
    wire inf_round_down_trigger_w;
    wire mul_uf_w;
    wire div_uf_w;
    wire underflow_trigger_w;
    wire invalid_trigger_w;
    wire overflow_trigger_w;
    wire inexact_trigger_w;
    wire except_trigger_w;
    wire enable_trigger_w;
    wire nan_out_trigger_w;
    wire snan_trigger_w;

    wire [10:0] exp_2047_c;
    wire [10:0] exp_2046_c;
    wire [51:0] mantissa_max_c;
    wire [62:0] inf_round_down_c;
    wire [62:0] out_inf_c;
    wire [62:0] nan_payload_w;
    wire [62:0] nan_output_0_w;
    wire [62:0] nan_output_w;
    wire [63:0] out_0_w;
    wire [63:0] out_1_w;
    wire [63:0] out_2_w;
    wire [63:0] inf_result_w;

    assign exp_2047_c = 11'h7ff;
    assign exp_2046_c = 11'h7fe;
    assign mantissa_max_c = 52'hfffffffffffff;
    assign inf_round_down_c = {exp_2046_c, mantissa_max_c};
    assign out_inf_c = {exp_2047_c, 52'b0};

    assign exp_2047 = exp_2047_c;
    assign exp_2046 = exp_2046_c;
    assign mantissa_max = mantissa_max_c;
    assign inf_round_down = inf_round_down_c;
    assign out_inf = out_inf_c;

    assign in_et_zero_w = (in_except[62:0] == 63'b0);
    assign opa_et_zero_w = (opa[62:0] == 63'b0);
    assign opb_et_zero_w = (opb[62:0] == 63'b0);
    assign input_et_zero_w = opa_et_zero_w | opb_et_zero_w;

    assign add_w      = (fpu_op == 3'b000);
    assign subtract_w = (fpu_op == 3'b001);
    assign multiply_w = (fpu_op == 3'b010);
    assign divide_w   = (fpu_op == 3'b011);

    assign opa_qnan_w = (opa[62:52] == 11'h7ff) &&
                        opa[51];
    assign opb_qnan_w = (opb[62:52] == 11'h7ff) &&
                        opb[51];
    assign opa_snan_w = (opa[62:52] == 11'h7ff) &&
                        !opa[51] && (opa[50:0] != 51'b0);
    assign opb_snan_w = (opb[62:52] == 11'h7ff) &&
                        !opb[51] && (opb[50:0] != 51'b0);

    assign opa_pos_inf_w = (opa[62:52] == 11'h7ff) &&
                           (opa[51:0] == 52'b0) && !opa[63];
    assign opb_pos_inf_w = (opb[62:52] == 11'h7ff) &&
                           (opb[51:0] == 52'b0) && !opb[63];
    assign opa_neg_inf_w = (opa[62:52] == 11'h7ff) &&
                           (opa[51:0] == 52'b0) && opa[63];
    assign opb_neg_inf_w = (opb[62:52] == 11'h7ff) &&
                           (opb[51:0] == 52'b0) && opb[63];
    assign opa_inf_w = opa_pos_inf_w | opa_neg_inf_w;
    assign opb_inf_w = opb_pos_inf_w | opb_neg_inf_w;

    assign opa_nan_w = (opa[62:52] == 11'h7ff) &&
                       (opa[51:0] != 52'b0);
    assign opb_nan_w = (opb[62:52] == 11'h7ff) &&
                       (opb[51:0] != 52'b0);
    assign nan_input_w = opa_nan_w | opb_nan_w;
    assign snan_input_w = opa_snan_w | opb_snan_w;
    assign a_nan_w = opa_nan_w;

    assign div_by_0_w = divide_w && opb_et_zero_w && !opa_et_zero_w;
    assign div_0_by_0_w = divide_w && opa_et_zero_w && opb_et_zero_w;
    assign div_inf_by_inf_w = divide_w && opa_inf_w && opb_inf_w;
    assign div_by_inf_w = divide_w && opb_inf_w;

    assign mul_0_by_inf_w = multiply_w &&
                            ((opa_et_zero_w && opb_inf_w) ||
                             (opa_inf_w && opb_et_zero_w));
    assign mul_inf_w = multiply_w && (opa_inf_w || opb_inf_w) &&
                       !mul_0_by_inf_w && !nan_input_w;

    assign div_inf_w = divide_w && opa_inf_w && !opb_inf_w &&
                       !nan_input_w;

    assign addsub_inf_invalid_w =
        (add_w &&
         ((opa_pos_inf_w && opb_neg_inf_w) ||
          (opa_neg_inf_w && opb_pos_inf_w))) ||
        (subtract_w &&
         ((opa_pos_inf_w && opb_pos_inf_w) ||
          (opa_neg_inf_w && opb_neg_inf_w)));

    assign add_inf_w = add_w && (opa_inf_w || opb_inf_w) &&
                       !addsub_inf_invalid_w && !nan_input_w;
    assign sub_inf_w = subtract_w && (opa_inf_w || opb_inf_w) &&
                       !addsub_inf_invalid_w && !nan_input_w;
    assign addsub_inf_w = add_inf_w || sub_inf_w;

    assign round_nearest_w = (rmode == 2'b00);
    assign round_to_zero_w = (rmode == 2'b01);
    assign round_to_pos_inf_w = (rmode == 2'b10);
    assign round_to_neg_inf_w = (rmode == 2'b11);

    assign out_inf_trigger_w =
        mul_inf_w || div_inf_w || addsub_inf_w || div_by_0_w ||
        (exponent_in > 12'd2046);

    assign out_pos_inf_w = out_inf_trigger_w && !in_except[63];
    assign out_neg_inf_w = out_inf_trigger_w && in_except[63];

    assign inf_round_down_trigger_w =
        (out_pos_inf_w && (round_to_zero_w || round_to_neg_inf_w)) ||
        (out_neg_inf_w && (round_to_zero_w || round_to_pos_inf_w));

    assign mul_uf_w = multiply_w &&
                      !opa_et_zero_w && !opb_et_zero_w &&
                      !opa_inf_w && !opb_inf_w && !nan_input_w &&
                      in_et_zero_w;

    assign div_uf_w =
        (div_by_inf_w && !opa_et_zero_w && !opa_inf_w &&
         !opa_nan_w) ||
        (divide_w && !opa_et_zero_w && !opb_et_zero_w &&
         !opa_inf_w && !opb_inf_w && !nan_input_w && in_et_zero_w);

    assign underflow_trigger_w = mul_uf_w || div_uf_w;

    assign invalid_trigger_w =
        snan_input_w || addsub_inf_invalid_w || mul_0_by_inf_w ||
        div_0_by_0_w || div_inf_by_inf_w;

    assign overflow_trigger_w = out_inf_trigger_w && !nan_input_w;
    assign inexact_trigger_w =
        ((mantissa_in != 2'b00) || out_inf_trigger_w ||
         underflow_trigger_w) && !nan_input_w;
    assign except_trigger_w =
        invalid_trigger_w || overflow_trigger_w ||
        underflow_trigger_w || inexact_trigger_w;
    assign nan_out_trigger_w = nan_input_w || invalid_trigger_w;
    assign snan_trigger_w = snan_input_w;
    assign enable_trigger_w = nan_out_trigger_w || except_trigger_w;

    assign nan_payload_w =
        opa_nan_w ? {opa[62:52], 1'b1, opa[50:0]} :
        opb_nan_w ? {opb[62:52], 1'b1, opb[50:0]} :
                    {exp_2047_c, 1'b1, opa[50:0]};

    assign nan_output_0_w = nan_payload_w;
    assign nan_output_w = nan_payload_w;

    assign out_0_w = underflow_trigger_w ?
                     {in_except[63], 63'b0} : in_except;

    assign inf_result_w = inf_round_down_trigger_w ?
                          {in_except[63], exp_2046_c, mantissa_max_c} :
                          {in_except[63], exp_2047_c, 52'b0};

    assign out_1_w = out_inf_trigger_w ? inf_result_w : out_0_w;
    assign out_2_w = nan_out_trigger_w ?
                     {in_except[63], nan_payload_w} : out_1_w;

    assign in_et_zero = in_et_zero_w;
    assign opa_et_zero = opa_et_zero_w;
    assign opb_et_zero = opb_et_zero_w;
    assign input_et_zero = input_et_zero_w;
    assign add = add_w;
    assign subtract = subtract_w;
    assign multiply = multiply_w;
    assign divide = divide_w;
    assign opa_qnan = opa_qnan_w;
    assign opb_qnan = opb_qnan_w;
    assign opa_snan = opa_snan_w;
    assign opb_snan = opb_snan_w;
    assign opa_pos_inf = opa_pos_inf_w;
    assign opb_pos_inf = opb_pos_inf_w;
    assign opa_neg_inf = opa_neg_inf_w;
    assign opb_neg_inf = opb_neg_inf_w;
    assign opa_inf = opa_inf_w;
    assign opb_inf = opb_inf_w;
    assign nan_input = nan_input_w;
    assign snan_input = snan_input_w;
    assign a_nan = a_nan_w;
    assign div_by_0 = div_by_0_w;
    assign div_0_by_0 = div_0_by_0_w;
    assign div_inf_by_inf = div_inf_by_inf_w;
    assign div_by_inf = div_by_inf_w;
    assign mul_0_by_inf = mul_0_by_inf_w;
    assign mul_inf = mul_inf_w;
    assign div_inf = div_inf_w;
    assign add_inf = add_inf_w;
    assign sub_inf = sub_inf_w;
    assign addsub_inf_invalid = addsub_inf_invalid_w;
    assign addsub_inf = addsub_inf_w;
    assign out_inf_trigger = out_inf_trigger_w;
    assign out_pos_inf = out_pos_inf_w;
    assign out_neg_inf = out_neg_inf_w;
    assign round_nearest = round_nearest_w;
    assign round_to_zero = round_to_zero_w;
    assign round_to_pos_inf = round_to_pos_inf_w;
    assign round_to_neg_inf = round_to_neg_inf_w;
    assign inf_round_down_trigger = inf_round_down_trigger_w;
    assign mul_uf = mul_uf_w;
    assign div_uf = div_uf_w;
    assign underflow_trigger = underflow_trigger_w;
    assign invalid_trigger = invalid_trigger_w;
    assign overflow_trigger = overflow_trigger_w;
    assign inexact_trigger = inexact_trigger_w;
    assign except_trigger = except_trigger_w;
    assign enable_trigger = enable_trigger_w;
    assign nan_out_trigger = nan_out_trigger_w;
    assign snan_trigger = snan_trigger_w;

    assign nan_output_0 = nan_output_0_w;
    assign nan_output = nan_output_w;
    assign out_0 = out_0_w;
    assign out_1 = out_1_w;
    assign out_2 = out_2_w;

    always @(posedge clk) begin
        if (rst) begin
            out       <= 64'b0;
            ex_enable <= 1'b0;
            underflow <= 1'b0;
            overflow  <= 1'b0;
            inexact   <= 1'b0;
            exception <= 1'b0;
            invalid   <= 1'b0;
        end else if (enable) begin
            out       <= out_2_w;
            ex_enable <= enable_trigger_w;
            underflow <= underflow_trigger_w;
            overflow  <= overflow_trigger_w;
            inexact   <= inexact_trigger_w;
            exception <= except_trigger_w;
            invalid   <= invalid_trigger_w;
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
