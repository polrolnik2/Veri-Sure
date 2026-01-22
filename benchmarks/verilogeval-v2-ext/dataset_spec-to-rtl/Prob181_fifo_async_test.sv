`timescale 1 ps/1 ps
`define OK 12
`define INCORRECT 13


module stimulus_gen (
    input  wr_clk,
    input  rd_clk,
    output logic       wr_reset,
    output logic       rd_reset,
    output logic       wr_en,
    output logic [7:0] din,
    output logic       rd_en,
    output reg[511:0]  wavedrom_title,
    output reg         wavedrom_enable
);


// Add two ports to module stimulus_gen:
//    output [511:0] wavedrom_title
//    output reg wavedrom_enable

    task wavedrom_start(input[511:0] title = "");
    endtask

    task wavedrom_stop;
        #1;
    endtask

    initial begin
        wr_reset <= 1'b1;
        rd_reset <= 1'b1;
        wr_en <= 1'b0;
        rd_en <= 1'b0;
        din <= 8'd0;

        wavedrom_start("Asynchronous FIFO (depth=16, width=8)");

        // Hold reset long enough for both clocks to tick.
        repeat(4) @(posedge wr_clk);
        repeat(4) @(posedge rd_clk);
        @(negedge wr_clk) wr_reset <= 1'b0;
        @(negedge rd_clk) rd_reset <= 1'b0;

        fork
            begin : wr_driver
                int i;
                // Burst writes to reach full quickly.
                for (i = 0; i < 50; i = i + 1) begin
                    @(posedge wr_clk);
                    wr_en <= 1'b1;
                    din <= $random;
                end
                // Random traffic.
                for (i = 0; i < 300; i = i + 1) begin
                    @(posedge wr_clk);
                    wr_en <= $random;
                    din <= $random;
                end
                wr_en <= 1'b0;
            end
            begin : rd_driver
                int j;
                // Delay reads to let FIFO fill.
                repeat(8) @(posedge rd_clk);
                for (j = 0; j < 80; j = j + 1) begin
                    @(posedge rd_clk);
                    rd_en <= 1'b1;
                end
                // Random traffic.
                for (j = 0; j < 300; j = j + 1) begin
                    @(posedge rd_clk);
                    rd_en <= $random;
                end
                rd_en <= 1'b0;
            end
        join

        wavedrom_stop();
        #1 $finish;
    end

endmodule

module tb();

    typedef struct packed {
        int errors;
        int errortime;
        int errors_dout;
        int errortime_dout;
        int errors_full;
        int errortime_full;
        int errors_empty;
        int errortime_empty;

        int clocks;
    } stats;

    stats stats1;


    wire[511:0] wavedrom_title;
    wire wavedrom_enable;
    int wavedrom_hide_after_time;

    reg wr_clk=0;
    reg rd_clk=0;
    initial forever #4 wr_clk = ~wr_clk;
    initial forever #7 rd_clk = ~rd_clk;

    logic       wr_reset;
    logic       rd_reset;
    logic       wr_en;
    logic [7:0] din;
    logic       rd_en;

    logic [7:0] dout_ref;
    logic [7:0] dout_dut;
    logic full_ref;
    logic full_dut;
    logic empty_ref;
    logic empty_dut;

    initial begin
        $dumpfile("wave.vcd");
        $dumpvars(1, tb_mismatch ,wr_clk,rd_clk,wr_reset,rd_reset,wr_en,rd_en,din,dout_ref,dout_dut,full_ref,full_dut,empty_ref,empty_dut );
    end


    wire tb_match;       // Verification
    wire tb_mismatch = ~tb_match;

    stimulus_gen stim1 (
        .wr_clk,
        .rd_clk,
        .* );
    RefModule good1 (
        .wr_clk,
        .rd_clk,
        .wr_reset,
        .rd_reset,
        .wr_en,
        .din,
        .full(full_ref),
        .rd_en,
        .dout(dout_ref),
        .empty(empty_ref) );

    TopModule top_module1 (
        .wr_clk,
        .rd_clk,
        .wr_reset,
        .rd_reset,
        .wr_en,
        .din,
        .full(full_dut),
        .rd_en,
        .dout(dout_dut),
        .empty(empty_dut) );


    bit strobe = 0;
    task wait_for_end_of_timestep;
        repeat(5) begin
            strobe <= !strobe;  // Try to delay until the very end of the time step.
            @(strobe);
        end
    endtask


    final begin
        if (stats1.errors_dout) $display("Hint: Output '%s' has %0d mismatches. First mismatch occurred at time %0d.", "dout", stats1.errors_dout, stats1.errortime_dout);
        else $display("Hint: Output '%s' has no mismatches.", "dout");

        if (stats1.errors_full) $display("Hint: Output '%s' has %0d mismatches. First mismatch occurred at time %0d.", "full", stats1.errors_full, stats1.errortime_full);
        else $display("Hint: Output '%s' has no mismatches.", "full");

        if (stats1.errors_empty) $display("Hint: Output '%s' has %0d mismatches. First mismatch occurred at time %0d.", "empty", stats1.errors_empty, stats1.errortime_empty);
        else $display("Hint: Output '%s' has no mismatches.", "empty");

        $display("Hint: Total mismatched samples is %1d out of %1d samples\n", stats1.errors, stats1.clocks);
        $display("Simulation finished at %0d ps", $time);
        $display("Mismatches: %1d in %1d samples", stats1.errors, stats1.clocks);
    end

    // Verification: XORs on the right makes any X in good_vector match anything, but X in dut_vector will only match X.
    assign tb_match = ( { dout_ref, full_ref, empty_ref } === ( { dout_ref, full_ref, empty_ref } ^ { dout_dut, full_dut, empty_dut } ^ { dout_ref, full_ref, empty_ref } ) );
    // Use explicit sensitivity list here. @(*) causes NetProc::nex_input() to be called when trying to compute
    // the sensitivity list of the @(strobe) process, which isn't implemented.
    always @(posedge wr_clk or negedge wr_clk or posedge rd_clk or negedge rd_clk) begin

        stats1.clocks++;
        if (!tb_match) begin
            if (stats1.errors == 0) stats1.errortime = $time;
            stats1.errors++;
        end
        if (dout_ref !== ( dout_ref ^ dout_dut ^ dout_ref ))
        begin if (stats1.errors_dout == 0) stats1.errortime_dout = $time;
            stats1.errors_dout = stats1.errors_dout+1'b1; end

        if (full_ref !== ( full_ref ^ full_dut ^ full_ref ))
        begin if (stats1.errors_full == 0) stats1.errortime_full = $time;
            stats1.errors_full = stats1.errors_full+1'b1; end

        if (empty_ref !== ( empty_ref ^ empty_dut ^ empty_ref ))
        begin if (stats1.errors_empty == 0) stats1.errortime_empty = $time;
            stats1.errors_empty = stats1.errors_empty+1'b1; end

    end

   // add timeout after 100K cycles
   initial begin
     #2000000
     $display("TIMEOUT");
     $finish();
   end

endmodule

