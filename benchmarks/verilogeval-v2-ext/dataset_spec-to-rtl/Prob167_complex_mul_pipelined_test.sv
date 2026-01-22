`timescale 1 ps/1 ps
`define OK 12
`define INCORRECT 13


module stimulus_gen (
    input clk,
    output logic        reset,
    output logic        in_valid,
    output logic [15:0] a_re,
    output logic [15:0] a_im,
    output logic [15:0] b_re,
    output logic [15:0] b_im,
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
        in_valid <= 1'b0;
        a_re <= 16'd0;
        a_im <= 16'd0;
        b_re <= 16'd0;
        b_im <= 16'd0;

        @(negedge clk) wavedrom_start("Pipelined complex multiply (latency=3)");

        repeat(2) @(posedge clk);
        reset <= 1'b0;

        // Drive random traffic; inputs are updated on negedge to avoid races.
        repeat(140) @(negedge clk) begin
            in_valid <= $random;
            a_re <= $random;
            a_im <= $random;
            b_re <= $random;
            b_im <= $random;
        end

        wavedrom_stop();
        repeat(20) @(posedge clk, negedge clk) begin
            in_valid <= 1'b0;
            a_re <= $random;
            a_im <= $random;
            b_re <= $random;
            b_im <= $random;
        end
        $finish;
    end

endmodule

module tb();

    typedef struct packed {
        int errors;
        int errortime;
        int errors_out_re;
        int errortime_out_re;
        int errors_out_im;
        int errortime_out_im;
        int errors_out_valid;
        int errortime_out_valid;

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
    logic in_valid;
    logic [15:0] a_re;
    logic [15:0] a_im;
    logic [15:0] b_re;
    logic [15:0] b_im;

    logic [31:0] out_re_ref;
    logic [31:0] out_re_dut;
    logic [31:0] out_im_ref;
    logic [31:0] out_im_dut;
    logic out_valid_ref;
    logic out_valid_dut;

    initial begin
        $dumpfile("wave.vcd");
        $dumpvars(1, stim1.clk, tb_mismatch ,clk,reset,in_valid,a_re,a_im,b_re,b_im,out_re_ref,out_re_dut,out_im_ref,out_im_dut,out_valid_ref,out_valid_dut );
    end


    wire tb_match;       // Verification
    wire tb_mismatch = ~tb_match;

    stimulus_gen stim1 (
        .clk,
        .* ,
        .reset,
        .in_valid,
        .a_re,
        .a_im,
        .b_re,
        .b_im );
    RefModule good1 (
        .clk,
        .reset,
        .in_valid,
        .a_re,
        .a_im,
        .b_re,
        .b_im,
        .out_re(out_re_ref),
        .out_im(out_im_ref),
        .out_valid(out_valid_ref) );

    TopModule top_module1 (
        .clk,
        .reset,
        .in_valid,
        .a_re,
        .a_im,
        .b_re,
        .b_im,
        .out_re(out_re_dut),
        .out_im(out_im_dut),
        .out_valid(out_valid_dut) );


    bit strobe = 0;
    task wait_for_end_of_timestep;
        repeat(5) begin
            strobe <= !strobe;  // Try to delay until the very end of the time step.
            @(strobe);
        end
    endtask


    final begin
        if (stats1.errors_out_re) $display("Hint: Output '%s' has %0d mismatches. First mismatch occurred at time %0d.", "out_re", stats1.errors_out_re, stats1.errortime_out_re);
        else $display("Hint: Output '%s' has no mismatches.", "out_re");

        if (stats1.errors_out_im) $display("Hint: Output '%s' has %0d mismatches. First mismatch occurred at time %0d.", "out_im", stats1.errors_out_im, stats1.errortime_out_im);
        else $display("Hint: Output '%s' has no mismatches.", "out_im");

        if (stats1.errors_out_valid) $display("Hint: Output '%s' has %0d mismatches. First mismatch occurred at time %0d.", "out_valid", stats1.errors_out_valid, stats1.errortime_out_valid);
        else $display("Hint: Output '%s' has no mismatches.", "out_valid");

        $display("Hint: Total mismatched samples is %1d out of %1d samples\n", stats1.errors, stats1.clocks);
        $display("Simulation finished at %0d ps", $time);
        $display("Mismatches: %1d in %1d samples", stats1.errors, stats1.clocks);
    end

    // Verification: XORs on the right makes any X in good_vector match anything, but X in dut_vector will only match X.
    assign tb_match =
        ( { out_re_ref, out_im_ref, out_valid_ref }
          === ( { out_re_ref, out_im_ref, out_valid_ref }
                ^ { out_re_dut, out_im_dut, out_valid_dut }
                ^ { out_re_ref, out_im_ref, out_valid_ref } ) );

    // Use explicit sensitivity list here. @(*) causes NetProc::nex_input() to be called when trying to compute
    // the sensitivity list of the @(strobe) process, which isn't implemented.
    always @(posedge clk, negedge clk) begin

        stats1.clocks++;
        if (!tb_match) begin
            if (stats1.errors == 0) stats1.errortime = $time;
            stats1.errors++;
        end
        if (out_re_ref !== ( out_re_ref ^ out_re_dut ^ out_re_ref ))
        begin if (stats1.errors_out_re == 0) stats1.errortime_out_re = $time;
            stats1.errors_out_re = stats1.errors_out_re+1'b1; end

        if (out_im_ref !== ( out_im_ref ^ out_im_dut ^ out_im_ref ))
        begin if (stats1.errors_out_im == 0) stats1.errortime_out_im = $time;
            stats1.errors_out_im = stats1.errors_out_im+1'b1; end

        if (out_valid_ref !== ( out_valid_ref ^ out_valid_dut ^ out_valid_ref ))
        begin if (stats1.errors_out_valid == 0) stats1.errortime_out_valid = $time;
            stats1.errors_out_valid = stats1.errors_out_valid+1'b1; end

    end

   // add timeout after 100K cycles
   initial begin
     #1000000
     $display("TIMEOUT");
     $finish();
   end

endmodule

