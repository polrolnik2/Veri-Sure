module RefModule (
    input  logic [3:0] a,
    input  logic [3:0] b,
    output logic [7:0] product
);
    logic [7:0] pp0, pp1, pp2, pp3;

    assign pp0 = b[0] ? {4'b0000, a}           : 8'd0;
    assign pp1 = b[1] ? ({4'b0000, a} << 1)    : 8'd0;
    assign pp2 = b[2] ? ({4'b0000, a} << 2)    : 8'd0;
    assign pp3 = b[3] ? ({4'b0000, a} << 3)    : 8'd0;

    assign product = pp0 + pp1 + pp2 + pp3;
endmodule

