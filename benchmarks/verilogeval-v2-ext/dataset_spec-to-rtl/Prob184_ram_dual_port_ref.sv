module RefModule (
    input  logic       clk,
    input  logic       reset,
    input  logic       a_we,
    input  logic [3:0] a_addr,
    input  logic [7:0] a_din,
    output logic [7:0] a_dout,
    input  logic       b_we,
    input  logic [3:0] b_addr,
    input  logic [7:0] b_din,
    output logic [7:0] b_dout
);
    localparam int unsigned DEPTH = 16;

    logic [7:0] mem [0:DEPTH-1];
    logic [7:0] a_read_next;
    logic [7:0] b_read_next;

    always_comb begin
        // Default: old memory contents.
        a_read_next = mem[a_addr];
        b_read_next = mem[b_addr];

        // WRITE-FIRST behavior.
        if (a_we) begin
            a_read_next = a_din;
            if (a_addr == b_addr && !b_we) begin
                b_read_next = a_din;
            end
        end
        if (b_we) begin
            b_read_next = b_din;
            if (b_addr == a_addr) begin
                a_read_next = b_din; // Port B wins on same-address conflict.
            end
        end
    end

    always_ff @(posedge clk) begin
        int i;
        if (reset) begin
            for (i = 0; i < DEPTH; i = i + 1) begin
                mem[i] <= 8'd0;
            end
            a_dout <= 8'd0;
            b_dout <= 8'd0;
        end else begin
            a_dout <= a_read_next;
            b_dout <= b_read_next;

            // Writes (Port B wins if both write same address).
            if (a_we && !(b_we && (b_addr == a_addr))) begin
                mem[a_addr] <= a_din;
            end
            if (b_we) begin
                mem[b_addr] <= b_din;
            end
        end
    end
endmodule

