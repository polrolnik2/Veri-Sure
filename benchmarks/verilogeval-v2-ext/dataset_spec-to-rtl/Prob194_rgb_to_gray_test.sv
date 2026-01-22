`timescale 1 ps/1 ps
`define OK 12
`define INCORRECT 13


module stimulus_gen (
    input clk,
    output logic [7:0] r,
    output logic [7:0] g,
    output logic [7:0] b,
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
        {r,g,b} <= 24'd0;
        @(negedge clk) wavedrom_start("RGB to grayscale (fixed-point)");

        // Directed colors.
        @(posedge clk) begin r <= 8'h00; g <= 8'h00; b <= 8'h00; end  // black
        @(posedge clk) begin r <= 8'hFF; g <= 8'hFF; b <= 8'hFF; end  // white
        @(posedge clk) begin r <= 8'hFF; g <= 8'h00; b <= 8'h00; end  // red
        @(posedge clk) begin r <= 8'h00; g <= 8'hFF; b <= 8'h00; end  // green
        @(posedge clk) begin r <= 8'h00; g <= 8'h00; b <= 8'hFF; end  // blue

        repeat(20) @(posedge clk) {r,g,b} <= $random;
        wavedrom_stop();
        repeat(120) @(posedge clk, negedge clk) {r,g,b} <= $random;
        $finish;
    end

endmodule

module tb();

    typedef struct packed {
        int errors;
        int errortime;
        int errors_gray;
        int errortime_gray;

        int clocks;
    } stats;

    stats stats1;


    wire[511:0] wavedrom_title;
    wire wavedrom_enable;
    int wavedrom_hide_after_time;

    reg clk=0;
    initial forever
        #5 clk = ~clk;

    logic [7:0] r;
    logic [7:0] g;
    logic [7:0] b;
    logic [7:0] gray_ref;
    logic [7:0] gray_dut;

    initial begin
        $dumpfile("wave.vcd");
        $dumpvars(1, stim1.clk, tb_mismatch ,r,g,b,gray_ref,gray_dut );
    end


    wire tb_match;       // Verification
    wire tb_mismatch = ~tb_match;

    stimulus_gen stim1 (
        .clk,
        .* ,
        .r,
        .g,
        .b );
    RefModule good1 (
        .r,
        .g,
        .b,
        .gray(gray_ref) );

    TopModule top_module1 (
        .r,
        .g,
        .b,
        .gray(gray_dut) );


    bit strobe = 0;
    task wait_for_end_of_timestep;
        repeat(5) begin
            strobe <= !strobe;  // Try to delay until the very end of the time step.
            @(strobe);
        end
    endtask


    final begin
        if (stats1.errors_gray) $display("Hint: Output '%s' has %0d mismatches. First mismatch occurred at time %0d.", "gray", stats1.errors_gray, stats1.errortime_gray);
        else $display("Hint: Output '%s' has no mismatches.", "gray");

        $display("Hint: Total mismatched samples is %1d out of %1d samples\n", stats1.errors, stats1.clocks);
        $display("Simulation finished at %0d ps", $time);
        $display("Mismatches: %1d in %1d samples", stats1.errors, stats1.clocks);
    end

    // Verification: XORs on the right makes any X in good_vector match anything, but X in dut_vector will only match X.
    assign tb_match = ( { gray_ref } === ( { gray_ref } ^ { gray_dut } ^ { gray_ref } ) );
    // Use explicit sensitivity list here. @(*) causes NetProc::nex_input() to be called when trying to compute
    // the sensitivity list of the @(strobe) process, which isn't implemented.
    always @(posedge clk, negedge clk) begin

        stats1.clocks++;
        if (!tb_match) begin
            if (stats1.errors == 0) stats1.errortime = $time;
            stats1.errors++;
        end
        if (gray_ref !== ( gray_ref ^ gray_dut ^ gray_ref ))
        begin if (stats1.errors_gray == 0) stats1.errortime_gray = $time;
            stats1.errors_gray = stats1.errors_gray+1'b1; end

    end

   // add timeout after 100K cycles
   initial begin
     #1000000
     $display("TIMEOUT");
     $finish();
   end

endmodule

