module RefModule (
    input  logic [7:0] r,
    input  logic [7:0] g,
    input  logic [7:0] b,
    output logic [7:0] gray
);
    logic [15:0] sum;

    always_comb begin
        sum = (16'd77  * {8'd0, r})
            + (16'd150 * {8'd0, g})
            + (16'd29  * {8'd0, b})
            + 16'd128;
        gray = sum[15:8];
    end
endmodule

