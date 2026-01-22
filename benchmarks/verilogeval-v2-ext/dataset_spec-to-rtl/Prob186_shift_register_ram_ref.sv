module RefModule (
    input  logic       clk,
    input  logic       reset,
    input  logic       enable,
    input  logic [7:0] din,
    input  logic [4:0] tap,
    output logic [7:0] dout
);
    localparam int unsigned DEPTH = 32;

    logic [7:0] mem [0:DEPTH-1];
    logic [4:0] wr_ptr; // points to next write position

    always_ff @(posedge clk) begin
        int i;
        if (reset) begin
            wr_ptr <= 5'd0;
            dout <= 8'd0;
            for (i = 0; i < DEPTH; i = i + 1) begin
                mem[i] <= 8'd0;
            end
        end else begin
            logic [4:0] wr_ptr_next;
            logic [4:0] rd_idx;

            wr_ptr_next = wr_ptr;
            if (enable) begin
                mem[wr_ptr] <= din;
                wr_ptr_next = wr_ptr + 1'b1;
            end

            // Stage[0] is the most recently written sample at index (wr_ptr_next - 1).
            rd_idx = wr_ptr_next - 5'd1 - tap;

            if (enable && (tap == 5'd0)) begin
                // WRITE-FIRST for the newest sample written this cycle.
                dout <= din;
            end else begin
                dout <= mem[rd_idx];
            end

            wr_ptr <= wr_ptr_next;
        end
    end
endmodule

