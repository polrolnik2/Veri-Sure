module RefModule (
    input  logic clk,
    input  logic reset,
    input  logic kick,
    output logic wdt_reset
);
    localparam int unsigned TIMEOUT = 20;

    logic [4:0] count;

    always_ff @(posedge clk) begin
        if (reset) begin
            count <= 5'd0;
            wdt_reset <= 1'b0;
        end else begin
            wdt_reset <= 1'b0;
            if (kick) begin
                count <= 5'd0;
            end else if (count == (TIMEOUT-1)) begin
                wdt_reset <= 1'b1;
                count <= 5'd0;
            end else begin
                count <= count + 5'd1;
            end
        end
    end
endmodule

