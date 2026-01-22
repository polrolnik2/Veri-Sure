module RefModule (
    input [15:0] A,      // Input A
    input [15:0] B,      // Input B
    output logic [15:0] result // Output result
);

    // Extract sign, exponent, and mantissa from A and B
    logic signA, signB, signS;
    logic [4:0] expA, expB;
    logic [10:0] mantA, mantB;
    
    assign signA = A[15];
    assign expA = A[14:10];
    assign mantA = {1'b1, A[9:0]};  // Implicit leading 1 + 10-bit mantissa = 11 bits
    
    assign signB = B[15];
    assign expB = B[14:10];
    assign mantB = {1'b1, B[9:0]};  // Implicit leading 1 + 10-bit mantissa = 11 bits

    // Exponent alignment: calculate exponent difference
    logic [4:0] exp_diff;
    logic expA_larger;
    assign expA_larger = (expA >= expB);
    assign exp_diff = expA_larger ? (expA - expB) : (expB - expA);
    
    // Select larger exponent and corresponding mantissa
    logic [4:0] exp_larger;
    logic [10:0] mant_larger, mant_smaller;
    assign exp_larger = expA_larger ? expA : expB;
    assign mant_larger = expA_larger ? mantA : mantB;
    assign mant_smaller = expA_larger ? mantB : mantA;
    
    // Right-shift smaller mantissa for alignment
    logic [10:0] mant_smaller_shifted;
    assign mant_smaller_shifted = mant_smaller >> exp_diff;
    
    // Determine sign based on magnitude
    logic signA_use, signB_use;
    assign signA_use = expA_larger ? signA : signB;
    assign signB_use = expA_larger ? signB : signA;
    
    // Perform addition or subtraction based on signs
    logic [11:0] sum_result;
    logic do_add;
    assign do_add = (signA_use == signB_use);
    
    always_comb begin
        if (do_add) begin
            // Same sign: add mantissas
            sum_result = mant_larger + mant_smaller_shifted;
        end else begin
            // Different signs: subtract mantissas
            sum_result = (mant_larger > mant_smaller_shifted) ? 
                         (mant_larger - mant_smaller_shifted) :
                         (mant_smaller_shifted - mant_larger);
        end
    end
    
    // Determine result sign
    logic [11:0] abs_sum;
    assign abs_sum = sum_result;
    
    always_comb begin
        if (do_add) begin
            signS = signA_use;
        end else begin
            signS = (mant_larger >= mant_smaller_shifted) ? signA_use : signB_use;
        end
    end
    
    // Normalize result
    logic [4:0] exp_result;
    logic [9:0] mant_result;
    
    always_comb begin
        // Find position of most significant bit and normalize
        if (abs_sum[11] == 1) begin
            // Carry: right shift by 1
            exp_result = exp_larger + 1;
            mant_result = abs_sum[10:1];
        end else if (abs_sum[10] == 1) begin
            // Normal case: no shift
            exp_result = exp_larger;
            mant_result = abs_sum[9:0];
        end else if (abs_sum[9] == 1) begin
            // Left shift by 1, exponent decreases by 1
            exp_result = exp_larger - 1;
            mant_result = {abs_sum[8:0], 1'b0};
        end else if (abs_sum[8] == 1) begin
            // Left shift by 2, exponent decreases by 2
            exp_result = exp_larger - 2;
            mant_result = {abs_sum[7:0], 2'b0};
        end else if (abs_sum[7] == 1) begin
            // Left shift by 3, exponent decreases by 3
            exp_result = exp_larger - 3;
            mant_result = {abs_sum[6:0], 3'b0};
        end else if (abs_sum[6] == 1) begin
            // Left shift by 4, exponent decreases by 4
            exp_result = exp_larger - 4;
            mant_result = {abs_sum[5:0], 4'b0};
        end else if (abs_sum[5] == 1) begin
            // Left shift by 5, exponent decreases by 5
            exp_result = exp_larger - 5;
            mant_result = {abs_sum[4:0], 5'b0};
        end else if (abs_sum[4] == 1) begin
            // Left shift by 6, exponent decreases by 6
            exp_result = exp_larger - 6;
            mant_result = {abs_sum[3:0], 6'b0};
        end else if (abs_sum[3] == 1) begin
            // Left shift by 7, exponent decreases by 7
            exp_result = exp_larger - 7;
            mant_result = {abs_sum[2:0], 7'b0};
        end else if (abs_sum[2] == 1) begin
            // Left shift by 8, exponent decreases by 8
            exp_result = exp_larger - 8;
            mant_result = {abs_sum[1:0], 8'b0};
        end else if (abs_sum[1] == 1) begin
            // Left shift by 9, exponent decreases by 9
            exp_result = exp_larger - 9;
            mant_result = {abs_sum[0], 9'b0};
        end else begin
            // Result is zero or underflow
            exp_result = 5'b0;
            mant_result = 10'b0;
        end
    end
    
    // Handle special cases and generate final output
    always_comb begin
        // Check for infinity or NaN
        if ((expA == 5'b11111) && (expB == 5'b11111)) begin
            // Both operands are infinity
            if (signA == signB) begin
                result = {signA, 5'b11111, 10'b0};  // Same sign infinity
            end else begin
                result = 16'h7e00;  // NaN
            end
        end else if (expA == 5'b11111) begin
            // A is infinity
            result = A;
        end else if (expB == 5'b11111) begin
            // B is infinity
            result = B;
        end else if ((expA == 5'b00000) && (expB == 5'b00000)) begin
            // Both operands are zero
            result = 16'b0;
        end else if (expA == 5'b00000) begin
            // A is zero
            result = B;
        end else if (expB == 5'b00000) begin
            // B is zero
            result = A;
        end else if (abs_sum == 12'b0) begin
            // Result is zero
            result = 16'b0;
        end else if (exp_result > 31) begin
            // Overflow to infinity
            result = {signS, 5'b11111, 10'b0};
        end else if (exp_result <= 0) begin
            // Underflow to zero
            result = 16'b0;
        end else begin
            // Normal result
            result = {signS, exp_result[4:0], mant_result[9:0]};
        end
    end

endmodule
