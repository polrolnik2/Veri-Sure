`timescale 1 ps/1 ps
`define OK 12
`define INCORRECT 13


module stimulus_gen (
    input clk,
    output logic reset,
    output logic a_we,
    output logic [3:0] a_addr,
    output logic [7:0] a_din,
    output logic b_we,
    output logic [3:0] b_addr,
    output logic [7:0] b_din,
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
        a_we <= 1'b0;
        b_we <= 1'b0;
        a_addr <= 4'd0;
        b_addr <= 4'd0;
        a_din <= 8'd0;
        b_din <= 8'd0;

        @(negedge clk) wavedrom_start("True dual-port RAM (16x8)");
        repeat(2) @(posedge clk);
        reset <= 1'b0;

        // Directed conflict cases.
        @(posedge clk) begin
            a_we <= 1'b1; a_addr <= 4'h3; a_din <= 8'hAA;
            b_we <= 1'b1; b_addr <= 4'h3; b_din <= 8'h55; // same address, B wins
        end
        @(posedge clk) begin
            a_we <= 1'b0; b_we <= 1'b0;
            a_addr <= 4'h3; b_addr <= 4'h3; // read back
        end

        @(posedge clk) begin
            // Cross-port read-during-write.
            a_we <= 1'b1; a_addr <= 4'h7; a_din <= 8'h0F;
            b_we <= 1'b0; b_addr <= 4'h7;
        end
        @(posedge clk) begin
            a_we <= 1'b0; b_we <= 1'b1; b_addr <= 4'h7; b_din <= 8'hF0;
            a_addr <= 4'h7;
        end

        // Random traffic.
        repeat(400) @(posedge clk) begin
            a_we <= $random;
            b_we <= $random;
            a_addr <= $random;
            b_addr <= $random;
            a_din <= $random;
            b_din <= $random;
            // Occasionally force a same-address write conflict.
            if (!($random & 31)) begin
                a_we <= 1'b1;
                b_we <= 1'b1;
                a_addr <= 4'hC;
                b_addr <= 4'hC;
                a_din <= 8'h12;
                b_din <= 8'h34;
            end
        end

        wavedrom_stop();
        repeat(40) @(posedge clk, negedge clk) begin
            a_we <= 1'b0;
            b_we <= 1'b0;
            a_addr <= $random;
            b_addr <= $random;
            a_din <= $random;
            b_din <= $random;
        end
        $finish;
    end

endmodule

module tb();

    typedef struct packed {
        int errors;
        int errortime;
        int errors_a_dout;
        int errortime_a_dout;
        int errors_b_dout;
        int errortime_b_dout;

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
    logic a_we;
    logic [3:0] a_addr;
    logic [7:0] a_din;
    logic [7:0] a_dout_ref;
    logic [7:0] a_dout_dut;
    logic b_we;
    logic [3:0] b_addr;
    logic [7:0] b_din;
    logic [7:0] b_dout_ref;
    logic [7:0] b_dout_dut;

    initial begin
        $dumpfile("wave.vcd");
        $dumpvars(1, stim1.clk, tb_mismatch ,clk,reset,a_we,a_addr,a_din,a_dout_ref,a_dout_dut,b_we,b_addr,b_din,b_dout_ref,b_dout_dut );
    end


    wire tb_match;       // Verification
    wire tb_mismatch = ~tb_match;

    stimulus_gen stim1 (
        .clk,
        .* ,
        .reset,
        .a_we,
        .a_addr,
        .a_din,
        .b_we,
        .b_addr,
        .b_din );
    RefModule good1 (
        .clk,
        .reset,
        .a_we,
        .a_addr,
        .a_din,
        .a_dout(a_dout_ref),
        .b_we,
        .b_addr,
        .b_din,
        .b_dout(b_dout_ref) );

    TopModule top_module1 (
        .clk,
        .reset,
        .a_we,
        .a_addr,
        .a_din,
        .a_dout(a_dout_dut),
        .b_we,
        .b_addr,
        .b_din,
        .b_dout(b_dout_dut) );


    bit strobe = 0;
    task wait_for_end_of_timestep;
        repeat(5) begin
            strobe <= !strobe;  // Try to delay until the very end of the time step.
            @(strobe);
        end
    endtask


    final begin
        if (stats1.errors_a_dout) $display("Hint: Output '%s' has %0d mismatches. First mismatch occurred at time %0d.", "a_dout", stats1.errors_a_dout, stats1.errortime_a_dout);
        else $display("Hint: Output '%s' has no mismatches.", "a_dout");

        if (stats1.errors_b_dout) $display("Hint: Output '%s' has %0d mismatches. First mismatch occurred at time %0d.", "b_dout", stats1.errors_b_dout, stats1.errortime_b_dout);
        else $display("Hint: Output '%s' has no mismatches.", "b_dout");

        $display("Hint: Total mismatched samples is %1d out of %1d samples\n", stats1.errors, stats1.clocks);
        $display("Simulation finished at %0d ps", $time);
        $display("Mismatches: %1d in %1d samples", stats1.errors, stats1.clocks);
    end

    // Verification: XORs on the right makes any X in good_vector match anything, but X in dut_vector will only match X.
    assign tb_match = ( { a_dout_ref, b_dout_ref } === ( { a_dout_ref, b_dout_ref } ^ { a_dout_dut, b_dout_dut } ^ { a_dout_ref, b_dout_ref } ) );
    // Use explicit sensitivity list here. @(*) causes NetProc::nex_input() to be called when trying to compute
    // the sensitivity list of the @(strobe) process, which isn't implemented.
    always @(posedge clk, negedge clk) begin

        stats1.clocks++;
        if (!tb_match) begin
            if (stats1.errors == 0) stats1.errortime = $time;
            stats1.errors++;
        end
        if (a_dout_ref !== ( a_dout_ref ^ a_dout_dut ^ a_dout_ref ))
        begin if (stats1.errors_a_dout == 0) stats1.errortime_a_dout = $time;
            stats1.errors_a_dout = stats1.errors_a_dout+1'b1; end

        if (b_dout_ref !== ( b_dout_ref ^ b_dout_dut ^ b_dout_ref ))
        begin if (stats1.errors_b_dout == 0) stats1.errortime_b_dout = $time;
            stats1.errors_b_dout = stats1.errors_b_dout+1'b1; end

    end

   // add timeout after 100K cycles
   initial begin
     #1500000
     $display("TIMEOUT");
     $finish();
   end

endmodule

