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

    wire opa_zero_w;
    wire opb_zero_w;
    wire in_zero_w;
    wire opa_nan_w;
    wire opb_nan_w;
    wire opa_snan_w;
    wire opb_snan_w;
    wire opa_inf_w;
    wire opb_inf_w;
    wire opa_pos_inf_w;
    wire opb_pos_inf_w;
    wire opa_neg_inf_w;
    wire opb_neg_inf_w;
    wire nan_input_w;
    wire snan_input_w;

    wire add_w;
    wire subtract_w;
    wire multiply_w;
    wire divide_w;

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
    wire a_nan_w;

    wire [51:0] nan_fraction_w;
    wire [62:0] nan_value_w;

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

    reg [62:0] nan_output0_r;
    reg [63:0] out0_r;
    reg [63:0] out1_r;
    reg [63:0] out2_r;

    reg inf_trigger_s0_r;
    reg inf_round_down_s0_r;
    reg inf_sign_s0_r;
    reg nan_trigger_s0_r;
    reg nan_trigger_s1_r;
    reg nan_sign_s0_r;
    reg nan_sign_s1_r;
    reg [62:0] nan_output_s1_r;

    assign opa_zero_w = (opa[62:0] == 63'b0);
    assign opb_zero_w = (opb[62:0] == 63'b0);
    assign in_zero_w = (in_except[62:0] == 63'b0);

    assign opa_nan_w = (&opa[62:52]) && (|opa[51:0]);
    assign opb_nan_w = (&opb[62:52]) && (|opb[51:0]);
    assign opa_snan_w = opa_nan_w && !opa[51];
    assign opb_snan_w = opb_nan_w && !opb[51];

    assign opa_inf_w = (&opa[62:52]) && !(|opa[51:0]);
    assign opb_inf_w = (&opb[62:52]) && !(|opb[51:0]);
    assign opa_pos_inf_w = opa_inf_w && !opa[63];
    assign opb_pos_inf_w = opb_inf_w && !opb[63];
    assign opa_neg_inf_w = opa_inf_w && opa[63];
    assign opb_neg_inf_w = opb_inf_w && opb[63];

    assign nan_input_w = opa_nan_w || opb_nan_w;
    assign snan_input_w = opa_snan_w || opb_snan_w;

    assign add_w      = (fpu_op == 3'b000);
    assign subtract_w = (fpu_op == 3'b001);
    assign multiply_w = (fpu_op == 3'b010);
    assign divide_w   = (fpu_op == 3'b011);

    assign div_by_0_w = divide_w && opb_zero_w && !opa_zero_w &&
                        !opa_inf_w && !opa_nan_w;
    assign div_0_by_0_w = divide_w && opa_zero_w && opb_zero_w;
    assign div_inf_by_inf_w = divide_w && opa_inf_w && opb_inf_w;
    assign div_by_inf_w = divide_w && opb_inf_w;

    assign mul_0_by_inf_w = multiply_w &&
                             ((opa_zero_w && opb_inf_w) ||
                              (opa_inf_w && opb_zero_w));

    assign mul_inf_w = multiply_w && (opa_inf_w || opb_inf_w) &&
                       !mul_0_by_inf_w && !nan_input_w;

    assign div_inf_w = divide_w &&
                       ((opa_inf_w && !opb_inf_w) || div_by_0_w) &&
                       !div_0_by_0_w && !div_inf_by_inf_w &&
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

    assign out_inf_trigger_w = mul_inf_w || div_inf_w || addsub_inf_w ||
                               div_by_0_w || (exponent_in > 12'd2046);

    assign out_pos_inf_w = out_inf_trigger_w && !in_except[63];
    assign out_neg_inf_w = out_inf_trigger_w && in_except[63];

    assign round_nearest_w   = (rmode == 2'b00);
    assign round_to_zero_w   = (rmode == 2'b01);
    assign round_to_pos_inf_w = (rmode == 2'b10);
    assign round_to_neg_inf_w = (rmode == 2'b11);

    assign inf_round_down_trigger_w =
        (out_pos_inf_w && (round_to_zero_w || round_to_neg_inf_w)) ||
        (out_neg_inf_w && (round_to_zero_w || round_to_pos_inf_w));

    assign mul_uf_w = multiply_w && !opa_zero_w && !opb_zero_w &&
                      !opa_inf_w && !opb_inf_w && !nan_input_w &&
                      in_zero_w;

    assign div_uf_w =
        (div_by_inf_w && !opa_inf_w && !nan_input_w) ||
        (divide_w && !opa_zero_w && !opb_zero_w &&
         !opa_inf_w && !opb_inf_w && !nan_input_w && in_zero_w);

    assign underflow_trigger_w = mul_uf_w || div_uf_w;

    assign invalid_trigger_w = snan_input_w || addsub_inf_invalid_w ||
                               mul_0_by_inf_w || div_0_by_0_w ||
                               div_inf_by_inf_w;

    assign overflow_trigger_w = out_inf_trigger_w && !nan_input_w;

    assign inexact_trigger_w = ((|mantissa_in) || out_inf_trigger_w ||
                                underflow_trigger_w) && !nan_input_w;

    assign except_trigger_w = invalid_trigger_w || overflow_trigger_w ||
                              underflow_trigger_w || inexact_trigger_w;

    assign nan_out_trigger_w = nan_input_w || invalid_trigger_w;
    assign enable_trigger_w = except_trigger_w || nan_out_trigger_w;
    assign snan_trigger_w = snan_input_w;

    assign a_nan_w = opa_nan_w || (!nan_input_w && invalid_trigger_w);
    assign nan_fraction_w = a_nan_w ? {1'b1, opa[50:0]} :
                                      {1'b1, opb[50:0]};
    assign nan_value_w = {11'b11111111111, nan_fraction_w};

    assign exp_2047 = 11'b11111111111;
    assign exp_2046 = 11'b11111111110;
    assign mantissa_max = {52{1'b1}};
    assign inf_round_down = {11'b11111111110, {52{1'b1}}};
    assign out_inf = {11'b11111111111, 52'b0};

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

    assign nan_output_0 = nan_output0_r;
    assign nan_output = nan_value_w;
    assign out_0 = out0_r;
    assign out_1 = out1_r;
    assign out_2 = out2_r;
    assign out = out2_r;

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

            nan_output0_r <= 63'b0;
            out0_r <= 64'b0;
            out1_r <= 64'b0;
            out2_r <= 64'b0;

            inf_trigger_s0_r <= 1'b0;
            inf_round_down_s0_r <= 1'b0;
            inf_sign_s0_r <= 1'b0;
            nan_trigger_s0_r <= 1'b0;
            nan_trigger_s1_r <= 1'b0;
            nan_sign_s0_r <= 1'b0;
            nan_sign_s1_r <= 1'b0;
            nan_output_s1_r <= 63'b0;
        end else if (enable) begin
            in_et_zero_r <= in_zero_w;
            opa_et_zero_r <= opa_zero_w;
            opb_et_zero_r <= opb_zero_w;
            input_et_zero_r <= in_zero_w;

            add_r <= add_w;
            subtract_r <= subtract_w;
            multiply_r <= multiply_w;
            divide_r <= divide_w;

            opa_qnan_r <= opa_nan_w && opa[51];
            opb_qnan_r <= opb_nan_w && opb[51];
            opa_snan_r <= opa_snan_w;
            opb_snan_r <= opb_snan_w;
            opa_pos_inf_r <= opa_pos_inf_w;
            opb_pos_inf_r <= opb_pos_inf_w;
            opa_neg_inf_r <= opa_neg_inf_w;
            opb_neg_inf_r <= opb_neg_inf_w;
            opa_inf_r <= opa_inf_w;
            opb_inf_r <= opb_inf_w;
            nan_input_r <= nan_input_w;
            snan_input_r <= snan_input_w;
            a_nan_r <= a_nan_w;

            div_by_0_r <= div_by_0_w;
            div_0_by_0_r <= div_0_by_0_w;
            div_inf_by_inf_r <= div_inf_by_inf_w;
            div_by_inf_r <= div_by_inf_w;
            mul_0_by_inf_r <= mul_0_by_inf_w;
            mul_inf_r <= mul_inf_w;
            div_inf_r <= div_inf_w;
            add_inf_r <= add_inf_w;
            sub_inf_r <= sub_inf_w;
            addsub_inf_invalid_r <= addsub_inf_invalid_w;
            addsub_inf_r <= addsub_inf_w;

            out_inf_trigger_r <= out_inf_trigger_w;
            out_pos_inf_r <= out_pos_inf_w;
            out_neg_inf_r <= out_neg_inf_w;
            round_nearest_r <= round_nearest_w;
            round_to_zero_r <= round_to_zero_w;
            round_to_pos_inf_r <= round_to_pos_inf_w;
            round_to_neg_inf_r <= round_to_neg_inf_w;
            inf_round_down_trigger_r <= inf_round_down_trigger_w;

            mul_uf_r <= mul_uf_w;
            div_uf_r <= div_uf_w;
            underflow_trigger_r <= underflow_trigger_w;
            invalid_trigger_r <= invalid_trigger_w;
            overflow_trigger_r <= overflow_trigger_w;
            inexact_trigger_r <= inexact_trigger_w;
            except_trigger_r <= except_trigger_w;
            enable_trigger_r <= enable_trigger_w;
            nan_out_trigger_r <= nan_out_trigger_w;
            snan_trigger_r <= snan_trigger_w;

            underflow <= underflow_trigger_w;
            overflow <= overflow_trigger_w;
            inexact <= inexact_trigger_w;
            exception <= except_trigger_w;
            invalid <= invalid_trigger_w;
            ex_enable <= enable_trigger_w;

            // Keep the registered output at one enabled rising edge.  The
            // intermediate values represent the ordered selection stages,
            // but each stage is formed from this update's inputs rather than
            // adding extra cycles of latency.
            out0_r <= underflow_trigger_w ?
                      {in_except[63], 63'b0} : in_except;

            inf_trigger_s0_r <= out_inf_trigger_w;
            inf_round_down_s0_r <= inf_round_down_trigger_w;
            inf_sign_s0_r <= in_except[63];

            if (out_inf_trigger_w) begin
                if (inf_round_down_trigger_w)
                    out1_r <= {in_except[63], 11'b11111111110,
                               {52{1'b1}}};
                else
                    out1_r <= {in_except[63], 11'b11111111111, 52'b0};
            end else begin
                out1_r <= underflow_trigger_w ?
                          {in_except[63], 63'b0} : in_except;
            end

            nan_output0_r <= nan_value_w;
            nan_trigger_s0_r <= nan_out_trigger_w;
            nan_trigger_s1_r <= nan_out_trigger_w;
            nan_sign_s0_r <= in_except[63];
            nan_sign_s1_r <= in_except[63];
            nan_output_s1_r <= nan_value_w;

            if (nan_out_trigger_w)
                out2_r <= {in_except[63], nan_value_w};
            else if (out_inf_trigger_w) begin
                if (inf_round_down_trigger_w)
                    out2_r <= {in_except[63], 11'b11111111110,
                               {52{1'b1}}};
                else
                    out2_r <= {in_except[63], 11'b11111111111, 52'b0};
            end else begin
                out2_r <= underflow_trigger_w ?
                          {in_except[63], 63'b0} : in_except;
            end
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
