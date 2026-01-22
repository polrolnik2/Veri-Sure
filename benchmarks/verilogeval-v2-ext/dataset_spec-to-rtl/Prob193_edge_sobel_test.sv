`timescale 1 ps/1 ps
`define OK 12
`define INCORRECT 13


module stimulus_gen (
    input clk,
    output logic [7:0] p00,
    output logic [7:0] p01,
    output logic [7:0] p02,
    output logic [7:0] p10,
    output logic [7:0] p11,
    output logic [7:0] p12,
    output logic [7:0] p20,
    output logic [7:0] p21,
    output logic [7:0] p22,
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
        {p00,p01,p02,p10,p11,p12,p20,p21,p22} <= '0;
        @(negedge clk) wavedrom_start("Sobel 3x3 edge operator");

        repeat(20) @(posedge clk) begin
            p00 <= $random; p01 <= $random; p02 <= $random;
            p10 <= $random; p11 <= $random; p12 <= $random;
            p20 <= $random; p21 <= $random; p22 <= $random;
        end

        wavedrom_stop();
        repeat(120) @(posedge clk, negedge clk) begin
            p00 <= $random; p01 <= $random; p02 <= $random;
            p10 <= $random; p11 <= $random; p12 <= $random;
            p20 <= $random; p21 <= $random; p22 <= $random;
        end
        $finish;
    end

endmodule

module tb();

    typedef struct packed {
        int errors;
        int errortime;
        int errors_gx;
        int errortime_gx;
        int errors_gy;
        int errortime_gy;
        int errors_mag;
        int errortime_mag;

        int clocks;
    } stats;

    stats stats1;


    wire[511:0] wavedrom_title;
    wire wavedrom_enable;
    int wavedrom_hide_after_time;

    reg clk=0;
    initial forever
        #5 clk = ~clk;

    logic [7:0] p00;
    logic [7:0] p01;
    logic [7:0] p02;
    logic [7:0] p10;
    logic [7:0] p11;
    logic [7:0] p12;
    logic [7:0] p20;
    logic [7:0] p21;
    logic [7:0] p22;

    logic signed [10:0] gx_ref;
    logic signed [10:0] gy_ref;
    logic [10:0] mag_ref;

    logic signed [10:0] gx_dut;
    logic signed [10:0] gy_dut;
    logic [10:0] mag_dut;

    initial begin
        $dumpfile("wave.vcd");
        $dumpvars(1, stim1.clk, tb_mismatch ,p00,p01,p02,p10,p11,p12,p20,p21,p22,gx_ref,gy_ref,mag_ref,gx_dut,gy_dut,mag_dut );
    end


    wire tb_match;       // Verification
    wire tb_mismatch = ~tb_match;

    stimulus_gen stim1 (
        .clk,
        .*  );
    RefModule good1 (
        .p00,
        .p01,
        .p02,
        .p10,
        .p11,
        .p12,
        .p20,
        .p21,
        .p22,
        .gx(gx_ref),
        .gy(gy_ref),
        .mag(mag_ref) );

    TopModule top_module1 (
        .p00,
        .p01,
        .p02,
        .p10,
        .p11,
        .p12,
        .p20,
        .p21,
        .p22,
        .gx(gx_dut),
        .gy(gy_dut),
        .mag(mag_dut) );


    bit strobe = 0;
    task wait_for_end_of_timestep;
        repeat(5) begin
            strobe <= !strobe;  // Try to delay until the very end of the time step.
            @(strobe);
        end
    endtask


    final begin
        if (stats1.errors_gx) $display("Hint: Output '%s' has %0d mismatches. First mismatch occurred at time %0d.", "gx", stats1.errors_gx, stats1.errortime_gx);
        else $display("Hint: Output '%s' has no mismatches.", "gx");

        if (stats1.errors_gy) $display("Hint: Output '%s' has %0d mismatches. First mismatch occurred at time %0d.", "gy", stats1.errors_gy, stats1.errortime_gy);
        else $display("Hint: Output '%s' has no mismatches.", "gy");

        if (stats1.errors_mag) $display("Hint: Output '%s' has %0d mismatches. First mismatch occurred at time %0d.", "mag", stats1.errors_mag, stats1.errortime_mag);
        else $display("Hint: Output '%s' has no mismatches.", "mag");

        $display("Hint: Total mismatched samples is %1d out of %1d samples\n", stats1.errors, stats1.clocks);
        $display("Simulation finished at %0d ps", $time);
        $display("Mismatches: %1d in %1d samples", stats1.errors, stats1.clocks);
    end

    // Verification: XORs on the right makes any X in good_vector match anything, but X in dut_vector will only match X.
    assign tb_match = ( { gx_ref, gy_ref, mag_ref } === ( { gx_ref, gy_ref, mag_ref } ^ { gx_dut, gy_dut, mag_dut } ^ { gx_ref, gy_ref, mag_ref } ) );
    // Use explicit sensitivity list here. @(*) causes NetProc::nex_input() to be called when trying to compute
    // the sensitivity list of the @(strobe) process, which isn't implemented.
    always @(posedge clk, negedge clk) begin

        stats1.clocks++;
        if (!tb_match) begin
            if (stats1.errors == 0) stats1.errortime = $time;
            stats1.errors++;
        end
        if (gx_ref !== ( gx_ref ^ gx_dut ^ gx_ref ))
        begin if (stats1.errors_gx == 0) stats1.errortime_gx = $time;
            stats1.errors_gx = stats1.errors_gx+1'b1; end

        if (gy_ref !== ( gy_ref ^ gy_dut ^ gy_ref ))
        begin if (stats1.errors_gy == 0) stats1.errortime_gy = $time;
            stats1.errors_gy = stats1.errors_gy+1'b1; end

        if (mag_ref !== ( mag_ref ^ mag_dut ^ mag_ref ))
        begin if (stats1.errors_mag == 0) stats1.errortime_mag = $time;
            stats1.errors_mag = stats1.errors_mag+1'b1; end

    end

   // add timeout after 100K cycles
   initial begin
     #1000000
     $display("TIMEOUT");
     $finish();
   end

endmodule

