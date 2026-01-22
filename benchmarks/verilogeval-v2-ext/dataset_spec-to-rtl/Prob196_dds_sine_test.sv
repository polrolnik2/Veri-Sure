`timescale 1 ps/1 ps
`define OK 12
`define INCORRECT 13


module stimulus_gen (
    input clk,
    output logic reset,
    output logic [15:0] phase_inc,
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
        phase_inc <= 16'd0;
        @(negedge clk) wavedrom_start("DDS sine (phase accumulator + LUT)");

        repeat(2) @(posedge clk);
        @(negedge clk) reset <= 1'b0;

        // Directed increments.
        @(negedge clk) phase_inc <= 16'd0;
        @(negedge clk) phase_inc <= 16'd1;
        @(negedge clk) phase_inc <= 16'd257;
        @(negedge clk) phase_inc <= 16'd1024;
        @(negedge clk) phase_inc <= 16'd4096;
        @(negedge clk) phase_inc <= 16'd12345;

        repeat(200) @(negedge clk) phase_inc <= $random;

        wavedrom_stop();
        repeat(80) @(posedge clk, negedge clk) phase_inc <= $random;
        $finish;
    end

endmodule

module tb();

    typedef struct packed {
        int errors;
        int errortime;
        int errors_sine_out;
        int errortime_sine_out;

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
    logic [15:0] phase_inc;
    logic signed [11:0] sine_ref;
    logic signed [11:0] sine_dut;

    initial begin
        $dumpfile("wave.vcd");
        $dumpvars(1, stim1.clk, tb_mismatch ,clk,reset,phase_inc,sine_ref,sine_dut );
    end


    wire tb_match;       // Verification
    wire tb_mismatch = ~tb_match;

    stimulus_gen stim1 (
        .clk,
        .* ,
        .reset,
        .phase_inc );
    RefModule good1 (
        .clk,
        .reset,
        .phase_inc,
        .sine_out(sine_ref) );

    TopModule top_module1 (
        .clk,
        .reset,
        .phase_inc,
        .sine_out(sine_dut) );


    bit strobe = 0;
    task wait_for_end_of_timestep;
        repeat(5) begin
            strobe <= !strobe;  // Try to delay until the very end of the time step.
            @(strobe);
        end
    endtask


    final begin
        if (stats1.errors_sine_out) $display("Hint: Output '%s' has %0d mismatches. First mismatch occurred at time %0d.", "sine_out", stats1.errors_sine_out, stats1.errortime_sine_out);
        else $display("Hint: Output '%s' has no mismatches.", "sine_out");

        $display("Hint: Total mismatched samples is %1d out of %1d samples\n", stats1.errors, stats1.clocks);
        $display("Simulation finished at %0d ps", $time);
        $display("Mismatches: %1d in %1d samples", stats1.errors, stats1.clocks);
    end

    // Verification: XORs on the right makes any X in good_vector match anything, but X in dut_vector will only match X.
    assign tb_match = ( { sine_ref } === ( { sine_ref } ^ { sine_dut } ^ { sine_ref } ) );
    // Use explicit sensitivity list here. @(*) causes NetProc::nex_input() to be called when trying to compute
    // the sensitivity list of the @(strobe) process, which isn't implemented.
    always @(posedge clk, negedge clk) begin

        stats1.clocks++;
        if (!tb_match) begin
            if (stats1.errors == 0) stats1.errortime = $time;
            stats1.errors++;
        end
        if (sine_ref !== ( sine_ref ^ sine_dut ^ sine_ref ))
        begin if (stats1.errors_sine_out == 0) stats1.errortime_sine_out = $time;
            stats1.errors_sine_out = stats1.errors_sine_out+1'b1; end

    end

   // add timeout after 100K cycles
   initial begin
     #1000000
     $display("TIMEOUT");
     $finish();
   end

endmodule

