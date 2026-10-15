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
    wire [67:0] fifo_dat_i_int;
    wire [67:0] fifo_dat_o_int;
    wire fifo_wr_int;
    wire fifo_rd_int;
    wire fifo_full_int;
    wire fifo_empty_int;
    wire fifo_do_rd_int;
    wire sel_sb_int;
    reg outstanding_store_int;
    reg fifo_wr_ack_int;

    reg [67:0] fifo_mem [0:3];
    reg [67:0] fifo_hold_data;
    reg [1:0] fifo_wr_ptr;
    reg [1:0] fifo_rd_ptr;
    reg [2:0] fifo_count;

    assign fifo_dat_i_int = {dcsb_sel_i, dcsb_dat_i, dcsb_adr_i};
    assign fifo_empty_int = (fifo_count == 3'd0);
    assign fifo_full_int = (fifo_count == 3'd4);
    assign fifo_dat_o_int = fifo_empty_int ? fifo_hold_data : fifo_mem[fifo_rd_ptr];
    assign fifo_wr_int = !(!dcsb_cyc_i || !dcsb_stb_i || !dcsb_we_i ||
                           fifo_full_int || fifo_wr_ack_int);
    assign fifo_rd_int = !outstanding_store_int;
    assign fifo_do_rd_int = !( !fifo_rd_int || fifo_empty_int );
    assign sel_sb_int = !fifo_empty_int || outstanding_store_int;

    assign fifo_dat_i = fifo_dat_i_int;
    assign fifo_dat_o = fifo_dat_o_int;
    assign fifo_wr = fifo_wr_int;
    assign fifo_rd = fifo_rd_int;
    assign fifo_full = fifo_full_int;
    assign fifo_empty = fifo_empty_int;
    assign sel_sb = sel_sb_int;
    assign outstanding_store = outstanding_store_int;
    assign fifo_wr_ack = fifo_wr_ack_int;

    assign {sbbiu_sel_o, sbbiu_dat_o, sbbiu_adr_o} =
        sel_sb_int ? fifo_dat_o_int : fifo_dat_i_int;
    assign sbbiu_cyc_o = sel_sb_int ? 1'b1 : dcsb_cyc_i;
    assign sbbiu_stb_o = sel_sb_int ? 1'b1 : dcsb_stb_i;
    assign sbbiu_we_o = sel_sb_int ? 1'b1 : dcsb_we_i;
    assign sbbiu_cab_o = sel_sb_int ? 1'b0 : dcsb_cab_i;

    assign dcsb_dat_o = sbbiu_dat_i;
    assign dcsb_ack_o = sel_sb_int ? fifo_wr_ack_int : sbbiu_ack_i;
    assign dcsb_err_o = sel_sb_int ? 1'b0 : sbbiu_err_i;

    always @(posedge clk) begin
        if (rst) begin
            fifo_count <= 3'd0;
            fifo_wr_ptr <= 2'd0;
            fifo_rd_ptr <= 2'd0;
            fifo_hold_data <= 68'd0;
        end else begin
            if (fifo_wr_int) begin
                fifo_mem[fifo_wr_ptr] <= fifo_dat_i_int;
                fifo_wr_ptr <= fifo_wr_ptr + 2'd1;
            end
            if (fifo_do_rd_int) begin
                fifo_hold_data <= fifo_mem[fifo_rd_ptr];
                fifo_rd_ptr <= fifo_rd_ptr + 2'd1;
            end
            case ({fifo_wr_int, fifo_do_rd_int})
                2'b10: fifo_count <= fifo_count + 3'd1;
                2'b01: fifo_count <= fifo_count - 3'd1;
                default: fifo_count <= fifo_count;
            endcase
        end
    end

    always @(posedge clk) begin
        if (rst) begin
            outstanding_store_int <= 1'b0;
            fifo_wr_ack_int <= 1'b0;
        end else begin
            fifo_wr_ack_int <= fifo_wr_int;
            if (sbbiu_ack_i)
                outstanding_store_int <= 1'b0;
            else if (sel_sb_int || fifo_wr_int)
                outstanding_store_int <= 1'b1;
        end
    end
`else
    assign sbbiu_dat_o = dcsb_dat_i;
    assign sbbiu_adr_o = dcsb_adr_i;
    assign sbbiu_cyc_o = dcsb_cyc_i;
    assign sbbiu_stb_o = dcsb_stb_i;
    assign sbbiu_we_o = dcsb_we_i;
    assign sbbiu_sel_o = dcsb_sel_i;
    assign sbbiu_cab_o = dcsb_cab_i;

    assign dcsb_dat_o = sbbiu_dat_i;
    assign dcsb_ack_o = sbbiu_ack_i;
    assign dcsb_err_o = sbbiu_err_i;

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