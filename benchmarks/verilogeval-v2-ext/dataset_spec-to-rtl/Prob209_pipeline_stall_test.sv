`timescale 1 ps/1 ps
`define OK 12
`define INCORRECT 13


module stimulus_gen (
    input clk,
    output logic reset,
    output logic stall,
    output logic valid_in,
    output logic [15:0] a,
    output logic [15:0] b,
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
        stall <= 1'b0;
        valid_in <= 1'b0;
        {a, b} <= 32'd0;
        @(negedge clk) wavedrom_start("2-stage pipelined adder with stall");

        repeat(3) @(posedge clk);
        @(negedge clk) reset <= 1'b0;

        // Random traffic with occasional stalls.
        repeat(400) @(negedge clk) begin
            stall <= !($random & 7);
            valid_in <= $random;
            a <= $random;
            b <= $random;
        end

        wavedrom_stop();
        repeat(80) @(posedge clk, negedge clk) begin
            stall <= $random;
            valid_in <= $random;
            a <= $random;
            b <= $random;
        end
        $finish;
    end

endmodule

module tb();

    typedef struct packed {
        int errors;
        int errortime;
        int errors_valid_out;
        int errortime_valid_out;
        int errors_sum;
        int errortime_sum;

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
    logic stall;
    logic valid_in;
    logic [15:0] a;
    logic [15:0] b;
    logic valid_ref;
    logic [16:0] sum_ref;
    logic valid_dut;
    logic [16:0] sum_dut;

    initial begin
        $dumpfile("wave.vcd");
        $dumpvars(1, stim1.clk, tb_mismatch ,clk,reset,stall,valid_in,a,b,valid_ref,sum_ref,valid_dut,sum_dut );
    end


    wire tb_match;       // Verification
    wire tb_mismatch = ~tb_match;

    stimulus_gen stim1 (
        .clk,
        .* ,
        .reset,
        .stall,
        .valid_in,
        .a,
        .b );
    RefModule good1 (
        .clk,
        .reset,
        .stall,
        .valid_in,
        .a,
        .b,
        .valid_out(valid_ref),
        .sum(sum_ref) );

    TopModule top_module1 (
        .clk,
        .reset,
        .stall,
        .valid_in,
        .a,
        .b,
        .valid_out(valid_dut),
        .sum(sum_dut) );


    bit strobe = 0;
    task wait_for_end_of_timestep;
        repeat(5) begin
            strobe <= !strobe;  // Try to delay until the very end of the time step.
            @(strobe);
        end
    endtask


    final begin
        if (stats1.errors_valid_out) $display("Hint: Output '%s' has %0d mismatches. First mismatch occurred at time %0d.", "valid_out", stats1.errors_valid_out, stats1.errortime_valid_out);
        else $display("Hint: Output '%s' has no mismatches.", "valid_out");

        if (stats1.errors_sum) $display("Hint: Output '%s' has %0d mismatches. First mismatch occurred at time %0d.", "sum", stats1.errors_sum, stats1.errortime_sum);
        else $display("Hint: Output '%s' has no mismatches.", "sum");

        $display("Hint: Total mismatched samples is %1d out of %1d samples\n", stats1.errors, stats1.clocks);
        $display("Simulation finished at %0d ps", $time);
        $display("Mismatches: %1d in %1d samples", stats1.errors, stats1.clocks);
    end

    // Verification: XORs on the right makes any X in good_vector match anything, but X in dut_vector will only match X.
    assign tb_match = ( { valid_ref, sum_ref } === ( { valid_ref, sum_ref } ^ { valid_dut, sum_dut } ^ { valid_ref, sum_ref } ) );
    // Use explicit sensitivity list here. @(*) causes NetProc::nex_input() to be called when trying to compute
    // the sensitivity list of the @(strobe) process, which isn't implemented.
    always @(posedge clk, negedge clk) begin

        stats1.clocks++;
        if (!tb_match) begin
            if (stats1.errors == 0) stats1.errortime = $time;
            stats1.errors++;
        end
        if (valid_ref !== ( valid_ref ^ valid_dut ^ valid_ref ))
        begin if (stats1.errors_valid_out == 0) stats1.errortime_valid_out = $time;
            stats1.errors_valid_out = stats1.errors_valid_out+1'b1; end

        if (sum_ref !== ( sum_ref ^ sum_dut ^ sum_ref ))
        begin if (stats1.errors_sum == 0) stats1.errortime_sum = $time;
            stats1.errors_sum = stats1.errors_sum+1'b1; end

    end

   // add timeout after 100K cycles
   initial begin
     #1000000
     $display("TIMEOUT");
     $finish();
   end

endmodule

