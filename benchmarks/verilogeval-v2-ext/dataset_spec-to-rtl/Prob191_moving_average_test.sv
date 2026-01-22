`timescale 1 ps/1 ps
`define OK 12
`define INCORRECT 13


module stimulus_gen (
    input clk,
    output logic reset,
    output logic [7:0] sample_in,
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
        sample_in <= 8'd0;
        @(negedge clk) wavedrom_start("8-sample moving average");

        repeat(2) @(posedge clk);
        @(negedge clk) reset <= 1'b0;

        // Directed sequence.
        @(negedge clk) sample_in <= 8'd0;
        @(negedge clk) sample_in <= 8'd8;
        @(negedge clk) sample_in <= 8'd16;
        @(negedge clk) sample_in <= 8'd24;
        @(negedge clk) sample_in <= 8'd32;

        // Random stream.
        repeat(140) @(negedge clk) sample_in <= $random;

        wavedrom_stop();
        repeat(40) @(posedge clk, negedge clk) sample_in <= $random;
        $finish;
    end

endmodule

module tb();

    typedef struct packed {
        int errors;
        int errortime;
        int errors_avg_out;
        int errortime_avg_out;

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
    logic [7:0] sample_in;
    logic [7:0] avg_out_ref;
    logic [7:0] avg_out_dut;

    initial begin
        $dumpfile("wave.vcd");
        $dumpvars(1, stim1.clk, tb_mismatch ,clk,reset,sample_in,avg_out_ref,avg_out_dut );
    end


    wire tb_match;       // Verification
    wire tb_mismatch = ~tb_match;

    stimulus_gen stim1 (
        .clk,
        .* ,
        .reset,
        .sample_in );
    RefModule good1 (
        .clk,
        .reset,
        .sample_in,
        .avg_out(avg_out_ref) );

    TopModule top_module1 (
        .clk,
        .reset,
        .sample_in,
        .avg_out(avg_out_dut) );


    bit strobe = 0;
    task wait_for_end_of_timestep;
        repeat(5) begin
            strobe <= !strobe;  // Try to delay until the very end of the time step.
            @(strobe);
        end
    endtask


    final begin
        if (stats1.errors_avg_out) $display("Hint: Output '%s' has %0d mismatches. First mismatch occurred at time %0d.", "avg_out", stats1.errors_avg_out, stats1.errortime_avg_out);
        else $display("Hint: Output '%s' has no mismatches.", "avg_out");

        $display("Hint: Total mismatched samples is %1d out of %1d samples\n", stats1.errors, stats1.clocks);
        $display("Simulation finished at %0d ps", $time);
        $display("Mismatches: %1d in %1d samples", stats1.errors, stats1.clocks);
    end

    // Verification: XORs on the right makes any X in good_vector match anything, but X in dut_vector will only match X.
    assign tb_match = ( { avg_out_ref } === ( { avg_out_ref } ^ { avg_out_dut } ^ { avg_out_ref } ) );
    // Use explicit sensitivity list here. @(*) causes NetProc::nex_input() to be called when trying to compute
    // the sensitivity list of the @(strobe) process, which isn't implemented.
    always @(posedge clk, negedge clk) begin

        stats1.clocks++;
        if (!tb_match) begin
            if (stats1.errors == 0) stats1.errortime = $time;
            stats1.errors++;
        end
        if (avg_out_ref !== ( avg_out_ref ^ avg_out_dut ^ avg_out_ref ))
        begin if (stats1.errors_avg_out == 0) stats1.errortime_avg_out = $time;
            stats1.errors_avg_out = stats1.errors_avg_out+1'b1; end

    end

   // add timeout after 100K cycles
   initial begin
     #1000000
     $display("TIMEOUT");
     $finish();
   end

endmodule

