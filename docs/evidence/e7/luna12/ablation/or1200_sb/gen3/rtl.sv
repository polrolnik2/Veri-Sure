module or1200_sb(
    input clk,
    input rst,
    input [31:0] dcsb_dat_i,
    input [31:0] dcsb_adr_i,
    input dcsb_cyc_i,
    input dcsb_stb_i,
    input dcsb_we_i,
    input [3:0] dcsb_sel_i,
    input dcsb_cab_i,
    output [31:0] dcsb_dat_o,
    output dcsb_ack_o,
    output dcsb_err_o,
    output [31:0] sbbiu_dat_o,
    output [31:0] sbbiu_adr_o,
    output sbbiu_cyc_o,
    output sbbiu_stb_o,
    output sbbiu_we_o,
    output [3:0] sbbiu_sel_o,
    output sbbiu_cab_o,
    input [31:0] sbbiu_dat_i,
    input sbbiu_ack_i,
    input sbbiu_err_i,
    output [67:0] fifo_dat_i,
    output [67:0] fifo_dat_o,
    output fifo_wr,
    output fifo_rd,
    output fifo_full,
    output fifo_empty,
    output sel_sb,
    output outstanding_store,
    output fifo_wr_ack,
    output or1200_sb_fifo
);

    reg [67:0] fifo_mem [0:3];
    reg [1:0] wr_ptr_r;
    reg [1:0] rd_ptr_r;
    reg [2:0] fifo_count_r;
    reg outstanding_store_r;
    reg fifo_wr_ack_r;
    integer i;

    wire [67:0] fifo_payload_r;
    wire fifo_wr_r;
    wire fifo_rd_r;
    wire fifo_pop_r;
    wire fifo_full_r;
    wire fifo_empty_r;
    wire sel_sb_r;

    assign fifo_payload_r = {dcsb_sel_i, dcsb_dat_i, dcsb_adr_i};
    assign fifo_dat_i = fifo_payload_r;
    assign fifo_dat_o = fifo_mem[rd_ptr_r];

    assign fifo_full_r = (fifo_count_r == 3'd4);
    assign fifo_empty_r = (fifo_count_r == 3'd0);
    assign fifo_wr_r = dcsb_cyc_i & dcsb_stb_i & dcsb_we_i &
                       ~fifo_full_r & ~fifo_wr_ack_r;
    assign fifo_rd_r = ~outstanding_store_r;
    assign fifo_pop_r = fifo_rd_r & ~fifo_empty_r;
    assign sel_sb_r = ~fifo_empty_r | (fifo_empty_r & outstanding_store_r);

    assign fifo_wr = fifo_wr_r;
    assign fifo_rd = fifo_rd_r;
    assign fifo_full = fifo_full_r;
    assign fifo_empty = fifo_empty_r;
    assign sel_sb = sel_sb_r;
    assign outstanding_store = outstanding_store_r;
    assign fifo_wr_ack = fifo_wr_ack_r;
    assign or1200_sb_fifo = fifo_pop_r;

    assign dcsb_dat_o = sbbiu_dat_i;
    assign dcsb_ack_o = sel_sb_r ? fifo_wr_ack_r : sbbiu_ack_i;
    assign dcsb_err_o = sel_sb_r ? 1'b0 : sbbiu_err_i;

    assign sbbiu_dat_o = sel_sb_r ? fifo_dat_o[63:32] : dcsb_dat_i;
    assign sbbiu_adr_o = sel_sb_r ? fifo_dat_o[31:0] : dcsb_adr_i;
    assign sbbiu_sel_o = sel_sb_r ? fifo_dat_o[67:64] : dcsb_sel_i;
    assign sbbiu_we_o = sel_sb_r ? 1'b1 : dcsb_we_i;
    assign sbbiu_cab_o = sel_sb_r ? 1'b0 : dcsb_cab_i;
    assign sbbiu_cyc_o = sel_sb_r ? 1'b1 : dcsb_cyc_i;
    assign sbbiu_stb_o = sel_sb_r ? 1'b1 : dcsb_stb_i;

    always @(posedge clk) begin
        if (rst) begin
            wr_ptr_r <= 2'b00;
            rd_ptr_r <= 2'b00;
            fifo_count_r <= 3'd0;
            outstanding_store_r <= 1'b0;
            fifo_wr_ack_r <= 1'b0;
            for (i = 0; i < 4; i = i + 1)
                fifo_mem[i] <= 68'd0;
        end else begin
            fifo_wr_ack_r <= fifo_wr_r;

            if (fifo_wr_r) begin
                fifo_mem[wr_ptr_r] <= fifo_payload_r;
                wr_ptr_r <= wr_ptr_r + 2'b01;
            end

            if (fifo_pop_r)
                rd_ptr_r <= rd_ptr_r + 2'b01;

            case ({fifo_wr_r, fifo_pop_r})
                2'b10: fifo_count_r <= fifo_count_r + 3'd1;
                2'b01: fifo_count_r <= fifo_count_r - 3'd1;
                default: fifo_count_r <= fifo_count_r;
            endcase

            if (sbbiu_ack_i)
                outstanding_store_r <= 1'b0;
            else if (sel_sb_r | fifo_wr_r)
                outstanding_store_r <= 1'b1;
        end
    end

endmodule