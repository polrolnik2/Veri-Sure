module RefModule (
    input  logic [7:0] a,
    input  logic [7:0] b,
    output logic [15:0] product
);
    logic signed [7:0] a_signed, b_signed;
    logic signed [15:0] pp0, pp1, pp2, pp3, pp4, pp5, pp6, pp7;
    logic [15:0] positive_product;
    assign a_signed = a[7] ? {{8{a[7]}}, a} : {{7'd0}, a};
    assign b_signed = b[7] ? {{8{b[7]}}, b} : {{7'd0}, b};
    assign pp0 = b_signed[0] ? {{8{a_signed[7]}}, a_signed}         : 16'd0;
    assign pp1 = b_signed[1] ? {{7{a_signed[7]}}, a_signed, 1'd0}   : 16'd0;
    assign pp2 = b_signed[2] ? {{6{a_signed[7]}}, a_signed, 2'd0}   : 16'd0;
    assign pp3 = b_signed[3] ? {{5{a_signed[7]}}, a_signed, 3'd0}   : 16'd0;
    assign pp4 = b_signed[4] ? {{4{a_signed[7]}}, a_signed, 4'd0}   : 16'd0;
    assign pp5 = b_signed[5] ? {{3{a_signed[7]}}, a_signed, 5'd0}   : 16'd0;
    assign pp6 = b_signed[6] ? {{2{a_signed[7]}}, a_signed, 6'd0}   : 16'd0;
    assign pp7 = b_signed[7] ? {{1{a_signed[7]}}, a_signed, 7'd0}   : 16'd0;
    assign positive_product = pp0 + pp1 + pp2 + pp3 + pp4 + pp5 + pp6 + pp7;
    assign product = (a[7] ^ b[7]) ? -positive_product : positive_product;
endmodule
