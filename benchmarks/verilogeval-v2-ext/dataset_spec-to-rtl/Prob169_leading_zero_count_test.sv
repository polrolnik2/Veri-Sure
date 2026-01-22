`timescale 1 ps/1 ps
`define OK 12
`define INCORRECT 13


module stimulus_gen (
    input clk,
    output logic [31:0] x,
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
        x <= 32'd0;
        @(negedge clk) wavedrom_start("Leading zero count (32-bit)");

        // Directed tests.
        @(posedge clk) x <= 32'h0000_0000; // 32
        @(posedge clk) x <= 32'h8000_0000; // 0
        @(posedge clk) x <= 32'h4000_0000; // 1
        @(posedge clk) x <= 32'h0000_0001; // 31
        @(posedge clk) x <= 32'h0001_0000; // 15
        @(posedge clk) x <= 32'h00F0_0000; // 8

        repeat(30) @(posedge clk) x <= $random;
        wavedrom_stop();
        repeat(70) @(posedge clk, negedge clk) x <= $random;
        $finish;
    end

endmodule

module tb();

    typedef struct packed {
        int errors;
        int errortime;
        int errors_count;
        int errortime_count;

        int clocks;
    } stats;

    stats stats1;


    wire[511:0] wavedrom_title;
    wire wavedrom_enable;
    int wavedrom_hide_after_time;

    reg clk=0;
    initial forever
        #5 clk = ~clk;

    logic [31:0] x;
    logic [5:0] count_ref;
    logic [5:0] count_dut;

    initial begin
        $dumpfile("wave.vcd");
        $dumpvars(1, stim1.clk, tb_mismatch ,x,count_ref,count_dut );
    end


    wire tb_match;       // Verification
    wire tb_mismatch = ~tb_match;

    stimulus_gen stim1 (
        .clk,
        .* ,
        .x );
    RefModule good1 (
        .x,
        .count(count_ref) );

    TopModule top_module1 (
        .x,
        .count(count_dut) );


    bit strobe = 0;
    task wait_for_end_of_timestep;
        repeat(5) begin
            strobe <= !strobe;  // Try to delay until the very end of the time step.
            @(strobe);
        end
    endtask


    final begin
        if (stats1.errors_count) $display("Hint: Output '%s' has %0d mismatches. First mismatch occurred at time %0d.", "count", stats1.errors_count, stats1.errortime_count);
        else $display("Hint: Output '%s' has no mismatches.", "count");

        $display("Hint: Total mismatched samples is %1d out of %1d samples\n", stats1.errors, stats1.clocks);
        $display("Simulation finished at %0d ps", $time);
        $display("Mismatches: %1d in %1d samples", stats1.errors, stats1.clocks);
    end

    // Verification: XORs on the right makes any X in good_vector match anything, but X in dut_vector will only match X.
    assign tb_match = ( { count_ref } === ( { count_ref } ^ { count_dut } ^ { count_ref } ) );
    // Use explicit sensitivity list here. @(*) causes NetProc::nex_input() to be called when trying to compute
    // the sensitivity list of the @(strobe) process, which isn't implemented.
    always @(posedge clk, negedge clk) begin

        stats1.clocks++;
        if (!tb_match) begin
            if (stats1.errors == 0) stats1.errortime = $time;
            stats1.errors++;
        end
        if (count_ref !== ( count_ref ^ count_dut ^ count_ref ))
        begin if (stats1.errors_count == 0) stats1.errortime_count = $time;
            stats1.errors_count = stats1.errors_count+1'b1; end

    end

   // add timeout after 100K cycles
   initial begin
     #1000000
     $display("TIMEOUT");
     $finish();
   end

endmodule

