module RefModule(
    input       [31:0]  src1,
    input       [31:0]  src2,
    output reg  [31:0]  out
    );
    
    reg [66:0]  fraction_1;
    reg [66:0]  fraction_2;
    reg [66:0]  fraction_Ans;
    reg [7:0]   exponent_1;
    reg [7:0]   exponent_2;
    reg [7:0]   exponent_Ans;
    reg         sign_1;
    reg         sign_2;
    reg         sign_Ans;
    reg  [4:0]  norm_count;
    reg         norm_vld;

    // Combinational implementation of FP32 addition
    always @* begin
        fraction_1  = {2'd0, src1[22:0], 42'd0};  
        fraction_2  = {2'd0, src2[22:0], 42'd0};  
        exponent_1  = src1[30:23];
        exponent_2  = src2[30:23];
        sign_1      = src1[31];
        sign_2      = src2[31]; 

        if(exponent_1 == 0) begin
            exponent_1 = 1;
            fraction_1[65] = 0;  
        end else begin
            fraction_1[65] = 1;
        end
        
        if(exponent_2 == 0) begin
            exponent_2 = 1;
            fraction_2[65] = 0;  
        end else begin
            fraction_2[65] = 1;
        end

        if(exponent_1 > exponent_2) begin
            fraction_2 = fraction_2 >> (exponent_1 - exponent_2);
            exponent_Ans = exponent_1;
        end else if(exponent_1 < exponent_2) begin
            fraction_1 = fraction_1 >> (exponent_2 - exponent_1);
            exponent_Ans = exponent_2;
        end else begin
            exponent_Ans = exponent_1;  
        end

        if(sign_1 == sign_2) begin
            fraction_Ans = fraction_1 + fraction_2;
            sign_Ans = sign_1;
        end else begin
            if(fraction_1 >= fraction_2) begin
                fraction_Ans = fraction_1 - fraction_2;
                sign_Ans = sign_1;
            end else begin
                fraction_Ans = fraction_2 - fraction_1;
                sign_Ans = sign_2;
            end
        end

        if(fraction_Ans[66]) begin
            fraction_Ans = fraction_Ans >> 1;
            exponent_Ans = exponent_Ans + 1;
        end

        if(fraction_Ans[65] == 0) begin
            PENC32({11'b0, fraction_Ans[64:42]}, norm_count, norm_vld);  
            fraction_Ans = fraction_Ans << (5'd23 - norm_count);  
            exponent_Ans = exponent_Ans + norm_count - 5'd23;  
        end

        out[22:0]  = fraction_Ans[64:42];
        out[30:23] = exponent_Ans[7:0];
        out[31]    = sign_Ans; 
    end

    task PENC32;
        input   [31:0] D;
        output  [4:0]  Q;
        output         vld;
        reg [3:0] Q2_h, Q2_l;
        reg       vld2_h, vld2_l;
        begin
            PENC16( D[31:16],   Q2_h,   vld2_h);
            PENC16( D[15:0],    Q2_l,   vld2_l);
            Q[4]    = vld2_h;
            Q[3:0]  = vld2_h ? Q2_h : Q2_l;
            vld     = vld2_h | vld2_l;
        end
    endtask

    task PENC16;
        input   [15:0] D;
        output  [3:0]  Q;
        output         vld;
        reg [2:0] Q1_h, Q1_l;
        reg       vld1_h, vld1_l;
        begin
            PENC8( D[15:8],  Q1_h,   vld1_h);
            PENC8( D[7:0],   Q1_l,   vld1_l);
            Q[3]    = vld1_h;
            Q[2:0]  = vld1_h ? Q1_h : Q1_l;
            vld     = vld1_h | vld1_l;
        end
    endtask

    task PENC8;
        input   [7:0] D;
        output  [2:0] Q;
        output        vld;
        begin
            vld  = D[7] | D[6] | D[5] | D[4] | D[3] | D[2] | D[1] | D[0];
            Q[2] = D[7] | D[6] | D[5] | D[4];
            Q[1] = (D[7] | D[6] | D[5] | D[4]) ? (D[7] | D[6]) : (D[3] | D[2]);
            Q[0] = (D[7] | D[6] | D[5] | D[4]) ? (D[7] | (~D[6] & D[5])) : (D[3] | (~D[2] & D[1]));
        end
    endtask
endmodule


