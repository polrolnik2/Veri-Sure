module RefModule (
    input  logic       wr_clk,
    input  logic       rd_clk,
    input  logic       wr_reset,
    input  logic       rd_reset,
    input  logic       wr_en,
    input  logic [7:0] din,
    output logic       full,
    input  logic       rd_en,
    output logic [7:0] dout,
    output logic       empty
);
    localparam int unsigned DEPTH = 16;
    localparam int unsigned ADDR_BITS = 4;
    localparam int unsigned PTR_BITS = ADDR_BITS + 1;

    logic [7:0] mem [0:DEPTH-1];

    // Write domain pointers.
    logic [PTR_BITS-1:0] wr_ptr_bin;
    logic [PTR_BITS-1:0] wr_ptr_gray;
    logic [PTR_BITS-1:0] rd_ptr_gray_w1, rd_ptr_gray_w2;

    // Read domain pointers.
    logic [PTR_BITS-1:0] rd_ptr_bin;
    logic [PTR_BITS-1:0] rd_ptr_gray;
    logic [PTR_BITS-1:0] wr_ptr_gray_r1, wr_ptr_gray_r2;

    function automatic logic [PTR_BITS-1:0] bin2gray(input logic [PTR_BITS-1:0] x);
        return (x >> 1) ^ x;
    endfunction

    // Write-side next-state.
    logic wr_fire;
    logic [PTR_BITS-1:0] wr_ptr_bin_next;
    logic [PTR_BITS-1:0] wr_ptr_gray_next;
    logic full_next;
    logic [PTR_BITS-1:0] rd_ptr_gray_w2_inv;

    assign wr_fire = wr_en && !full;
    assign wr_ptr_bin_next = wr_ptr_bin + (wr_fire ? 1'b1 : 1'b0);
    assign wr_ptr_gray_next = bin2gray(wr_ptr_bin_next);
    assign rd_ptr_gray_w2_inv = {~rd_ptr_gray_w2[PTR_BITS-1:PTR_BITS-2], rd_ptr_gray_w2[PTR_BITS-3:0]};
    assign full_next = (wr_ptr_gray_next == rd_ptr_gray_w2_inv);

    // Read-side next-state.
    logic rd_fire;
    logic [PTR_BITS-1:0] rd_ptr_bin_next;
    logic [PTR_BITS-1:0] rd_ptr_gray_next;
    logic empty_next;

    assign rd_fire = rd_en && !empty;
    assign rd_ptr_bin_next = rd_ptr_bin + (rd_fire ? 1'b1 : 1'b0);
    assign rd_ptr_gray_next = bin2gray(rd_ptr_bin_next);
    assign empty_next = (rd_ptr_gray_next == wr_ptr_gray_r2);

    // Write clock domain logic.
    always_ff @(posedge wr_clk) begin
        if (wr_reset) begin
            wr_ptr_bin <= '0;
            wr_ptr_gray <= '0;
            rd_ptr_gray_w1 <= '0;
            rd_ptr_gray_w2 <= '0;
            full <= 1'b0;
        end else begin
            // Sync read pointer gray into write domain.
            rd_ptr_gray_w1 <= rd_ptr_gray;
            rd_ptr_gray_w2 <= rd_ptr_gray_w1;

            full <= full_next;
            if (wr_fire) begin
                mem[wr_ptr_bin[ADDR_BITS-1:0]] <= din;
                wr_ptr_bin <= wr_ptr_bin_next;
                wr_ptr_gray <= wr_ptr_gray_next;
            end
        end
    end

    // Read clock domain logic.
    always_ff @(posedge rd_clk) begin
        if (rd_reset) begin
            rd_ptr_bin <= '0;
            rd_ptr_gray <= '0;
            wr_ptr_gray_r1 <= '0;
            wr_ptr_gray_r2 <= '0;
            empty <= 1'b1;
            dout <= 8'd0;
        end else begin
            // Sync write pointer gray into read domain.
            wr_ptr_gray_r1 <= wr_ptr_gray;
            wr_ptr_gray_r2 <= wr_ptr_gray_r1;

            empty <= empty_next;
            if (rd_fire) begin
                dout <= mem[rd_ptr_bin[ADDR_BITS-1:0]];
                rd_ptr_bin <= rd_ptr_bin_next;
                rd_ptr_gray <= rd_ptr_gray_next;
            end
        end
    end
endmodule

