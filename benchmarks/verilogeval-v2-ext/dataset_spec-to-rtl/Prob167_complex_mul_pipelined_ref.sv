module RefModule (
    input  logic        clk,
    input  logic        reset,
    input  logic        in_valid,
    input  logic [15:0] a_re,
    input  logic [15:0] a_im,
    input  logic [15:0] b_re,
    input  logic [15:0] b_im,
    output logic [31:0] out_re,
    output logic [31:0] out_im,
    output logic        out_valid
);
    logic [2:0] v;

    // Stage 0 regs (latched inputs)
    logic signed [15:0] a_re_s0, a_im_s0, b_re_s0, b_im_s0;

    // Stage 1 regs (partial products using 3-multiplier method)
    logic signed [31:0] p1_s1;  // a_re*b_re
    logic signed [31:0] p2_s1;  // a_im*b_im
    logic signed [33:0] p3_s1;  // (a_re+a_im)*(b_re+b_im) in wider precision

    assign out_valid = v[2];

    always_ff @(posedge clk) begin
        if (reset) begin
            v <= 3'b000;
            a_re_s0 <= '0;
            a_im_s0 <= '0;
            b_re_s0 <= '0;
            b_im_s0 <= '0;
            p1_s1 <= '0;
            p2_s1 <= '0;
            p3_s1 <= '0;
            out_re <= 32'd0;
            out_im <= 32'd0;
        end else begin
            v <= {v[1:0], in_valid};

            // Stage 0: latch inputs
            if (in_valid) begin
                a_re_s0 <= $signed(a_re);
                a_im_s0 <= $signed(a_im);
                b_re_s0 <= $signed(b_re);
                b_im_s0 <= $signed(b_im);
            end

            // Stage 1: compute partial products
            if (v[0]) begin
                logic signed [16:0] sum_a;
                logic signed [16:0] sum_b;
                sum_a = $signed(a_re_s0) + $signed(a_im_s0);
                sum_b = $signed(b_re_s0) + $signed(b_im_s0);

                p1_s1 <= $signed(a_re_s0) * $signed(b_re_s0);
                p2_s1 <= $signed(a_im_s0) * $signed(b_im_s0);
                p3_s1 <= $signed(sum_a) * $signed(sum_b);
            end

            // Stage 2: combine into output (hold outputs when not producing a valid result)
            if (v[1]) begin
                logic signed [32:0] real_ext;
                logic signed [33:0] imag_ext;

                real_ext = $signed({p1_s1[31], p1_s1}) - $signed({p2_s1[31], p2_s1});
                imag_ext = $signed(p3_s1)
                           - $signed({{2{p1_s1[31]}}, p1_s1})
                           - $signed({{2{p2_s1[31]}}, p2_s1});

                out_re <= real_ext[31:0];
                out_im <= imag_ext[31:0];
            end
        end
    end
endmodule

