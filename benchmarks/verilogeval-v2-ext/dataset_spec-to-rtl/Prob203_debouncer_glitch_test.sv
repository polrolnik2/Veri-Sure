`timescale 1 ps/1 ps
`define OK 12
`define INCORRECT 13


module stimulus_gen (
    input clk,
    output logic reset,
    output logic noisy,
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

    task automatic stable_level(input logic level, input int cycles);
        int i;
        for (i = 0; i < cycles; i = i + 1) begin
            @(negedge clk);
            noisy <= level;
        end
    endtask

    initial begin
        reset <= 1'b1;
        noisy <= 1'b0;
        @(negedge clk) wavedrom_start("Debouncer with glitch filter (8 samples)");

        repeat(3) @(posedge clk);
        @(negedge clk) reset <= 1'b0;

        // A few stable regions with glitches.
        stable_level(1'b0, 20);
        @(negedge clk) noisy <= 1'b1;  // short glitch
        @(negedge clk) noisy <= 1'b0;
        stable_level(1'b0, 20);

        stable_level(1'b1, 20);
        @(negedge clk) noisy <= 1'b0;  // short glitch
        @(negedge clk) noisy <= 1'b1;
        stable_level(1'b1, 20);

        // Random noisy toggling.
        repeat(200) @(negedge clk) noisy <= $random;

        wavedrom_stop();
        repeat(80) @(posedge clk, negedge clk) noisy <= $random;
        $finish;
    end

endmodule

module tb();

    typedef struct packed {
        int errors;
        int errortime;
        int errors_clean;
        int errortime_clean;

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
    logic noisy;
    logic clean_ref;
    logic clean_dut;

    initial begin
        $dumpfile("wave.vcd");
        $dumpvars(1, stim1.clk, tb_mismatch ,clk,reset,noisy,clean_ref,clean_dut );
    end


    wire tb_match;       // Verification
    wire tb_mismatch = ~tb_match;

    stimulus_gen stim1 (
        .clk,
        .* ,
        .reset,
        .noisy );
    RefModule good1 (
        .clk,
        .reset,
        .noisy,
        .clean(clean_ref) );

    TopModule top_module1 (
        .clk,
        .reset,
        .noisy,
        .clean(clean_dut) );


    bit strobe = 0;
    task wait_for_end_of_timestep;
        repeat(5) begin
            strobe <= !strobe;  // Try to delay until the very end of the time step.
            @(strobe);
        end
    endtask


    final begin
        if (stats1.errors_clean) $display("Hint: Output '%s' has %0d mismatches. First mismatch occurred at time %0d.", "clean", stats1.errors_clean, stats1.errortime_clean);
        else $display("Hint: Output '%s' has no mismatches.", "clean");

        $display("Hint: Total mismatched samples is %1d out of %1d samples\n", stats1.errors, stats1.clocks);
        $display("Simulation finished at %0d ps", $time);
        $display("Mismatches: %1d in %1d samples", stats1.errors, stats1.clocks);
    end

    // Verification: XORs on the right makes any X in good_vector match anything, but X in dut_vector will only match X.
    assign tb_match = ( { clean_ref } === ( { clean_ref } ^ { clean_dut } ^ { clean_ref } ) );
    // Use explicit sensitivity list here. @(*) causes NetProc::nex_input() to be called when trying to compute
    // the sensitivity list of the @(strobe) process, which isn't implemented.
    always @(posedge clk, negedge clk) begin

        stats1.clocks++;
        if (!tb_match) begin
            if (stats1.errors == 0) stats1.errortime = $time;
            stats1.errors++;
        end
        if (clean_ref !== ( clean_ref ^ clean_dut ^ clean_ref ))
        begin if (stats1.errors_clean == 0) stats1.errortime_clean = $time;
            stats1.errors_clean = stats1.errors_clean+1'b1; end

    end

   // add timeout after 100K cycles
   initial begin
     #1000000
     $display("TIMEOUT");
     $finish();
   end

endmodule

