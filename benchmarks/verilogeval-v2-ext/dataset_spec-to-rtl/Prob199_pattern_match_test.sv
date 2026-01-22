`timescale 1 ps/1 ps
`define OK 12
`define INCORRECT 13


module stimulus_gen (
    input clk,
    output logic reset,
    output logic in_bit,
    output logic [7:0] pattern,
    output logic [3:0] pattern_len,
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

    task automatic feed_bits(input [31:0] bits, input int nbits);
        int i;
        for (i = nbits-1; i >= 0; i = i - 1) begin
            @(negedge clk);
            in_bit <= bits[i];
        end
    endtask

    initial begin
        reset <= 1'b1;
        in_bit <= 1'b0;
        pattern <= 8'd0;
        pattern_len <= 4'd0;
        @(negedge clk) wavedrom_start("Variable-length pattern match");

        repeat(2) @(posedge clk);
        @(negedge clk) reset <= 1'b0;

        // Directed: match pattern 1101 (len=4).
        @(negedge clk) begin
            pattern <= 8'b0000_1101;
            pattern_len <= 4'd4;
        end
        feed_bits(32'b1101, 4);        // should match once
        feed_bits(32'b0001101, 7);     // should match once at the end

        // Random patterns and bits.
        repeat(120) begin
            @(negedge clk);
            in_bit <= $random;
            pattern <= $random;
            pattern_len <= ($random % 10); // includes invalid 0 and >8
        end

        wavedrom_stop();
        repeat(40) @(posedge clk, negedge clk) begin
            in_bit <= $random;
            pattern <= $random;
            pattern_len <= ($random % 10);
        end
        $finish;
    end

endmodule

module tb();

    typedef struct packed {
        int errors;
        int errortime;
        int errors_match;
        int errortime_match;

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
    logic in_bit;
    logic [7:0] pattern;
    logic [3:0] pattern_len;
    logic match_ref;
    logic match_dut;

    initial begin
        $dumpfile("wave.vcd");
        $dumpvars(1, stim1.clk, tb_mismatch ,clk,reset,in_bit,pattern,pattern_len,match_ref,match_dut );
    end


    wire tb_match;       // Verification
    wire tb_mismatch = ~tb_match;

    stimulus_gen stim1 (
        .clk,
        .* ,
        .reset,
        .in_bit,
        .pattern,
        .pattern_len );
    RefModule good1 (
        .clk,
        .reset,
        .in_bit,
        .pattern,
        .pattern_len,
        .match(match_ref) );

    TopModule top_module1 (
        .clk,
        .reset,
        .in_bit,
        .pattern,
        .pattern_len,
        .match(match_dut) );


    bit strobe = 0;
    task wait_for_end_of_timestep;
        repeat(5) begin
            strobe <= !strobe;  // Try to delay until the very end of the time step.
            @(strobe);
        end
    endtask


    final begin
        if (stats1.errors_match) $display("Hint: Output '%s' has %0d mismatches. First mismatch occurred at time %0d.", "match", stats1.errors_match, stats1.errortime_match);
        else $display("Hint: Output '%s' has no mismatches.", "match");

        $display("Hint: Total mismatched samples is %1d out of %1d samples\n", stats1.errors, stats1.clocks);
        $display("Simulation finished at %0d ps", $time);
        $display("Mismatches: %1d in %1d samples", stats1.errors, stats1.clocks);
    end

    // Verification: XORs on the right makes any X in good_vector match anything, but X in dut_vector will only match X.
    assign tb_match = ( { match_ref } === ( { match_ref } ^ { match_dut } ^ { match_ref } ) );
    // Use explicit sensitivity list here. @(*) causes NetProc::nex_input() to be called when trying to compute
    // the sensitivity list of the @(strobe) process, which isn't implemented.
    always @(posedge clk, negedge clk) begin

        stats1.clocks++;
        if (!tb_match) begin
            if (stats1.errors == 0) stats1.errortime = $time;
            stats1.errors++;
        end
        if (match_ref !== ( match_ref ^ match_dut ^ match_ref ))
        begin if (stats1.errors_match == 0) stats1.errortime_match = $time;
            stats1.errors_match = stats1.errors_match+1'b1; end

    end

   // add timeout after 100K cycles
   initial begin
     #1000000
     $display("TIMEOUT");
     $finish();
   end

endmodule

