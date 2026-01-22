`timescale 1 ps/1 ps
`define OK 12
`define INCORRECT 13


module stimulus_gen (
    input  clk_fast,
    input  clk_slow,
    input  ready_fast,
    output logic reset_fast,
    output logic reset_slow,
    output logic pulse_in,
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
        reset_fast <= 1'b1;
        reset_slow <= 1'b1;
        pulse_in <= 1'b0;

        wavedrom_start("CDC pulse sync (fast->slow)");

        repeat(4) @(posedge clk_fast);
        repeat(2) @(posedge clk_slow);
        @(negedge clk_fast) reset_fast <= 1'b0;
        @(negedge clk_slow) reset_slow <= 1'b0;

        // Generate pulses; mostly only when ready, but occasionally inject spurious pulses when not ready.
        repeat(400) @(posedge clk_fast) begin
            if (ready_fast) begin
                pulse_in <= !($random & 3); // ~25% chance
            end else begin
                pulse_in <= !($random & 31); // rare spurious
            end
        end
        pulse_in <= 1'b0;

        wavedrom_stop();
        #1 $finish;
    end

endmodule

module tb();

    typedef struct packed {
        int errors;
        int errortime;
        int errors_ready;
        int errortime_ready;
        int errors_pulse_out;
        int errortime_pulse_out;

        int clocks;
    } stats;

    stats stats1;


    wire[511:0] wavedrom_title;
    wire wavedrom_enable;
    int wavedrom_hide_after_time;

    reg clk_fast=0;
    reg clk_slow=0;
    initial forever #3 clk_fast = ~clk_fast;
    initial forever #11 clk_slow = ~clk_slow;

    logic reset_fast;
    logic reset_slow;
    logic pulse_in;

    logic ready_ref;
    logic ready_dut;
    logic pulse_out_ref;
    logic pulse_out_dut;

    initial begin
        $dumpfile("wave.vcd");
        $dumpvars(1, tb_mismatch ,clk_fast,clk_slow,reset_fast,reset_slow,pulse_in,ready_ref,ready_dut,pulse_out_ref,pulse_out_dut );
    end


    wire tb_match;       // Verification
    wire tb_mismatch = ~tb_match;

    stimulus_gen stim1 (
        .clk_fast,
        .clk_slow,
        .ready_fast(ready_ref),
        .* );
    RefModule good1 (
        .clk_fast,
        .reset_fast,
        .clk_slow,
        .reset_slow,
        .pulse_in,
        .ready(ready_ref),
        .pulse_out(pulse_out_ref) );

    TopModule top_module1 (
        .clk_fast,
        .reset_fast,
        .clk_slow,
        .reset_slow,
        .pulse_in,
        .ready(ready_dut),
        .pulse_out(pulse_out_dut) );


    bit strobe = 0;
    task wait_for_end_of_timestep;
        repeat(5) begin
            strobe <= !strobe;  // Try to delay until the very end of the time step.
            @(strobe);
        end
    endtask


    final begin
        if (stats1.errors_ready) $display("Hint: Output '%s' has %0d mismatches. First mismatch occurred at time %0d.", "ready", stats1.errors_ready, stats1.errortime_ready);
        else $display("Hint: Output '%s' has no mismatches.", "ready");

        if (stats1.errors_pulse_out) $display("Hint: Output '%s' has %0d mismatches. First mismatch occurred at time %0d.", "pulse_out", stats1.errors_pulse_out, stats1.errortime_pulse_out);
        else $display("Hint: Output '%s' has no mismatches.", "pulse_out");

        $display("Hint: Total mismatched samples is %1d out of %1d samples\n", stats1.errors, stats1.clocks);
        $display("Simulation finished at %0d ps", $time);
        $display("Mismatches: %1d in %1d samples", stats1.errors, stats1.clocks);
    end

    // Verification: XORs on the right makes any X in good_vector match anything, but X in dut_vector will only match X.
    assign tb_match = ( { ready_ref, pulse_out_ref } === ( { ready_ref, pulse_out_ref } ^ { ready_dut, pulse_out_dut } ^ { ready_ref, pulse_out_ref } ) );
    // Use explicit sensitivity list here. @(*) causes NetProc::nex_input() to be called when trying to compute
    // the sensitivity list of the @(strobe) process, which isn't implemented.
    always @(posedge clk_fast or negedge clk_fast or posedge clk_slow or negedge clk_slow) begin

        stats1.clocks++;
        if (!tb_match) begin
            if (stats1.errors == 0) stats1.errortime = $time;
            stats1.errors++;
        end
        if (ready_ref !== ( ready_ref ^ ready_dut ^ ready_ref ))
        begin if (stats1.errors_ready == 0) stats1.errortime_ready = $time;
            stats1.errors_ready = stats1.errors_ready+1'b1; end

        if (pulse_out_ref !== ( pulse_out_ref ^ pulse_out_dut ^ pulse_out_ref ))
        begin if (stats1.errors_pulse_out == 0) stats1.errortime_pulse_out = $time;
            stats1.errors_pulse_out = stats1.errors_pulse_out+1'b1; end

    end

   // add timeout after 100K cycles
   initial begin
     #2000000
     $display("TIMEOUT");
     $finish();
   end

endmodule

