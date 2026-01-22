module RefModule (
    input  logic       clk,
    input  logic       reset,
    input  logic       start,
    input  logic [7:0] a,
    input  logic [7:0] b,
    output logic [15:0] product,
    output logic       done
);
    logic        busy;
    logic [3:0]  count;
    logic [15:0] acc;
    logic [15:0] multiplicand;
    logic [7:0]  multiplier;

    always_ff @(posedge clk) begin
        if (reset) begin
            busy <= 1'b0;
            count <= 4'd0;
            acc <= 16'd0;
            multiplicand <= 16'd0;
            multiplier <= 8'd0;
            product <= 16'd0;
            done <= 1'b0;
        end else begin
            done <= 1'b0;

            if (!busy) begin
                if (start) begin
                    busy <= 1'b1;
                    count <= 4'd0;
                    acc <= 16'd0;
                    multiplicand <= {8'd0, a};
                    multiplier <= b;
                end
            end else begin
                logic [15:0] acc_next;
                acc_next = acc + (multiplier[0] ? multiplicand : 16'd0);

                acc <= acc_next;
                multiplicand <= (multiplicand << 1);
                multiplier <= (multiplier >> 1);
                count <= count + 4'd1;

                if (count == 4'd7) begin
                    busy <= 1'b0;
                    product <= acc_next;
                    done <= 1'b1;
                end
            end
        end
    end
endmodule

