module RefModule (
    input  logic              clk,
    input  logic              reset,
    input  logic signed [7:0] sample_in,
    output logic signed [17:0] sample_out
);
    localparam logic signed [7:0] C0 = 8'sd7;
    localparam logic signed [7:0] C1 = -8'sd3;
    localparam logic signed [7:0] C2 = 8'sd5;
    localparam logic signed [7:0] C3 = -8'sd2;

    logic signed [7:0] x1;
    logic signed [7:0] x2;
    logic signed [7:0] x3;

    logic signed [15:0] m0;
    logic signed [15:0] m1;
    logic signed [15:0] m2;
    logic signed [15:0] m3;
    logic signed [17:0] acc_next;

    always_comb begin
        // Compute output using the window that includes the current sample_in.
        m0 = sample_in * C0;
        m1 = x1 * C1;
        m2 = x2 * C2;
        m3 = x3 * C3;

        acc_next =
            {{2{m0[15]}}, m0}
            + {{2{m1[15]}}, m1}
            + {{2{m2[15]}}, m2}
            + {{2{m3[15]}}, m3};
    end

    always_ff @(posedge clk) begin
        if (reset) begin
            x1 <= '0;
            x2 <= '0;
            x3 <= '0;
            sample_out <= '0;
        end else begin
            x3 <= x2;
            x2 <= x1;
            x1 <= sample_in;
            sample_out <= acc_next;
        end
    end
endmodule

