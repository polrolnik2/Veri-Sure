`timescale 1 ps/1 ps
`define OK 12
`define INCORRECT 13


module stimulus_gen (
    input clk,
    output logic reset,
    output logic [3:0] req,
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
        req <= 4'b0000;

        @(negedge clk) wavedrom_start("Round-robin arbiter (4 req)");
        repeat(2) @(posedge clk);
        reset <= 1'b0;

        // Directed patterns.
        @(posedge clk) req <= 4'b1111;
        repeat(10) @(posedge clk) req <= 4'b1111;
        @(posedge clk) req <= 4'b0101;
        repeat(10) @(posedge clk) req <= 4'b0101;
        @(posedge clk) req <= 4'b0000;
        repeat(4) @(posedge clk) req <= 4'b0000;

        // Random patterns.
        repeat(400) @(posedge clk) begin
            req <= $random;
        end

        wavedrom_stop();
        repeat(40) @(posedge clk, negedge clk) begin
            req <= $random;
        end
        $finish;
    end

endmodule

module tb();

    typedef struct packed {
        int errors;
        int errortime;
        int errors_grant;
        int errortime_grant;

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
    logic [3:0] req;
    logic [3:0] grant_ref;
    logic [3:0] grant_dut;

    initial begin
        $dumpfile("wave.vcd");
        $dumpvars(1, stim1.clk, tb_mismatch ,clk,reset,req,grant_ref,grant_dut );
    end


    wire tb_match;       // Verification
    wire tb_mismatch = ~tb_match;

    stimulus_gen stim1 (
        .clk,
        .* ,
        .reset,
        .req );
    RefModule good1 (
        .clk,
        .reset,
        .req,
        .grant(grant_ref) );

    TopModule top_module1 (
        .clk,
        .reset,
        .req,
        .grant(grant_dut) );


    bit strobe = 0;
    task wait_for_end_of_timestep;
        repeat(5) begin
            strobe <= !strobe;  // Try to delay until the very end of the time step.
            @(strobe);
        end
    endtask


    final begin
        if (stats1.errors_grant) $display("Hint: Output '%s' has %0d mismatches. First mismatch occurred at time %0d.", "grant", stats1.errors_grant, stats1.errortime_grant);
        else $display("Hint: Output '%s' has no mismatches.", "grant");

        $display("Hint: Total mismatched samples is %1d out of %1d samples\n", stats1.errors, stats1.clocks);
        $display("Simulation finished at %0d ps", $time);
        $display("Mismatches: %1d in %1d samples", stats1.errors, stats1.clocks);
    end

    // Verification: XORs on the right makes any X in good_vector match anything, but X in dut_vector will only match X.
    assign tb_match = ( { grant_ref } === ( { grant_ref } ^ { grant_dut } ^ { grant_ref } ) );
    // Use explicit sensitivity list here. @(*) causes NetProc::nex_input() to be called when trying to compute
    // the sensitivity list of the @(strobe) process, which isn't implemented.
    always @(posedge clk, negedge clk) begin

        stats1.clocks++;
        if (!tb_match) begin
            if (stats1.errors == 0) stats1.errortime = $time;
            stats1.errors++;
        end
        if (grant_ref !== ( grant_ref ^ grant_dut ^ grant_ref ))
        begin if (stats1.errors_grant == 0) stats1.errortime_grant = $time;
            stats1.errors_grant = stats1.errors_grant+1'b1; end

    end

   // add timeout after 100K cycles
   initial begin
     #1500000
     $display("TIMEOUT");
     $finish();
   end

endmodule

