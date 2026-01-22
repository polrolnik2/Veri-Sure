module RefModule (
    input  logic        clk,
    input  logic        reset,
    input  logic [15:0] inc,
    output logic        tick
);
    logic [15:0] acc;

    always_ff @(posedge clk) begin
        if (reset) begin
            acc <= 16'd0;
            tick <= 1'b0;
        end else begin
            logic [16:0] sum;
            sum = {1'b0, acc} + {1'b0, inc};
            acc <= sum[15:0];
            tick <= sum[16];
        end
    end
endmodule

