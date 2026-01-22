`timescale 1 ps/1 ps
`define OK 12
`define INCORRECT 13


module stimulus_gen (
    input clk,
    output logic reset,
    output logic kick,
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
        kick <= 1'b0;
        @(negedge clk) wavedrom_start("Watchdog timer (timeout=20)");

        repeat(3) @(posedge clk);
        @(negedge clk) reset <= 1'b0;

        // Provide kicks, then leave a long gap to trigger the watchdog.
        repeat(5) begin
            @(negedge clk) kick <= 1'b1;
            @(negedge clk) kick <= 1'b0;
            repeat(7) @(negedge clk);
        end

        // No kicks for a while.
        repeat(60) @(negedge clk) kick <= 1'b0;

        // Random kicks.
        repeat(200) @(negedge clk) kick <= !($random & 31);

        wavedrom_stop();
        repeat(80) @(posedge clk, negedge clk) kick <= $random;
        $finish;
    end

endmodule

module tb();

    typedef struct packed {
        int errors;
        int errortime;
        int errors_wdt_reset;
        int errortime_wdt_reset;

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
    logic kick;
    logic wdt_ref;
    logic wdt_dut;

    initial begin
        $dumpfile("wave.vcd");
        $dumpvars(1, stim1.clk, tb_mismatch ,clk,reset,kick,wdt_ref,wdt_dut );
    end


    wire tb_match;       // Verification
    wire tb_mismatch = ~tb_match;

    stimulus_gen stim1 (
        .clk,
        .* ,
        .reset,
        .kick );
    RefModule good1 (
        .clk,
        .reset,
        .kick,
        .wdt_reset(wdt_ref) );

    TopModule top_module1 (
        .clk,
        .reset,
        .kick,
        .wdt_reset(wdt_dut) );


    bit strobe = 0;
    task wait_for_end_of_timestep;
        repeat(5) begin
            strobe <= !strobe;  // Try to delay until the very end of the time step.
            @(strobe);
        end
    endtask


    final begin
        if (stats1.errors_wdt_reset) $display("Hint: Output '%s' has %0d mismatches. First mismatch occurred at time %0d.", "wdt_reset", stats1.errors_wdt_reset, stats1.errortime_wdt_reset);
        else $display("Hint: Output '%s' has no mismatches.", "wdt_reset");

        $display("Hint: Total mismatched samples is %1d out of %1d samples\n", stats1.errors, stats1.clocks);
        $display("Simulation finished at %0d ps", $time);
        $display("Mismatches: %1d in %1d samples", stats1.errors, stats1.clocks);
    end

    // Verification: XORs on the right makes any X in good_vector match anything, but X in dut_vector will only match X.
    assign tb_match = ( { wdt_ref } === ( { wdt_ref } ^ { wdt_dut } ^ { wdt_ref } ) );
    // Use explicit sensitivity list here. @(*) causes NetProc::nex_input() to be called when trying to compute
    // the sensitivity list of the @(strobe) process, which isn't implemented.
    always @(posedge clk, negedge clk) begin

        stats1.clocks++;
        if (!tb_match) begin
            if (stats1.errors == 0) stats1.errortime = $time;
            stats1.errors++;
        end
        if (wdt_ref !== ( wdt_ref ^ wdt_dut ^ wdt_ref ))
        begin if (stats1.errors_wdt_reset == 0) stats1.errortime_wdt_reset = $time;
            stats1.errors_wdt_reset = stats1.errors_wdt_reset+1'b1; end

    end

   // add timeout after 100K cycles
   initial begin
     #1000000
     $display("TIMEOUT");
     $finish();
   end

endmodule

