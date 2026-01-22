`timescale 1 ps/1 ps
`define OK 12
`define INCORRECT 13


module stimulus_gen (
    input clk,
    output logic        reset,
    output logic        start,
    output logic [15:0] radicand,
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

    task automatic run_op(input logic [15:0] n_in);
        int i;
        @(negedge clk);
        radicand <= n_in;
        start <= 1'b1;

        @(negedge clk);
        start <= 1'b0;

        // During the 8-cycle operation, change inputs and inject a spurious start pulse.
        for (i = 0; i < 8; i = i + 1) begin
            @(negedge clk);
            radicand <= $random;
            start <= (i == 4);  // should be ignored while busy
        end

        @(negedge clk);
        start <= 1'b0;
    endtask

    initial begin
        reset <= 1'b1;
        start <= 1'b0;
        radicand <= 16'd0;

        @(negedge clk) wavedrom_start("Integer sqrt (8-cycle iterative)");

        repeat(2) @(posedge clk);
        reset <= 1'b0;

        // Directed tests.
        run_op(16'd0);
        run_op(16'd1);
        run_op(16'd2);
        run_op(16'd3);
        run_op(16'd4);
        run_op(16'd15);
        run_op(16'd16);
        run_op(16'd255);
        run_op(16'd256);
        run_op(16'd65535);

        // Random tests.
        repeat(20) run_op($random);

        wavedrom_stop();
        repeat(20) @(posedge clk, negedge clk) begin
            radicand <= $random;
            start <= 1'b0;
        end
        $finish;
    end

endmodule

module tb();

    typedef struct packed {
        int errors;
        int errortime;
        int errors_root;
        int errortime_root;
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
    logic [15:0] radicand;
    logic [7:0] root_ref;
    logic [7:0] root_dut;
    logic done_ref;
    logic done_dut;

    initial begin
        $dumpfile("wave.vcd");
        $dumpvars(1, stim1.clk, tb_mismatch ,clk,reset,start,radicand,root_ref,root_dut,done_ref,done_dut );
    end


    wire tb_match;       // Verification
    wire tb_mismatch = ~tb_match;

    stimulus_gen stim1 (
        .clk,
        .* ,
        .reset,
        .start,
        .radicand );
    RefModule good1 (
        .clk,
        .reset,
        .start,
        .radicand,
        .root(root_ref),
        .done(done_ref) );

    TopModule top_module1 (
        .clk,
        .reset,
        .start,
        .radicand,
        .root(root_dut),
        .done(done_dut) );


    bit strobe = 0;
    task wait_for_end_of_timestep;
        repeat(5) begin
            strobe <= !strobe;  // Try to delay until the very end of the time step.
            @(strobe);
        end
    endtask


    final begin
        if (stats1.errors_root) $display("Hint: Output '%s' has %0d mismatches. First mismatch occurred at time %0d.", "root", stats1.errors_root, stats1.errortime_root);
        else $display("Hint: Output '%s' has no mismatches.", "root");

        if (stats1.errors_done) $display("Hint: Output '%s' has %0d mismatches. First mismatch occurred at time %0d.", "done", stats1.errors_done, stats1.errortime_done);
        else $display("Hint: Output '%s' has no mismatches.", "done");

        $display("Hint: Total mismatched samples is %1d out of %1d samples\n", stats1.errors, stats1.clocks);
        $display("Simulation finished at %0d ps", $time);
        $display("Mismatches: %1d in %1d samples", stats1.errors, stats1.clocks);
    end

    // Verification: XORs on the right makes any X in good_vector match anything, but X in dut_vector will only match X.
    assign tb_match =
        ( { root_ref, done_ref }
          === ( { root_ref, done_ref } ^ { root_dut, done_dut } ^ { root_ref, done_ref } ) );

    // Use explicit sensitivity list here. @(*) causes NetProc::nex_input() to be called when trying to compute
    // the sensitivity list of the @(strobe) process, which isn't implemented.
    always @(posedge clk, negedge clk) begin

        stats1.clocks++;
        if (!tb_match) begin
            if (stats1.errors == 0) stats1.errortime = $time;
            stats1.errors++;
        end
        if (root_ref !== ( root_ref ^ root_dut ^ root_ref ))
        begin if (stats1.errors_root == 0) stats1.errortime_root = $time;
            stats1.errors_root = stats1.errors_root+1'b1; end

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

