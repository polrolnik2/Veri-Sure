module or1200_gmultp2_32x32 (
    input  logic [31:0] X,
    input  logic [31:0] Y,
    input  logic        CLK,
    input  logic        RST,
    output logic [63:0] P
);

    logic signed [31:0] xi;
    logic signed [31:0] yi;
    logic signed [63:0] xi_ext;
    logic signed [63:0] yi_ext;
    logic signed [63:0] product;
    logic        [63:0] p0;
    logic        [63:0] p1;

    assign xi     = X;
    assign yi     = Y;
    assign xi_ext = {{32{xi[31]}}, xi};
    assign yi_ext = {{32{yi[31]}}, yi};
    assign product = xi_ext * yi_ext;

    always @(posedge CLK) begin
        p0 <= product;
    end

    always @(posedge CLK or posedge RST) begin
        if (RST)
            p1 <= 64'b0;
        else
            p1 <= p0;
    end

    assign P = p1;

endmodule