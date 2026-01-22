`timescale 1 ps/1 ps
`define OK 12
`define INCORRECT 13


module stimulus_gen (
    input clk,
    output logic [31:0] a,
    output logic [31:0] b,
    output logic [3:0]  op,
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
        a <= 32'd0;
        b <= 32'd0;
        op <= 4'd0;
        @(negedge clk) wavedrom_start("32-bit general ALU");

        // A few directed op sweeps.
        @(posedge clk) begin a <= 32'h0000_0001; b <= 32'h0000_0001; op <= 4'd0; end // add
        @(posedge clk) begin a <= 32'h0000_0000; b <= 32'h0000_0001; op <= 4'd1; end // sub
        @(posedge clk) begin a <= 32'hF0F0_F0F0; b <= 32'h0FF0_0FF0; op <= 4'd2; end // and
        @(posedge clk) begin a <= 32'h8000_0000; b <= 32'h0000_0001; op <= 4'd7; end // sra
        @(posedge clk) begin a <= 32'h7FFF_FFFF; b <= 32'h0000_0001; op <= 4'd0; end // overflow add
        @(posedge clk) begin a <= 32'h8000_0000; b <= 32'h0000_0001; op <= 4'd1; end // overflow sub

        repeat(30) @(posedge clk) begin
            a <= $random;
            b <= $random;
            op <= $random;
        end
        wavedrom_stop();

        repeat(70) @(posedge clk, negedge clk) begin
            a <= $random;
            b <= $random;
            op <= $random;
        end
        $finish;
    end

endmodule

module tb();

    typedef struct packed {
        int errors;
        int errortime;
        int errors_result;
        int errortime_result;
        int errors_zero;
        int errortime_zero;
        int errors_carry;
        int errortime_carry;
        int errors_overflow;
        int errortime_overflow;
        int errors_negative;
        int errortime_negative;

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
    logic [3:0]  op;
    logic [31:0] result_ref;
    logic [31:0] result_dut;
    logic zero_ref;
    logic zero_dut;
    logic carry_ref;
    logic carry_dut;
    logic overflow_ref;
    logic overflow_dut;
    logic negative_ref;
    logic negative_dut;

    initial begin
        $dumpfile("wave.vcd");
        $dumpvars(1, stim1.clk, tb_mismatch ,a,b,op,result_ref,result_dut,zero_ref,zero_dut,carry_ref,carry_dut,overflow_ref,overflow_dut,negative_ref,negative_dut );
    end


    wire tb_match;       // Verification
    wire tb_mismatch = ~tb_match;

    stimulus_gen stim1 (
        .clk,
        .* ,
        .a,
        .b,
        .op );
    RefModule good1 (
        .a,
        .b,
        .op,
        .result(result_ref),
        .zero(zero_ref),
        .carry(carry_ref),
        .overflow(overflow_ref),
        .negative(negative_ref) );

    TopModule top_module1 (
        .a,
        .b,
        .op,
        .result(result_dut),
        .zero(zero_dut),
        .carry(carry_dut),
        .overflow(overflow_dut),
        .negative(negative_dut) );


    bit strobe = 0;
    task wait_for_end_of_timestep;
        repeat(5) begin
            strobe <= !strobe;  // Try to delay until the very end of the time step.
            @(strobe);
        end
    endtask


    final begin
        if (stats1.errors_result) $display("Hint: Output '%s' has %0d mismatches. First mismatch occurred at time %0d.", "result", stats1.errors_result, stats1.errortime_result);
        else $display("Hint: Output '%s' has no mismatches.", "result");

        if (stats1.errors_zero) $display("Hint: Output '%s' has %0d mismatches. First mismatch occurred at time %0d.", "zero", stats1.errors_zero, stats1.errortime_zero);
        else $display("Hint: Output '%s' has no mismatches.", "zero");

        if (stats1.errors_carry) $display("Hint: Output '%s' has %0d mismatches. First mismatch occurred at time %0d.", "carry", stats1.errors_carry, stats1.errortime_carry);
        else $display("Hint: Output '%s' has no mismatches.", "carry");

        if (stats1.errors_overflow) $display("Hint: Output '%s' has %0d mismatches. First mismatch occurred at time %0d.", "overflow", stats1.errors_overflow, stats1.errortime_overflow);
        else $display("Hint: Output '%s' has no mismatches.", "overflow");

        if (stats1.errors_negative) $display("Hint: Output '%s' has %0d mismatches. First mismatch occurred at time %0d.", "negative", stats1.errors_negative, stats1.errortime_negative);
        else $display("Hint: Output '%s' has no mismatches.", "negative");

        $display("Hint: Total mismatched samples is %1d out of %1d samples\n", stats1.errors, stats1.clocks);
        $display("Simulation finished at %0d ps", $time);
        $display("Mismatches: %1d in %1d samples", stats1.errors, stats1.clocks);
    end

    // Verification: XORs on the right makes any X in good_vector match anything, but X in dut_vector will only match X.
    assign tb_match =
        ( { result_ref, zero_ref, carry_ref, overflow_ref, negative_ref }
          === ( { result_ref, zero_ref, carry_ref, overflow_ref, negative_ref }
                ^ { result_dut, zero_dut, carry_dut, overflow_dut, negative_dut }
                ^ { result_ref, zero_ref, carry_ref, overflow_ref, negative_ref } ) );

    // Use explicit sensitivity list here. @(*) causes NetProc::nex_input() to be called when trying to compute
    // the sensitivity list of the @(strobe) process, which isn't implemented.
    always @(posedge clk, negedge clk) begin

        stats1.clocks++;
        if (!tb_match) begin
            if (stats1.errors == 0) stats1.errortime = $time;
            stats1.errors++;
        end
        if (result_ref !== ( result_ref ^ result_dut ^ result_ref ))
        begin if (stats1.errors_result == 0) stats1.errortime_result = $time;
            stats1.errors_result = stats1.errors_result+1'b1; end

        if (zero_ref !== ( zero_ref ^ zero_dut ^ zero_ref ))
        begin if (stats1.errors_zero == 0) stats1.errortime_zero = $time;
            stats1.errors_zero = stats1.errors_zero+1'b1; end

        if (carry_ref !== ( carry_ref ^ carry_dut ^ carry_ref ))
        begin if (stats1.errors_carry == 0) stats1.errortime_carry = $time;
            stats1.errors_carry = stats1.errors_carry+1'b1; end

        if (overflow_ref !== ( overflow_ref ^ overflow_dut ^ overflow_ref ))
        begin if (stats1.errors_overflow == 0) stats1.errortime_overflow = $time;
            stats1.errors_overflow = stats1.errors_overflow+1'b1; end

        if (negative_ref !== ( negative_ref ^ negative_dut ^ negative_ref ))
        begin if (stats1.errors_negative == 0) stats1.errortime_negative = $time;
            stats1.errors_negative = stats1.errors_negative+1'b1; end

    end

   // add timeout after 100K cycles
   initial begin
     #1000000
     $display("TIMEOUT");
     $finish();
   end

endmodule

