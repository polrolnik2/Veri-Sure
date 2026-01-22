module RefModule(
    input logic [15:0] a,      // 16-bit FP16 number a
    input logic [15:0] b,      // 16-bit FP16 number b
    output logic [15:0] result // 16-bit FP16 result
);

    // Fields for FP16
    logic sign_a, sign_b, sign_result;
    logic [4:0] exponent_a, exponent_b;
    logic [6:0] exponent_result, exponent_sum;
    logic [9:0] mantissa_a, mantissa_b, mantissa_result;
    logic [20:0] product_mantissa;  // 11-bit * 11-bit = 21-bit result

    // Extract components of FP16 a
    assign sign_a = a[15];
    assign exponent_a = a[14:10];
    assign mantissa_a = {1'b1, a[9:0]};  // implicit leading 1 for normalized numbers

    // Extract components of FP16 b
    assign sign_b = b[15];
    assign exponent_b = b[14:10];
    assign mantissa_b = {1'b1, b[9:0]};  // implicit leading 1 for normalized numbers

    // Multiply mantissas
    assign product_mantissa = mantissa_a * mantissa_b;

    // Add exponents
    assign exponent_sum = exponent_a + exponent_b - 15; // subtract the bias (15 for FP16)

    // Handle sign of result
    assign sign_result = sign_a ^ sign_b;

    // Normalize result if product mantissa exceeds 10 bits
    always_comb begin
        // Find position of most significant bit and normalize
        if (product_mantissa[20] == 1) begin
            // MSB at [20]: right shift by 1
            mantissa_result = product_mantissa[19:10];
            exponent_result = exponent_sum + 1;
        end else if (product_mantissa[19] == 1) begin
            // MSB at [19]: normal case, no shift
            mantissa_result = product_mantissa[18:9];
            exponent_result = exponent_sum;
        end else if (product_mantissa[18] == 1) begin
            // MSB at [18]: left shift by 1, exponent -= 1
            mantissa_result = product_mantissa[17:8];
            exponent_result = exponent_sum - 1;
        end else if (product_mantissa[17] == 1) begin
            // MSB at [17]: left shift by 2, exponent -= 2
            mantissa_result = product_mantissa[16:7];
            exponent_result = exponent_sum - 2;
        end else if (product_mantissa[16] == 1) begin
            // MSB at [16]: left shift by 3, exponent -= 3
            mantissa_result = product_mantissa[15:6];
            exponent_result = exponent_sum - 3;
        end else if (product_mantissa[15] == 1) begin
            // MSB at [15]: left shift by 4, exponent -= 4
            mantissa_result = product_mantissa[14:5];
            exponent_result = exponent_sum - 4;
        end else if (product_mantissa[14] == 1) begin
            // MSB at [14]: left shift by 5, exponent -= 5
            mantissa_result = product_mantissa[13:4];
            exponent_result = exponent_sum - 5;
        end else if (product_mantissa[13] == 1) begin
            // MSB at [13]: left shift by 6, exponent -= 6
            mantissa_result = product_mantissa[12:3];
            exponent_result = exponent_sum - 6;
        end else if (product_mantissa[12] == 1) begin
            // MSB at [12]: left shift by 7, exponent -= 7
            mantissa_result = product_mantissa[11:2];
            exponent_result = exponent_sum - 7;
        end else if (product_mantissa[11] == 1) begin
            // MSB at [11]: left shift by 8, exponent -= 8
            mantissa_result = product_mantissa[10:1];
            exponent_result = exponent_sum - 8;
        end else if (product_mantissa[10] == 1) begin
            // MSB at [10]: left shift by 9, exponent -= 9
            mantissa_result = {product_mantissa[9:0], 1'b0}[9:0];
            exponent_result = exponent_sum - 9;
        end else begin
            // Result is zero or underflow
            mantissa_result = 10'b0;
            exponent_result = 7'b0;
        end
    end

    // Handle special cases: zero, denormalized, and overflow
    always_comb begin
        if (exponent_a == 5'b11111 || exponent_b == 5'b11111) begin
            // Check for NaN or infinity
            result = {sign_result, 5'b11111, 10'b0};
        end else if (exponent_a == 0 || exponent_b == 0) begin
            // Check for zero
            result = 16'b0;
        end else if (exponent_result > 31) begin
            // Overflow handling (set to infinity)
            result = {sign_result, 5'b11111, 10'b0};
        end else if (exponent_result <= 0) begin
            // Underflow handling (set to zero)
            result = 16'b0;
        end else begin
            // Normal result
            result = {sign_result, exponent_result[4:0], mantissa_result[9:0]};
        end
    end
endmodule
