module RefModule (
    input  logic clk,
    input  logic reset,
    input  logic noisy,
    output logic clean
);
    logic [7:0] hist;

    always_ff @(posedge clk) begin
        if (reset) begin
            hist <= 8'd0;
            clean <= 1'b0;
        end else begin
            logic [7:0] hist_next;
            hist_next = {hist[6:0], noisy};
            hist <= hist_next;

            if (&hist_next) clean <= 1'b1;
            else if (~|hist_next) clean <= 1'b0;
            else clean <= clean;
        end
    end
endmodule

