module RefModule (
    input  logic clk,
    input  logic reset,
    output logic clk_div
);
    localparam int unsigned DIV = 5;
    localparam int unsigned HI_LEN = (DIV + 1) / 2;  // 3 for DIV=5

    logic [2:0] cnt_p;
    logic [2:0] cnt_n;
    logic clk_p;
    logic clk_n;

    always_ff @(posedge clk) begin
        if (reset) begin
            cnt_p <= 3'd0;
            clk_p <= 1'b0;
        end else begin
            if (cnt_p == 3'd0) clk_p <= 1'b1;
            else if (cnt_p == HI_LEN[2:0]) clk_p <= 1'b0;

            if (cnt_p == (DIV-1)) cnt_p <= 3'd0;
            else cnt_p <= cnt_p + 3'd1;
        end
    end

    always_ff @(negedge clk) begin
        if (reset) begin
            cnt_n <= 3'd0;
            clk_n <= 1'b0;
        end else begin
            if (cnt_n == 3'd0) clk_n <= 1'b1;
            else if (cnt_n == HI_LEN[2:0]) clk_n <= 1'b0;

            if (cnt_n == (DIV-1)) cnt_n <= 3'd0;
            else cnt_n <= cnt_n + 3'd1;
        end
    end

    always_comb begin
        clk_div = clk_p | clk_n;
    end
endmodule

