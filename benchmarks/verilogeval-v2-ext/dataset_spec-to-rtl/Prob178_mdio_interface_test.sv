`timescale 1 ps/1 ps
`define OK 12
`define INCORRECT 13


module stimulus_gen (
    input clk,
    output logic        reset,
    output logic        start,
    output logic        op,
    output logic [4:0]  phy_addr,
    output logic [4:0]  reg_addr,
    output logic [15:0] wr_data,
    output logic        mdio_in,
    output reg[511:0]  wavedrom_title,
    output reg         wavedrom_enable
);

    task wavedrom_start(input[511:0] title = "");
    endtask

    task wavedrom_stop;
        #1;
    endtask

    localparam int unsigned TOTAL_BITS = 64;
    localparam int unsigned TOTAL_CYCLES = (TOTAL_BITS*2) + 1; // final low + done

    logic active;
    int unsigned offset;
    logic [15:0] phy_rd_data;

    always_ff @(posedge clk) begin
        if (reset) begin
            active <= 1'b0;
            offset <= 0;
            phy_rd_data <= 16'h0000;
            mdio_in <= 1'b1;
        end else begin
            if (!active && start) begin
                active <= 1'b1;
                offset <= 0;
                phy_rd_data <= $random;
            end else if (active) begin
                offset <= offset + 1;
                if (offset >= (TOTAL_CYCLES-1)) begin
                    active <= 1'b0;
                end
            end

            // Default pulled-up line when PHY not driving.
            mdio_in <= 1'b1;

            if (active && (op == 1'b1)) begin
                // For READ, drive turnaround/data bits in a deterministic schedule.
                // Update on LOW half-cycles so it is stable for the next HIGH sample.
                if (offset[0] == 1'b0) begin
                    int unsigned bitpos;
                    bitpos = (offset >> 1);
                    if (bitpos == 47) begin
                        mdio_in <= 1'b0; // TA2 = 0
                    end else if ((bitpos >= 48) && (bitpos < 64)) begin
                        mdio_in <= phy_rd_data[63 - bitpos];
                    end else begin
                        mdio_in <= 1'b1;
                    end
                end
            end
        end
    end

    task automatic run_op(
        input logic        op_in,
        input logic [4:0]  phy_in,
        input logic [4:0]  reg_in,
        input logic [15:0] wdata_in
    );
        @(negedge clk);
        op <= op_in;
        phy_addr <= phy_in;
        reg_addr <= reg_in;
        wr_data <= wdata_in;
        start <= 1'b1;

        // spurious start while busy should be ignored
        repeat(4) @(negedge clk) start <= $random;
        @(negedge clk) start <= 1'b0;

        // Wait long enough for completion.
        repeat(TOTAL_CYCLES+5) @(posedge clk);
    endtask

    initial begin
        reset <= 1'b1;
        start <= 1'b0;
        op <= 1'b0;
        phy_addr <= 5'd0;
        reg_addr <= 5'd0;
        wr_data <= 16'd0;
        mdio_in <= 1'b1;

        @(negedge clk) wavedrom_start("MDIO master (Clause22, fixed timing)");
        repeat(2) @(posedge clk);
        reset <= 1'b0;

        run_op(1'b0, 5'h01, 5'h02, 16'hA55A); // write
        run_op(1'b1, 5'h03, 5'h04, 16'h0000); // read
        repeat(6) run_op($random, $random, $random, $random);

        wavedrom_stop();
        repeat(40) @(posedge clk, negedge clk) begin
            start <= 1'b0;
            op <= $random;
            phy_addr <= $random;
            reg_addr <= $random;
            wr_data <= $random;
        end
        $finish;
    end
endmodule

module tb();
    typedef struct packed {
        int errors;
        int errortime;
        int errors_mdc;
        int errortime_mdc;
        int errors_mdio_out;
        int errortime_mdio_out;
        int errors_mdio_oe;
        int errortime_mdio_oe;
        int errors_rd_data;
        int errortime_rd_data;
        int errors_busy;
        int errortime_busy;
        int errors_done;
        int errortime_done;
        int clocks;
    } stats;

    stats stats1;

    wire[511:0] wavedrom_title;
    wire wavedrom_enable;
    int wavedrom_hide_after_time;

    reg clk=0;
    initial forever #5 clk = ~clk;

    logic        reset;
    logic        start;
    logic        op;
    logic [4:0]  phy_addr;
    logic [4:0]  reg_addr;
    logic [15:0] wr_data;
    logic        mdio_in;

    logic mdc_ref, mdc_dut;
    logic mdio_out_ref, mdio_out_dut;
    logic mdio_oe_ref, mdio_oe_dut;
    logic [15:0] rd_data_ref, rd_data_dut;
    logic busy_ref, busy_dut;
    logic done_ref, done_dut;

    initial begin
        $dumpfile("wave.vcd");
        $dumpvars(1, stim1.clk, tb_mismatch ,clk,reset,start,op,phy_addr,reg_addr,wr_data,mdio_in,mdc_ref,mdc_dut,mdio_out_ref,mdio_out_dut,mdio_oe_ref,mdio_oe_dut,rd_data_ref,rd_data_dut,busy_ref,busy_dut,done_ref,done_dut );
    end

    wire tb_match;
    wire tb_mismatch = ~tb_match;

    stimulus_gen stim1 (
        .clk,
        .*,
        .reset,
        .start,
        .op,
        .phy_addr,
        .reg_addr,
        .wr_data,
        .mdio_in
    );

    RefModule good1 (
        .clk,
        .reset,
        .start,
        .op,
        .phy_addr,
        .reg_addr,
        .wr_data,
        .mdio_in,
        .mdc(mdc_ref),
        .mdio_out(mdio_out_ref),
        .mdio_oe(mdio_oe_ref),
        .rd_data(rd_data_ref),
        .busy(busy_ref),
        .done(done_ref)
    );

    TopModule top_module1 (
        .clk,
        .reset,
        .start,
        .op,
        .phy_addr,
        .reg_addr,
        .wr_data,
        .mdio_in,
        .mdc(mdc_dut),
        .mdio_out(mdio_out_dut),
        .mdio_oe(mdio_oe_dut),
        .rd_data(rd_data_dut),
        .busy(busy_dut),
        .done(done_dut)
    );

    final begin
        $display("Hint: Total mismatched samples is %1d out of %1d samples\n", stats1.errors, stats1.clocks);
        $display("Simulation finished at %0d ps", $time);
        $display("Mismatches: %1d in %1d samples", stats1.errors, stats1.clocks);
    end

    assign tb_match =
        ( { mdc_ref, mdio_out_ref, mdio_oe_ref, rd_data_ref, busy_ref, done_ref }
          === ( { mdc_ref, mdio_out_ref, mdio_oe_ref, rd_data_ref, busy_ref, done_ref }
                ^ { mdc_dut, mdio_out_dut, mdio_oe_dut, rd_data_dut, busy_dut, done_dut }
                ^ { mdc_ref, mdio_out_ref, mdio_oe_ref, rd_data_ref, busy_ref, done_ref } ) );

    always @(posedge clk, negedge clk) begin
        stats1.clocks++;
        if (!tb_match) begin
            if (stats1.errors == 0) stats1.errortime = $time;
            stats1.errors++;
        end
        if (mdc_ref !== (mdc_ref ^ mdc_dut ^ mdc_ref))
        begin if (stats1.errors_mdc == 0) stats1.errortime_mdc = $time;
            stats1.errors_mdc = stats1.errors_mdc+1'b1; end
        if (mdio_out_ref !== (mdio_out_ref ^ mdio_out_dut ^ mdio_out_ref))
        begin if (stats1.errors_mdio_out == 0) stats1.errortime_mdio_out = $time;
            stats1.errors_mdio_out = stats1.errors_mdio_out+1'b1; end
        if (mdio_oe_ref !== (mdio_oe_ref ^ mdio_oe_dut ^ mdio_oe_ref))
        begin if (stats1.errors_mdio_oe == 0) stats1.errortime_mdio_oe = $time;
            stats1.errors_mdio_oe = stats1.errors_mdio_oe+1'b1; end
        if (rd_data_ref !== (rd_data_ref ^ rd_data_dut ^ rd_data_ref))
        begin if (stats1.errors_rd_data == 0) stats1.errortime_rd_data = $time;
            stats1.errors_rd_data = stats1.errors_rd_data+1'b1; end
        if (busy_ref !== (busy_ref ^ busy_dut ^ busy_ref))
        begin if (stats1.errors_busy == 0) stats1.errortime_busy = $time;
            stats1.errors_busy = stats1.errors_busy+1'b1; end
        if (done_ref !== (done_ref ^ done_dut ^ done_ref))
        begin if (stats1.errors_done == 0) stats1.errortime_done = $time;
            stats1.errors_done = stats1.errors_done+1'b1; end
    end

   initial begin
     #8000000
     $display("TIMEOUT");
     $finish();
   end

endmodule

