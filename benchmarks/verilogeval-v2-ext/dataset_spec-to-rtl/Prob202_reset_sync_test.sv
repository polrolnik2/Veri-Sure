`timescale 1 ps/1 ps
`define OK 12
`define INCORRECT 13


module stimulus_gen (
    input clk,
    output logic arst,
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
        arst <= 1'b1;
        @(negedge clk) wavedrom_start("Async reset, sync release (2-flop)");

        // Deassert reset not aligned to a clock edge.
        repeat(3) @(posedge clk);
        #2 arst <= 1'b0;

        // Assert again mid-cycle.
        repeat(7) @(posedge clk);
        #3 arst <= 1'b1;
        #11 arst <= 1'b0;

        // A few more random pulses.
        repeat(8) begin
            repeat(5) @(posedge clk);
            #1 arst <= 1'b1;
            #7 arst <= 1'b0;
        end

        wavedrom_stop();
        repeat(100) @(posedge clk, negedge clk);
        $finish;
    end

endmodule

module tb();

    typedef struct packed {
        int errors;
        int errortime;
        int errors_srst;
        int errortime_srst;

        int clocks;
    } stats;

    stats stats1;


    wire[511:0] wavedrom_title;
    wire wavedrom_enable;
    int wavedrom_hide_after_time;

    reg clk=0;
    initial forever
        #5 clk = ~clk;

    logic arst;
    logic srst_ref;
    logic srst_dut;

    initial begin
        $dumpfile("wave.vcd");
        $dumpvars(1, stim1.clk, tb_mismatch ,clk,arst,srst_ref,srst_dut );
    end


    wire tb_match;       // Verification
    wire tb_mismatch = ~tb_match;

    stimulus_gen stim1 (
        .clk,
        .* ,
        .arst );
    RefModule good1 (
        .clk,
        .arst,
        .srst(srst_ref) );

    TopModule top_module1 (
        .clk,
        .arst,
        .srst(srst_dut) );


    bit strobe = 0;
    task wait_for_end_of_timestep;
        repeat(5) begin
            strobe <= !strobe;  // Try to delay until the very end of the time step.
            @(strobe);
        end
    endtask


    final begin
        if (stats1.errors_srst) $display("Hint: Output '%s' has %0d mismatches. First mismatch occurred at time %0d.", "srst", stats1.errors_srst, stats1.errortime_srst);
        else $display("Hint: Output '%s' has no mismatches.", "srst");

        $display("Hint: Total mismatched samples is %1d out of %1d samples\n", stats1.errors, stats1.clocks);
        $display("Simulation finished at %0d ps", $time);
        $display("Mismatches: %1d in %1d samples", stats1.errors, stats1.clocks);
    end

    // Verification: XORs on the right makes any X in good_vector match anything, but X in dut_vector will only match X.
    assign tb_match = ( { srst_ref } === ( { srst_ref } ^ { srst_dut } ^ { srst_ref } ) );
    // Use explicit sensitivity list here. @(*) causes NetProc::nex_input() to be called when trying to compute
    // the sensitivity list of the @(strobe) process, which isn't implemented.
    always @(posedge clk, negedge clk) begin

        stats1.clocks++;
        if (!tb_match) begin
            if (stats1.errors == 0) stats1.errortime = $time;
            stats1.errors++;
        end
        if (srst_ref !== ( srst_ref ^ srst_dut ^ srst_ref ))
        begin if (stats1.errors_srst == 0) stats1.errortime_srst = $time;
            stats1.errors_srst = stats1.errors_srst+1'b1; end

    end

   // add timeout after 100K cycles
   initial begin
     #1000000
     $display("TIMEOUT");
     $finish();
   end

endmodule

