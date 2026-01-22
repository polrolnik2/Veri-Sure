module RefModule (
    input  logic [31:0] a,
    input  logic [31:0] b,
    output logic [31:0] sum
);
    logic signed [31:0] a_s;
    logic signed [31:0] b_s;
    logic signed [31:0] sum_raw;

    logic same_sign;
    logic overflow;

    assign a_s = $signed(a);
    assign b_s = $signed(b);
    assign sum_raw = a_s + b_s;

    assign same_sign = (a_s[31] == b_s[31]);
    assign overflow = same_sign && (sum_raw[31] != a_s[31]);

    always_comb begin
        if (overflow) begin
            sum = a_s[31] ? 32'h8000_0000 : 32'h7FFF_FFFF;
        end else begin
            sum = sum_raw;
        end
    end
endmodule

