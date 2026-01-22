`timescale 1 ps/1 ps
`define OK 12
`define INCORRECT 13


module stimulus_gen (
    input clk,
    output logic reset,
    output logic start,
    output logic [7:0] dividend,
    output logic [7:0] divisor,
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

    task automatic run_op(input logic [7:0] dividend_in, input logic [7:0] divisor_in);
        int i;
        @(negedge clk);
        dividend <= dividend_in;
        divisor <= divisor_in;
        start <= 1'b1;

        @(negedge clk);
        start <= 1'b0;

        // During the 8-cycle operation, change inputs and inject a spurious start pulse.
        for (i = 0; i < 8; i = i + 1) begin
            @(negedge clk);
            dividend <= $random;
            divisor <= $random;
            start <= (i == 2);  // should be ignored while busy
        end

        @(negedge clk);
        start <= 1'b0;
    endtask

    initial begin
        reset <= 1'b1;
        start <= 1'b0;
        dividend <= 8'd0;
        divisor <= 8'd1;

        @(negedge clk) wavedrom_start("8-bit restoring divider");

        repeat(2) @(posedge clk);
        reset <= 1'b0;

        // Directed tests (avoid divisor=0 here).
        run_op(8'd100, 8'd3);
        run_op(8'd255, 8'd15);
        run_op(8'd17,  8'd5);
        run_op(8'd0,   8'd7);

        // Random tests (force divisor != 0).
        repeat(20) run_op($random, ($random | 8'd1));

        wavedrom_stop();
        repeat(20) @(posedge clk, negedge clk) begin
            dividend <= $random;
            divisor <= ($random | 8'd1);
            start <= 1'b0;
        end
        $finish;
    end

endmodule

module tb();

    typedef struct packed {
        int errors;
        int errortime;
        int errors_quotient;
        int errortime_quotient;
        int errors_remainder;
        int errortime_remainder;
        int errors_done;
        int errortime_done;

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
    logic start;
    logic [7:0] dividend;
    logic [7:0] divisor;
    logic [7:0] quotient_ref;
    logic [7:0] quotient_dut;
    logic [7:0] remainder_ref;
    logic [7:0] remainder_dut;
    logic done_ref;
    logic done_dut;

    initial begin
        $dumpfile("wave.vcd");
        $dumpvars(1, stim1.clk, tb_mismatch ,clk,reset,start,dividend,divisor,quotient_ref,quotient_dut,remainder_ref,remainder_dut,done_ref,done_dut );
    end


    wire tb_match;       // Verification
    wire tb_mismatch = ~tb_match;

    stimulus_gen stim1 (
        .clk,
        .* ,
        .reset,
        .start,
        .dividend,
        .divisor );
    RefModule good1 (
        .clk,
        .reset,
        .start,
        .dividend,
        .divisor,
        .quotient(quotient_ref),
        .remainder(remainder_ref),
        .done(done_ref) );

    TopModule top_module1 (
        .clk,
        .reset,
        .start,
        .dividend,
        .divisor,
        .quotient(quotient_dut),
        .remainder(remainder_dut),
        .done(done_dut) );


    bit strobe = 0;
    task wait_for_end_of_timestep;
        repeat(5) begin
            strobe <= !strobe;  // Try to delay until the very end of the time step.
            @(strobe);
        end
    endtask


    final begin
        if (stats1.errors_quotient) $display("Hint: Output '%s' has %0d mismatches. First mismatch occurred at time %0d.", "quotient", stats1.errors_quotient, stats1.errortime_quotient);
        else $display("Hint: Output '%s' has no mismatches.", "quotient");

        if (stats1.errors_remainder) $display("Hint: Output '%s' has %0d mismatches. First mismatch occurred at time %0d.", "remainder", stats1.errors_remainder, stats1.errortime_remainder);
        else $display("Hint: Output '%s' has no mismatches.", "remainder");

        if (stats1.errors_done) $display("Hint: Output '%s' has %0d mismatches. First mismatch occurred at time %0d.", "done", stats1.errors_done, stats1.errortime_done);
        else $display("Hint: Output '%s' has no mismatches.", "done");

        $display("Hint: Total mismatched samples is %1d out of %1d samples\n", stats1.errors, stats1.clocks);
        $display("Simulation finished at %0d ps", $time);
        $display("Mismatches: %1d in %1d samples", stats1.errors, stats1.clocks);
    end

    // Verification: XORs on the right makes any X in good_vector match anything, but X in dut_vector will only match X.
    assign tb_match =
        ( { quotient_ref, remainder_ref, done_ref }
          === ( { quotient_ref, remainder_ref, done_ref } ^ { quotient_dut, remainder_dut, done_dut } ^ { quotient_ref, remainder_ref, done_ref } ) );

    // Use explicit sensitivity list here. @(*) causes NetProc::nex_input() to be called when trying to compute
    // the sensitivity list of the @(strobe) process, which isn't implemented.
    always @(posedge clk, negedge clk) begin

        stats1.clocks++;
        if (!tb_match) begin
            if (stats1.errors == 0) stats1.errortime = $time;
            stats1.errors++;
        end
        if (quotient_ref !== ( quotient_ref ^ quotient_dut ^ quotient_ref ))
        begin if (stats1.errors_quotient == 0) stats1.errortime_quotient = $time;
            stats1.errors_quotient = stats1.errors_quotient+1'b1; end

        if (remainder_ref !== ( remainder_ref ^ remainder_dut ^ remainder_ref ))
        begin if (stats1.errors_remainder == 0) stats1.errortime_remainder = $time;
            stats1.errors_remainder = stats1.errors_remainder+1'b1; end

        if (done_ref !== ( done_ref ^ done_dut ^ done_ref ))
        begin if (stats1.errors_done == 0) stats1.errortime_done = $time;
            stats1.errors_done = stats1.errors_done+1'b1; end

    end

   // add timeout after 100K cycles
   initial begin
     #1000000
     $display("TIMEOUT");
     $finish();
   end

endmodule

