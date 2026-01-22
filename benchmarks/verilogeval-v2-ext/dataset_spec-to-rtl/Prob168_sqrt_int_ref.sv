module RefModule (
    input  logic        clk,
    input  logic        reset,
    input  logic        start,
    input  logic [15:0] radicand,
    output logic [7:0]  root,
    output logic        done
);
    logic       busy;
    logic [3:0] count;

    logic [15:0] n;
    logic [8:0]  low;
    logic [8:0]  high;

    always_ff @(posedge clk) begin
        if (reset) begin
            busy <= 1'b0;
            count <= 4'd0;
            n <= 16'd0;
            low <= 9'd0;
            high <= 9'd0;
            root <= 8'd0;
            done <= 1'b0;
        end else begin
            done <= 1'b0;

            if (!busy) begin
                if (start) begin
                    busy <= 1'b1;
                    count <= 4'd0;
                    n <= radicand;
                    low <= 9'd0;
                    high <= 9'd255;
                end
            end else begin
                logic [8:0] mid9;
                logic [7:0] mid;
                logic [15:0] mid_sq;
                logic [8:0] low_next;
                logic [8:0] high_next;

                mid9 = (low + high) >> 1;
                mid = mid9[7:0];
                mid_sq = mid * mid;

                low_next = low;
                high_next = high;
                if (mid_sq <= n) begin
                    low_next = {1'b0, mid} + 9'd1;
                end else begin
                    high_next = {1'b0, mid} - 9'd1;
                end

                low <= low_next;
                high <= high_next;
                count <= count + 4'd1;

                if (count == 4'd7) begin
                    busy <= 1'b0;
                    root <= high_next[7:0];
                    done <= 1'b1;
                end
            end
        end
    end
endmodule

