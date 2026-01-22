module RefModule (
    input  logic       clk,
    input  logic       reset,
    input  logic [7:0] sample_in,
    output logic [7:0] avg_out
);
    logic [7:0] window [0:7];
    logic [11:0] sum;

    integer i;

    always_ff @(posedge clk) begin
        if (reset) begin
            for (i = 0; i < 8; i = i + 1) begin
                window[i] <= 8'd0;
            end
            sum <= 12'd0;
            avg_out <= 8'd0;
        end else begin
            logic [11:0] sum_next;
            sum_next = sum + {4'd0, sample_in} - {4'd0, window[7]};

            for (i = 7; i > 0; i = i - 1) begin
                window[i] <= window[i-1];
            end
            window[0] <= sample_in;

            sum <= sum_next;
            avg_out <= sum_next[11:3];  // divide by 8
        end
    end
endmodule

