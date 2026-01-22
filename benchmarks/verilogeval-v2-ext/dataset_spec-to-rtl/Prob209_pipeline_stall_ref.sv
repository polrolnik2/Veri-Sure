module RefModule (
    input  logic        clk,
    input  logic        reset,
    input  logic        stall,
    input  logic        valid_in,
    input  logic [15:0] a,
    input  logic [15:0] b,
    output logic        valid_out,
    output logic [16:0] sum
);
    logic        v1;
    logic [16:0] s1;
    logic        v2;
    logic [16:0] s2;

    always_ff @(posedge clk) begin
        if (reset) begin
            v1 <= 1'b0;
            s1 <= 17'd0;
            v2 <= 1'b0;
            s2 <= 17'd0;
        end else if (stall) begin
            v1 <= v1;
            s1 <= s1;
            v2 <= v2;
            s2 <= s2;
        end else begin
            v2 <= v1;
            s2 <= s1;
            v1 <= valid_in;
            s1 <= {1'b0, a} + {1'b0, b};
        end
    end

    always_comb begin
        valid_out = v2;
        sum = s2;
    end
endmodule

