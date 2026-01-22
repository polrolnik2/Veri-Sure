`timescale 1 ps/1 ps
`define OK 12
`define INCORRECT 13


module stimulus_gen (
    input clk,
    output logic reset,
    output logic sig_in,
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

    int period;
    int cnt;

    initial begin
        reset <= 1'b1;
        sig_in <= 1'b0;
        period = 2;
        cnt = 0;
        @(negedge clk) wavedrom_start("Frequency meter (64-cycle window)");

        repeat(3) @(posedge clk);
        @(negedge clk) reset <= 1'b0;

        // Change the input toggle period occasionally.
        repeat(600) @(negedge clk) begin
            cnt = cnt + 1;
            if (cnt >= period) begin
                cnt = 0;
                sig_in <= ~sig_in;
            end
            if (!($random & 63)) begin
                period = (($random % 10) + 1);
                if (period < 1) period = 1;
            end
        end

        wavedrom_stop();
        repeat(80) @(posedge clk, negedge clk) sig_in <= $random;
        $finish;
    end

endmodule

module tb();

    typedef struct packed {
        int errors;
        int errortime;
        int errors_freq_count;
        int errortime_freq_count;
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
    logic sig_in;
    logic [15:0] freq_ref;
    logic done_ref;
    logic [15:0] freq_dut;
    logic done_dut;

    initial begin
        $dumpfile("wave.vcd");
        $dumpvars(1, stim1.clk, tb_mismatch ,clk,reset,sig_in,freq_ref,done_ref,freq_dut,done_dut );
    end


    wire tb_match;       // Verification
    wire tb_mismatch = ~tb_match;

    stimulus_gen stim1 (
        .clk,
        .* ,
        .reset,
        .sig_in );
    RefModule good1 (
        .clk,
        .reset,
        .sig_in,
        .freq_count(freq_ref),
        .done(done_ref) );

    TopModule top_module1 (
        .clk,
        .reset,
        .sig_in,
        .freq_count(freq_dut),
        .done(done_dut) );


    bit strobe = 0;
    task wait_for_end_of_timestep;
        repeat(5) begin
            strobe <= !strobe;  // Try to delay until the very end of the time step.
            @(strobe);
        end
    endtask


    final begin
        if (stats1.errors_freq_count) $display("Hint: Output '%s' has %0d mismatches. First mismatch occurred at time %0d.", "freq_count", stats1.errors_freq_count, stats1.errortime_freq_count);
        else $display("Hint: Output '%s' has no mismatches.", "freq_count");

        if (stats1.errors_done) $display("Hint: Output '%s' has %0d mismatches. First mismatch occurred at time %0d.", "done", stats1.errors_done, stats1.errortime_done);
        else $display("Hint: Output '%s' has no mismatches.", "done");

        $display("Hint: Total mismatched samples is %1d out of %1d samples\n", stats1.errors, stats1.clocks);
        $display("Simulation finished at %0d ps", $time);
        $display("Mismatches: %1d in %1d samples", stats1.errors, stats1.clocks);
    end

    // Verification: XORs on the right makes any X in good_vector match anything, but X in dut_vector will only match X.
    assign tb_match = ( { freq_ref, done_ref } === ( { freq_ref, done_ref } ^ { freq_dut, done_dut } ^ { freq_ref, done_ref } ) );
    // Use explicit sensitivity list here. @(*) causes NetProc::nex_input() to be called when trying to compute
    // the sensitivity list of the @(strobe) process, which isn't implemented.
    always @(posedge clk, negedge clk) begin

        stats1.clocks++;
        if (!tb_match) begin
            if (stats1.errors == 0) stats1.errortime = $time;
            stats1.errors++;
        end
        if (freq_ref !== ( freq_ref ^ freq_dut ^ freq_ref ))
        begin if (stats1.errors_freq_count == 0) stats1.errortime_freq_count = $time;
            stats1.errors_freq_count = stats1.errors_freq_count+1'b1; end

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

