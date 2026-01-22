`timescale 1 ps/1 ps
`define OK 12
`define INCORRECT 13


module stimulus_gen (
    input clk,
    output logic reset,
    output logic start,
    output logic signed [15:0] angle,
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

    function automatic logic signed [15:0] rand_angle;
        int r;
        begin
            r = $random;
            if (r < 0) r = -r;
            r = r % 23041;  // 0..23040
            if ($random & 1) r = -r;
            rand_angle = r[15:0];
        end
    endfunction

    task automatic run_op(input logic signed [15:0] angle_in);
        int i;
        @(negedge clk);
        angle <= angle_in;
        start <= 1'b1;
        @(negedge clk);
        start <= 1'b0;

        // While busy (12 iterations), perturb angle and inject a spurious start pulse.
        for (i = 0; i < 12; i = i + 1) begin
            @(negedge clk);
            angle <= rand_angle();
            start <= (i == 4);
        end

        @(negedge clk);
        start <= 1'b0;

        // Gap before next operation.
        repeat(6) @(negedge clk);
    endtask

    initial begin
        reset <= 1'b1;
        start <= 1'b0;
        angle <= 16'sd0;

        @(negedge clk) wavedrom_start("CORDIC rotation (12 iters)");

        repeat(2) @(posedge clk);
        @(negedge clk) reset <= 1'b0;

        // Directed angles (degrees*256).
        run_op(16'sd0);        // 0 deg
        run_op(16'sd7680);     // 30 deg
        run_op(16'sd11520);    // 45 deg
        run_op(-16'sd11520);   // -45 deg
        run_op(16'sd23040);    // 90 deg
        run_op(-16'sd23040);   // -90 deg

        // Random angles.
        repeat(20) run_op(rand_angle());

        wavedrom_stop();
        repeat(40) @(posedge clk, negedge clk) begin
            angle <= rand_angle();
            start <= 1'b0;
        end
        $finish;
    end

endmodule

module tb();

    typedef struct packed {
        int errors;
        int errortime;
        int errors_cos_out;
        int errortime_cos_out;
        int errors_sin_out;
        int errortime_sin_out;
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
    logic signed [15:0] angle;
    logic signed [15:0] cos_ref;
    logic signed [15:0] sin_ref;
    logic done_ref;
    logic signed [15:0] cos_dut;
    logic signed [15:0] sin_dut;
    logic done_dut;

    initial begin
        $dumpfile("wave.vcd");
        $dumpvars(1, stim1.clk, tb_mismatch ,clk,reset,start,angle,cos_ref,sin_ref,done_ref,cos_dut,sin_dut,done_dut );
    end


    wire tb_match;       // Verification
    wire tb_mismatch = ~tb_match;

    stimulus_gen stim1 (
        .clk,
        .* ,
        .reset,
        .start,
        .angle );
    RefModule good1 (
        .clk,
        .reset,
        .start,
        .angle,
        .cos_out(cos_ref),
        .sin_out(sin_ref),
        .done(done_ref) );

    TopModule top_module1 (
        .clk,
        .reset,
        .start,
        .angle,
        .cos_out(cos_dut),
        .sin_out(sin_dut),
        .done(done_dut) );


    bit strobe = 0;
    task wait_for_end_of_timestep;
        repeat(5) begin
            strobe <= !strobe;  // Try to delay until the very end of the time step.
            @(strobe);
        end
    endtask


    final begin
        if (stats1.errors_cos_out) $display("Hint: Output '%s' has %0d mismatches. First mismatch occurred at time %0d.", "cos_out", stats1.errors_cos_out, stats1.errortime_cos_out);
        else $display("Hint: Output '%s' has no mismatches.", "cos_out");

        if (stats1.errors_sin_out) $display("Hint: Output '%s' has %0d mismatches. First mismatch occurred at time %0d.", "sin_out", stats1.errors_sin_out, stats1.errortime_sin_out);
        else $display("Hint: Output '%s' has no mismatches.", "sin_out");

        if (stats1.errors_done) $display("Hint: Output '%s' has %0d mismatches. First mismatch occurred at time %0d.", "done", stats1.errors_done, stats1.errortime_done);
        else $display("Hint: Output '%s' has no mismatches.", "done");

        $display("Hint: Total mismatched samples is %1d out of %1d samples\n", stats1.errors, stats1.clocks);
        $display("Simulation finished at %0d ps", $time);
        $display("Mismatches: %1d in %1d samples", stats1.errors, stats1.clocks);
    end

    // Verification: XORs on the right makes any X in good_vector match anything, but X in dut_vector will only match X.
    assign tb_match = ( { cos_ref, sin_ref, done_ref } === ( { cos_ref, sin_ref, done_ref } ^ { cos_dut, sin_dut, done_dut } ^ { cos_ref, sin_ref, done_ref } ) );
    // Use explicit sensitivity list here. @(*) causes NetProc::nex_input() to be called when trying to compute
    // the sensitivity list of the @(strobe) process, which isn't implemented.
    always @(posedge clk, negedge clk) begin

        stats1.clocks++;
        if (!tb_match) begin
            if (stats1.errors == 0) stats1.errortime = $time;
            stats1.errors++;
        end
        if (cos_ref !== ( cos_ref ^ cos_dut ^ cos_ref ))
        begin if (stats1.errors_cos_out == 0) stats1.errortime_cos_out = $time;
            stats1.errors_cos_out = stats1.errors_cos_out+1'b1; end

        if (sin_ref !== ( sin_ref ^ sin_dut ^ sin_ref ))
        begin if (stats1.errors_sin_out == 0) stats1.errortime_sin_out = $time;
            stats1.errors_sin_out = stats1.errors_sin_out+1'b1; end

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

