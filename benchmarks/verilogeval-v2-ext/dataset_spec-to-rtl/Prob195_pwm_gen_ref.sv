module RefModule (
    input  logic       clk,
    input  logic       reset,
    input  logic [7:0] duty,
    output logic       pwm
);
    logic [7:0] counter;

    always_ff @(posedge clk) begin
        if (reset) begin
            counter <= 8'd0;
            pwm <= 1'b0;
        end else begin
            pwm <= (counter < duty);
            counter <= counter + 8'd1;
        end
    end
endmodule

