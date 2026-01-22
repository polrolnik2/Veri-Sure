module RefModule (
    input  logic              clk,
    input  logic              reset,
    input  logic              start,
    input  logic signed [15:0] angle,
    output logic signed [15:0] cos_out,
    output logic signed [15:0] sin_out,
    output logic              done
);
    localparam int unsigned NITER = 12;
    localparam logic signed [17:0] X0 = 18'sd9949;  // 0.607252... in Q1.14

    logic busy;
    logic [3:0] iter;

    logic signed [17:0] x;
    logic signed [17:0] y;
    logic signed [15:0] z;

    function automatic logic signed [15:0] atan_deg256(input logic [3:0] idx);
        case (idx)
            4'd0: atan_deg256 = 16'sd11520;
            4'd1: atan_deg256 = 16'sd6801;
            4'd2: atan_deg256 = 16'sd3593;
            4'd3: atan_deg256 = 16'sd1824;
            4'd4: atan_deg256 = 16'sd916;
            4'd5: atan_deg256 = 16'sd458;
            4'd6: atan_deg256 = 16'sd229;
            4'd7: atan_deg256 = 16'sd115;
            4'd8: atan_deg256 = 16'sd57;
            4'd9: atan_deg256 = 16'sd29;
            4'd10: atan_deg256 = 16'sd14;
            4'd11: atan_deg256 = 16'sd7;
            default: atan_deg256 = 16'sd0;
        endcase
    endfunction

    always_ff @(posedge clk) begin
        if (reset) begin
            busy <= 1'b0;
            iter <= 4'd0;
            x <= '0;
            y <= '0;
            z <= '0;
            cos_out <= '0;
            sin_out <= '0;
            done <= 1'b0;
        end else begin
            done <= 1'b0;

            if (!busy) begin
                if (start) begin
                    busy <= 1'b1;
                    iter <= 4'd0;
                    x <= X0;
                    y <= 18'sd0;
                    z <= angle;
                end
            end else begin
                logic signed [17:0] x_shift;
                logic signed [17:0] y_shift;
                logic signed [17:0] x_next;
                logic signed [17:0] y_next;
                logic signed [15:0] z_next;
                logic signed [15:0] atan_i;

                atan_i = atan_deg256(iter);
                x_shift = (y >>> iter);
                y_shift = (x >>> iter);

                if (z >= 0) begin
                    x_next = x - x_shift;
                    y_next = y + y_shift;
                    z_next = z - atan_i;
                end else begin
                    x_next = x + x_shift;
                    y_next = y - y_shift;
                    z_next = z + atan_i;
                end

                x <= x_next;
                y <= y_next;
                z <= z_next;
                iter <= iter + 4'd1;

                if (iter == (NITER-1)) begin
                    busy <= 1'b0;
                    cos_out <= x_next[15:0];
                    sin_out <= y_next[15:0];
                    done <= 1'b1;
                end
            end
        end
    end
endmodule

