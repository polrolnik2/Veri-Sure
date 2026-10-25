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
    output fifo_wr_ack
);

`ifdef OR1200_SB_IMPLEMENTED

    localparam integer SB_FIFO_DEPTH = 4;

    reg [67:0] sb_fifo_mem [0:SB_FIFO_DEPTH-1];
    reg [1:0] sb_fifo_wr_ptr_r;
    reg [1:0] sb_fifo_rd_ptr_r;
    reg [2:0] sb_fifo_count_r;
    reg [67:0] sb_active_data_r;
    reg outstanding_store_r;
    reg fifo_wr_ack_r;

    wire [67:0] fifo_dat_i_r;
    wire [67:0] fifo_dat_o_r;
    wire fifo_wr_r;
    wire fifo_rd_r;
    wire fifo_full_r;
    wire fifo_empty_r;
    wire fifo_pop_r;
    wire sel_sb_r;

    assign fifo_dat_i_r = {dcsb_sel_i, dcsb_dat_i, dcsb_adr_i};
    assign fifo_empty_r = (sb_fifo_count_r == 3'd0);
    assign fifo_full_r = (sb_fifo_count_r == SB_FIFO_DEPTH);
    assign fifo_wr_r = dcsb_cyc_i & dcsb_stb_i & dcsb_we_i &
                       ~fifo_full_r & ~fifo_wr_ack_r;
    assign fifo_rd_r = ~outstanding_store_r;
    assign fifo_pop_r = fifo_rd_r & ~fifo_empty_r;
    assign sel_sb_r = ~fifo_empty_r |
                      (fifo_empty_r & outstanding_store_r);

    assign fifo_dat_o_r = (outstanding_store_r | fifo_empty_r)
                        ? sb_active_data_r
                        : sb_fifo_mem[sb_fifo_rd_ptr_r];

    assign fifo_dat_i = fifo_dat_i_r;
    assign fifo_dat_o = fifo_dat_o_r;
    assign fifo_wr = fifo_wr_r;
    assign fifo_rd = fifo_rd_r;
    assign fifo_full = fifo_full_r;
    assign fifo_empty = fifo_empty_r;
    assign sel_sb = sel_sb_r;
    assign outstanding_store = outstanding_store_r;
    assign fifo_wr_ack = fifo_wr_ack_r;

    assign dcsb_dat_o = sbbiu_dat_i;
    assign dcsb_ack_o = sel_sb_r ? fifo_wr_ack_r : sbbiu_ack_i;
    assign dcsb_err_o = sel_sb_r ? 1'b0 : sbbiu_err_i;

    assign sbbiu_dat_o = sel_sb_r ? fifo_dat_o_r[63:32] : dcsb_dat_i;
    assign sbbiu_adr_o = sel_sb_r ? fifo_dat_o_r[31:0] : dcsb_adr_i;
    assign sbbiu_cyc_o = sel_sb_r ? 1'b1 : dcsb_cyc_i;
    assign sbbiu_stb_o = sel_sb_r ? 1'b1 : dcsb_stb_i;
    assign sbbiu_we_o = sel_sb_r ? 1'b1 : dcsb_we_i;
    assign sbbiu_sel_o = sel_sb_r ? fifo_dat_o_r[67:64] : dcsb_sel_i;
    assign sbbiu_cab_o = sel_sb_r ? 1'b0 : dcsb_cab_i;

    always @(posedge clk or posedge rst) begin
        if (rst) begin
            sb_fifo_wr_ptr_r <= 2'd0;
            sb_fifo_rd_ptr_r <= 2'd0;
            sb_fifo_count_r <= 3'd0;
            sb_active_data_r <= 68'd0;
            outstanding_store_r <= 1'b0;
            fifo_wr_ack_r <= 1'b0;
        end else begin
            fifo_wr_ack_r <= fifo_wr_r;

            if (sb_fifo_count_r == 3'd0 && fifo_wr_r && fifo_rd_r) begin
                // An empty FIFO can pass the newly accepted entry directly
                // into the active transaction slot.
                sb_active_data_r <= fifo_dat_i_r;
            end else begin
                if (fifo_wr_r) begin
                    sb_fifo_mem[sb_fifo_wr_ptr_r] <= fifo_dat_i_r;
                    sb_fifo_wr_ptr_r <= sb_fifo_wr_ptr_r + 2'd1;
                end

                if (fifo_pop_r) begin
                    sb_active_data_r <= sb_fifo_mem[sb_fifo_rd_ptr_r];
                    sb_fifo_rd_ptr_r <= sb_fifo_rd_ptr_r + 2'd1;
                end

                case ({fifo_wr_r, fifo_pop_r})
                    2'b10: sb_fifo_count_r <= sb_fifo_count_r + 3'd1;
                    2'b01: sb_fifo_count_r <= sb_fifo_count_r - 3'd1;
                    default: sb_fifo_count_r <= sb_fifo_count_r;
                endcase
            end

            if (sbbiu_ack_i)
                outstanding_store_r <= 1'b0;
            else if (sel_sb_r | fifo_wr_r)
                outstanding_store_r <= 1'b1;
        end
    end

`else

    assign dcsb_dat_o = sbbiu_dat_i;
    assign dcsb_ack_o = sbbiu_ack_i;
    assign dcsb_err_o = sbbiu_err_i;

    assign sbbiu_dat_o = dcsb_dat_i;
    assign sbbiu_adr_o = dcsb_adr_i;
    assign sbbiu_cyc_o = dcsb_cyc_i;
    assign sbbiu_stb_o = dcsb_stb_i;
    assign sbbiu_we_o = dcsb_we_i;
    assign sbbiu_sel_o = dcsb_sel_i;
    assign sbbiu_cab_o = dcsb_cab_i;

    assign fifo_dat_i = 68'd0;
    assign fifo_dat_o = 68'd0;
    assign fifo_wr = 1'b0;
    assign fifo_rd = 1'b0;
    assign fifo_full = 1'b0;
    assign fifo_empty = 1'b1;
    assign sel_sb = 1'b0;
    assign outstanding_store = 1'b0;
    assign fifo_wr_ack = 1'b0;

`endif

endmodule