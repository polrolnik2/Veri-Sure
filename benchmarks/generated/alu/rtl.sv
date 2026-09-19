module alu (
    input  logic [15:0] a,
    input  logic [15:0] b,
    input  logic [2:0]  cmd,
    output logic [15:0] r
);

    logic [31:0] sr_value;
    logic [31:0] sru_value;

    always @(*) begin
        sr_value  = {{16{a[15]}}, a};
        sru_value = {16'b0, a};

        case (cmd)
            3'b000: r = a + b;
            3'b001: r = a - b;
            3'b010: r = a & b;
            3'b011: r = a | b;
            3'b100: r = a ^ b;
            3'b101: r = a << b;
            3'b110: r = sr_value >> b;
            3'b111: r = sru_value >> b;
            3'bxxx: r = 16'bx;
            default: begin
                r = 16'b0;
`ifndef CODE_FOR_SYNTHESIS
                $display("alu: invalid command %b", cmd);
`endif
            end
        endcase
    end

endmodule