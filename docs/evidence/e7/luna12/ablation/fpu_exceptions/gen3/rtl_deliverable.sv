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

    output reg in_et_zero,
    output reg opa_et_zero,
    output reg opb_et_zero,
    output reg input_et_zero,
    output reg add,
    output reg subtract,
    output reg multiply,
    output reg divide,
    output reg opa_qnan,
    output reg opb_qnan,
    output reg opa_snan,
    output reg opb_snan,
    output reg opa_pos_inf,
    output reg opb_pos_inf,
    output reg opa_neg_inf,
    output reg opb_neg_inf,
    output reg opa_inf,
    output reg opb_inf,
    output reg nan_input,
    output reg snan_input,
    output reg a_nan,
    output reg div_by_0,
    output reg div_0_by_0,
    output reg div_inf_by_inf,
    output reg div_by_inf,
    output reg mul_0_by_inf,
    output reg mul_inf,
    output reg div_inf,
    output reg add_inf,
    output reg sub_inf,
    output reg addsub_inf_invalid,
    output reg addsub_inf,
    output reg out_inf_trigger,
    output reg out_pos_inf,
    output reg out_neg_inf,
    output reg round_nearest,
    output reg round_to_zero,
    output reg round_to_pos_inf,
    output reg round_to_neg_inf,
    output reg inf_round_down_trigger,
    output reg mul_uf,
    output reg div_uf,
    output reg underflow_trigger,
    output reg invalid_trigger,
    output reg overflow_trigger,
    output reg inexact_trigger,
    output reg except_trigger,
    output reg enable_trigger,
    output reg nan_out_trigger,
    output reg snan_trigger,
    output [10:0] exp_2047,
    output [10:0] exp_2046,
    output reg [62:0] nan_output_0,
    output reg [62:0] nan_output,
    output [51:0] mantissa_max,
    output reg [62:0] inf_round_down,
    output reg [62:0] out_inf,
    output reg [63:0] out_0,
    output reg [63:0] out_1,
    output reg [63:0] out_2
);

    wire opa_zero_w;
    wire opb_zero_w;
    wire in_zero_w;
    wire opa_nan_w;
    wire opb_nan_w;
    wire opa_qnan_w;
    wire opb_qnan_w;
    wire opa_snan_w;
    wire opb_snan_w;
    wire opa_inf_w;
    wire opb_inf_w;
    wire opa_pos_inf_w;
    wire opb_pos_inf_w;
    wire opa_neg_inf_w;
    wire opb_neg_inf_w;
    wire add_w;
    wire subtract_w;
    wire multiply_w;
    wire divide_w;
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
    wire [51:0] selected_nan_frac_w;
    wire [62:0] nan_output_w;
    wire [62:0] inf_round_down_w;
    wire [62:0] out_inf_w;
    wire [63:0] out_0_w;
    wire [63:0] out_1_w;
    wire [63:0] out_2_w;
    wire valid_inf_result_w;

    assign exp_2047 = 11'h7ff;
    assign exp_2046 = 11'h7fe;
    assign mantissa_max = 52'hfffffffffffff;

    assign opa_zero_w = (opa[62:0] == 63'b0);
    assign opb_zero_w = (opb[62:0] == 63'b0);
    assign in_zero_w = (in_except[62:0] == 63'b0);

    assign opa_nan_w = (opa[62:52] == 11'h7ff) && (|opa[51:0]);
    assign opb_nan_w = (opb[62:52] == 11'h7ff) && (|opb[51:0]);
    assign opa_qnan_w = opa_nan_w && opa[51];
    assign opb_qnan_w = opb_nan_w && opb[51];
    assign opa_snan_w = opa_nan_w && !opa[51];
    assign opb_snan_w = opb_nan_w && !opb[51];

    assign opa_inf_w = (opa[62:52] == 11'h7ff) && !(|opa[51:0]);
    assign opb_inf_w = (opb[62:52] == 11'h7ff) && !(|opb[51:0]);
    assign opa_pos_inf_w = opa_inf_w && !opa[63];
    assign opb_pos_inf_w = opb_inf_w && !opb[63];
    assign opa_neg_inf_w = opa_inf_w && opa[63];
    assign opb_neg_inf_w = opb_inf_w && opb[63];

    assign add_w = (fpu_op == 3'b000);
    assign subtract_w = (fpu_op == 3'b001);
    assign multiply_w = (fpu_op == 3'b010);
    assign divide_w = (fpu_op == 3'b011);

    assign nan_input_w = opa_nan_w || opb_nan_w;
    assign snan_input_w = opa_snan_w || opb_snan_w;
    assign a_nan_w = opa_nan_w || !opb_nan_w;

    assign div_by_0_w = divide_w && opb_zero_w && !opa_zero_w;
    assign div_0_by_0_w = divide_w && opa_zero_w && opb_zero_w;
    assign div_inf_by_inf_w = divide_w && opa_inf_w && opb_inf_w;
    assign div_by_inf_w = divide_w && opb_inf_w;

    assign mul_0_by_inf_w =
        multiply_w && ((opa_zero_w && opb_inf_w) ||
                       (opb_zero_w && opa_inf_w));
    assign mul_inf_w = multiply_w && (opa_inf_w || opb_inf_w);
    assign div_inf_w = divide_w &&
                       (opa_inf_w || opb_inf_w || div_by_0_w);

    assign add_inf_w = add_w && (opa_inf_w || opb_inf_w);
    assign sub_inf_w = subtract_w && (opa_inf_w || opb_inf_w);
    assign addsub_inf_invalid_w =
        (add_w && ((opa_pos_inf_w && opb_neg_inf_w) ||
                   (opa_neg_inf_w && opb_pos_inf_w))) ||
        (subtract_w && ((opa_pos_inf_w && opb_pos_inf_w) ||
                        (opa_neg_inf_w && opb_neg_inf_w)));
    assign addsub_inf_w =
        (add_inf_w || sub_inf_w) && !addsub_inf_invalid_w;

    assign valid_inf_result_w =
        addsub_inf_w ||
        (mul_inf_w && !mul_0_by_inf_w) ||
        (divide_w &&
         ((opa_inf_w && !opb_inf_w) || div_by_0_w));

    assign out_inf_trigger_w =
        valid_inf_result_w || div_by_0_w || (exponent_in > 12'd2046);
    assign out_pos_inf_w = out_inf_trigger_w && !in_except[63];
    assign out_neg_inf_w = out_inf_trigger_w && in_except[63];

    assign round_nearest_w = (rmode == 2'b00);
    assign round_to_zero_w = (rmode == 2'b01);
    assign round_to_pos_inf_w = (rmode == 2'b10);
    assign round_to_neg_inf_w = (rmode == 2'b11);

    assign inf_round_down_trigger_w =
        (out_pos_inf_w && (round_to_zero_w || round_to_neg_inf_w)) ||
        (out_neg_inf_w && (round_to_zero_w || round_to_pos_inf_w));

    assign mul_uf_w =
        multiply_w && !opa_zero_w && !opb_zero_w &&
        !opa_inf_w && !opb_inf_w && in_zero_w;
    assign div_uf_w =
        divide_w &&
        ((opb_inf_w && !opa_inf_w) ||
         (!opa_zero_w && !opb_zero_w && !opa_inf_w &&
          !opb_inf_w && in_zero_w));
    assign underflow_trigger_w =
        (mul_uf_w || div_uf_w) && !nan_input_w;

    assign invalid_trigger_w =
        snan_input_w || addsub_inf_invalid_w || mul_0_by_inf_w ||
        div_0_by_0_w || div_inf_by_inf_w;
    assign overflow_trigger_w = out_inf_trigger_w && !nan_input_w;
    assign inexact_trigger_w =
        ((|mantissa_in) || out_inf_trigger_w || underflow_trigger_w) &&
        !nan_input_w;
    assign except_trigger_w =
        invalid_trigger_w || overflow_trigger_w ||
        underflow_trigger_w || inexact_trigger_w;
    assign nan_out_trigger_w = nan_input_w || invalid_trigger_w;
    assign snan_trigger_w = snan_input_w;
    assign enable_trigger_w = except_trigger_w || nan_out_trigger_w;

    assign selected_nan_frac_w =
        opa_nan_w ? opa[51:0] :
        (opb_nan_w ? opb[51:0] : opa[51:0]);
    assign nan_output_w =
        {11'h7ff, (selected_nan_frac_w | 52'h8000000000000)};

    assign inf_round_down_w =
        inf_round_down_trigger_w ? {11'h7fe, 52'hfffffffffffff} : 63'b0;
    assign out_inf_w =
        inf_round_down_trigger_w ? {11'h7fe, 52'hfffffffffffff} :
                                   {11'h7ff, 52'b0};

    assign out_0_w =
        underflow_trigger_w ? {in_except[63], 63'b0} : in_except;
    assign out_1_w =
        out_inf_trigger_w ? {in_except[63], out_inf_w} : out_0_w;
    assign out_2_w =
        nan_out_trigger_w ? {in_except[63], nan_output_w} : out_1_w;

    always @(posedge clk) begin
        if (rst) begin
            out <= 64'b0;
            ex_enable <= 1'b0;
            underflow <= 1'b0;
            overflow <= 1'b0;
            inexact <= 1'b0;
            exception <= 1'b0;
            invalid <= 1'b0;

            in_et_zero <= 1'b0;
            opa_et_zero <= 1'b0;
            opb_et_zero <= 1'b0;
            input_et_zero <= 1'b0;
            add <= 1'b0;
            subtract <= 1'b0;
            multiply <= 1'b0;
            divide <= 1'b0;
            opa_qnan <= 1'b0;
            opb_qnan <= 1'b0;
            opa_snan <= 1'b0;
            opb_snan <= 1'b0;
            opa_pos_inf <= 1'b0;
            opb_pos_inf <= 1'b0;
            opa_neg_inf <= 1'b0;
            opb_neg_inf <= 1'b0;
            opa_inf <= 1'b0;
            opb_inf <= 1'b0;
            nan_input <= 1'b0;
            snan_input <= 1'b0;
            a_nan <= 1'b0;
            div_by_0 <= 1'b0;
            div_0_by_0 <= 1'b0;
            div_inf_by_inf <= 1'b0;
            div_by_inf <= 1'b0;
            mul_0_by_inf <= 1'b0;
            mul_inf <= 1'b0;
            div_inf <= 1'b0;
            add_inf <= 1'b0;
            sub_inf <= 1'b0;
            addsub_inf_invalid <= 1'b0;
            addsub_inf <= 1'b0;
            out_inf_trigger <= 1'b0;
            out_pos_inf <= 1'b0;
            out_neg_inf <= 1'b0;
            round_nearest <= 1'b0;
            round_to_zero <= 1'b0;
            round_to_pos_inf <= 1'b0;
            round_to_neg_inf <= 1'b0;
            inf_round_down_trigger <= 1'b0;
            mul_uf <= 1'b0;
            div_uf <= 1'b0;
            underflow_trigger <= 1'b0;
            invalid_trigger <= 1'b0;
            overflow_trigger <= 1'b0;
            inexact_trigger <= 1'b0;
            except_trigger <= 1'b0;
            enable_trigger <= 1'b0;
            nan_out_trigger <= 1'b0;
            snan_trigger <= 1'b0;
            nan_output_0 <= 63'b0;
            nan_output <= 63'b0;
            inf_round_down <= 63'b0;
            out_inf <= 63'b0;
            out_0 <= 64'b0;
            out_1 <= 64'b0;
            out_2 <= 64'b0;
        end else if (enable) begin
            out <= out_2_w;
            ex_enable <= enable_trigger_w;
            underflow <= underflow_trigger_w;
            overflow <= overflow_trigger_w;
            inexact <= inexact_trigger_w;
            exception <= except_trigger_w;
            invalid <= invalid_trigger_w;

            in_et_zero <= in_zero_w;
            opa_et_zero <= opa_zero_w;
            opb_et_zero <= opb_zero_w;
            input_et_zero <= in_zero_w;
            add <= add_w;
            subtract <= subtract_w;
            multiply <= multiply_w;
            divide <= divide_w;
            opa_qnan <= opa_qnan_w;
            opb_qnan <= opb_qnan_w;
            opa_snan <= opa_snan_w;
            opb_snan <= opb_snan_w;
            opa_pos_inf <= opa_pos_inf_w;
            opb_pos_inf <= opb_pos_inf_w;
            opa_neg_inf <= opa_neg_inf_w;
            opb_neg_inf <= opb_neg_inf_w;
            opa_inf <= opa_inf_w;
            opb_inf <= opb_inf_w;
            nan_input <= nan_input_w;
            snan_input <= snan_input_w;
            a_nan <= a_nan_w;
            div_by_0 <= div_by_0_w;
            div_0_by_0 <= div_0_by_0_w;
            div_inf_by_inf <= div_inf_by_inf_w;
            div_by_inf <= div_by_inf_w;
            mul_0_by_inf <= mul_0_by_inf_w;
            mul_inf <= mul_inf_w;
            div_inf <= div_inf_w;
            add_inf <= add_inf_w;
            sub_inf <= sub_inf_w;
            addsub_inf_invalid <= addsub_inf_invalid_w;
            addsub_inf <= addsub_inf_w;
            out_inf_trigger <= out_inf_trigger_w;
            out_pos_inf <= out_pos_inf_w;
            out_neg_inf <= out_neg_inf_w;
            round_nearest <= round_nearest_w;
            round_to_zero <= round_to_zero_w;
            round_to_pos_inf <= round_to_pos_inf_w;
            round_to_neg_inf <= round_to_neg_inf_w;
            inf_round_down_trigger <= inf_round_down_trigger_w;
            mul_uf <= mul_uf_w;
            div_uf <= div_uf_w;
            underflow_trigger <= underflow_trigger_w;
            invalid_trigger <= invalid_trigger_w;
            overflow_trigger <= overflow_trigger_w;
            inexact_trigger <= inexact_trigger_w;
            except_trigger <= except_trigger_w;
            enable_trigger <= enable_trigger_w;
            nan_out_trigger <= nan_out_trigger_w;
            snan_trigger <= snan_trigger_w;
            nan_output_0 <= nan_output_w;
            nan_output <= nan_output_w;
            inf_round_down <= inf_round_down_w;
            out_inf <= out_inf_w;
            out_0 <= out_0_w;
            out_1 <= out_1_w;
            out_2 <= out_2_w;
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
