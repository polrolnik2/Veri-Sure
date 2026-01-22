`timescale 1 ps/1 ps
`define OK 12
`define INCORRECT 13


module stimulus_gen (
    input clk,
    output logic reset,
    output logic wr_en,
    output logic rd_en,
    output logic [7:0] din,
    output reg[511:0] wavedrom_title,
    output reg wavedrom_enable
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
        reset <= 1'b1;
        wr_en <= 1'b0;
        rd_en <= 1'b0;
        din <= 8'd0;

        @(negedge clk) wavedrom_start("Synchronous FIFO (depth=16, width=8)");
        repeat(2) @(posedge clk);
        reset <= 1'b0;

        // Fill to full.
        repeat(16) @(posedge clk) begin
            wr_en <= 1'b1;
            rd_en <= 1'b0;
            din <= $random;
        end

        // Attempt writes while full.
        repeat(4) @(posedge clk) begin
            wr_en <= 1'b1;
            rd_en <= 1'b0;
            din <= $random;
        end

        // Drain to empty.
        repeat(16) @(posedge clk) begin
            wr_en <= 1'b0;
            rd_en <= 1'b1;
            din <= $random;
        end

        // Attempt reads while empty.
        repeat(4) @(posedge clk) begin
            wr_en <= 1'b0;
            rd_en <= 1'b1;
            din <= $random;
        end

        // Random mixed traffic.
        repeat(200) @(posedge clk) begin
            wr_en <= $random;
            rd_en <= $random;
            din <= $random;
        end

        wavedrom_stop();
        repeat(40) @(posedge clk, negedge clk) begin
            wr_en <= 1'b0;
            rd_en <= 1'b0;
            din <= $random;
        end
        $finish;
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

    reg clk=0;
    initial forever
        #5 clk = ~clk;

    logic reset;
    logic wr_en;
    logic rd_en;
    logic [7:0] din;

    logic [7:0] dout_ref;
    logic [7:0] dout_dut;
    logic full_ref;
    logic full_dut;
    logic empty_ref;
    logic empty_dut;

    initial begin
        $dumpfile("wave.vcd");
        $dumpvars(1, stim1.clk, tb_mismatch ,clk,reset,wr_en,rd_en,din,dout_ref,dout_dut,full_ref,full_dut,empty_ref,empty_dut );
    end


    wire tb_match;       // Verification
    wire tb_mismatch = ~tb_match;

    stimulus_gen stim1 (
        .clk,
        .* ,
        .reset,
        .wr_en,
        .rd_en,
        .din );
    RefModule good1 (
        .clk,
        .reset,
        .wr_en,
        .rd_en,
        .din,
        .dout(dout_ref),
        .full(full_ref),
        .empty(empty_ref) );

    TopModule top_module1 (
        .clk,
        .reset,
        .wr_en,
        .rd_en,
        .din,
        .dout(dout_dut),
        .full(full_dut),
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
    always @(posedge clk, negedge clk) begin

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
     #1000000
     $display("TIMEOUT");
     $finish();
   end

endmodule

