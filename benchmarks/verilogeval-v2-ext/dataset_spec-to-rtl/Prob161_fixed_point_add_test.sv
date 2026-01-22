`timescale 1 ps/1 ps
`define OK 12
`define INCORRECT 13


module stimulus_gen (
    input clk,
    output logic [31:0] a,
    output logic [31:0] b,
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
        {a, b} <= 64'd0;
        @(negedge clk) wavedrom_start("Q15.16 saturating add");

        // Directed corner cases (exercise saturation).
        @(posedge clk) begin a <= 32'h7FFF_FFFF; b <= 32'h0000_0001; end  // + overflow
        @(posedge clk) begin a <= 32'h8000_0000; b <= 32'hFFFF_FFFF; end  // - overflow
        @(posedge clk) begin a <= 32'h4000_0000; b <= 32'h4000_0000; end  // + overflow via sign flip
        @(posedge clk) begin a <= 32'h8000_0000; b <= 32'h8000_0000; end  // - overflow
        @(posedge clk) begin a <= 32'h0001_0000; b <= 32'h0001_0000; end  // 1.0 + 1.0
        @(posedge clk) begin a <= 32'hFFFF_0000; b <= 32'h0001_0000; end  // -1.0 + 1.0 = 0

        repeat(20) @(posedge clk) begin
            a <= $random;
            b <= $random;
        end

        wavedrom_stop();

        repeat(80) @(posedge clk, negedge clk) begin
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

    logic [31:0] a;
    logic [31:0] b;
    logic [31:0] sum_ref;
    logic [31:0] sum_dut;

    initial begin
        $dumpfile("wave.vcd");
        $dumpvars(1, stim1.clk, tb_mismatch ,a,b,sum_ref,sum_dut );
    end


    wire tb_match;       // Verification
    wire tb_mismatch = ~tb_match;

    stimulus_gen stim1 (
        .clk,
        .* ,
        .a,
        .b );
    RefModule good1 (
        .a,
        .b,
        .sum(sum_ref) );

    TopModule top_module1 (
        .a,
        .b,
        .sum(sum_dut) );


    bit strobe = 0;
    task wait_for_end_of_timestep;
        repeat(5) begin
            strobe <= !strobe;  // Try to delay until the very end of the time step.
            @(strobe);
        end
    endtask


    final begin
        if (stats1.errors_sum) $display("Hint: Output '%s' has %0d mismatches. First mismatch occurred at time %0d.", "sum", stats1.errors_sum, stats1.errortime_sum);
        else $display("Hint: Output '%s' has no mismatches.", "sum");

        $display("Hint: Total mismatched samples is %1d out of %1d samples\n", stats1.errors, stats1.clocks);
        $display("Simulation finished at %0d ps", $time);
        $display("Mismatches: %1d in %1d samples", stats1.errors, stats1.clocks);
    end

    // Verification: XORs on the right makes any X in good_vector match anything, but X in dut_vector will only match X.
    assign tb_match = ( { sum_ref } === ( { sum_ref } ^ { sum_dut } ^ { sum_ref } ) );
    // Use explicit sensitivity list here. @(*) causes NetProc::nex_input() to be called when trying to compute
    // the sensitivity list of the @(strobe) process, which isn't implemented.
    always @(posedge clk, negedge clk) begin

        stats1.clocks++;
        if (!tb_match) begin
            if (stats1.errors == 0) stats1.errortime = $time;
            stats1.errors++;
        end
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

