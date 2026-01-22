module RefModule (
    input  logic [31:0] a,
    input  logic [31:0] b,
    input  logic [3:0]  op,
    output logic [31:0] result,
    output logic        zero,
    output logic        carry,
    output logic        overflow,
    output logic        negative
);
    logic [32:0] ext;
    logic [4:0] shamt;

    assign shamt = b[4:0];

    always_comb begin
        result = 32'd0;
        carry = 1'b0;
        overflow = 1'b0;
        ext = 33'd0;

        case (op)
            4'd0: begin  // ADD
                ext = {1'b0, a} + {1'b0, b};
                result = ext[31:0];
                carry = ext[32];
                overflow = (~(a[31] ^ b[31])) & (result[31] ^ a[31]);
            end
            4'd1: begin  // SUB
                ext = {1'b0, a} + {1'b0, ~b} + 33'd1;
                result = ext[31:0];
                carry = ext[32];  // 1 = no borrow
                overflow = (a[31] ^ b[31]) & (result[31] ^ a[31]);
            end
            4'd2: result = a & b;
            4'd3: result = a | b;
            4'd4: result = a ^ b;
            4'd5: result = a << shamt;
            4'd6: result = a >> shamt;
            4'd7: result = $signed(a) >>> shamt;
            4'd8: result = ($signed(a) < $signed(b)) ? 32'd1 : 32'd0;
            4'd9: result = (a < b) ? 32'd1 : 32'd0;
            4'd10: result = (a == b) ? 32'd1 : 32'd0;
            4'd11: result = (a != b) ? 32'd1 : 32'd0;
            default: begin
                result = 32'd0;
                carry = 1'b0;
                overflow = 1'b0;
            end
        endcase
    end

    assign zero = (result == 32'd0);
    assign negative = result[31];
endmodule

