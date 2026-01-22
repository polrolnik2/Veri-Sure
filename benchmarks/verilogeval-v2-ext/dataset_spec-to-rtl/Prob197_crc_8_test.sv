`timescale 1 ps/1 ps
`define OK 12
`define INCORRECT 13


module stimulus_gen (
    input clk,
    output logic [7:0] crc_in,
    output logic [7:0] data,
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
        {crc_in, data} <= 16'd0;
        @(negedge clk) wavedrom_start("CRC-8 parallel update");

        // Directed.
        @(posedge clk) begin crc_in <= 8'h00; data <= 8'h00; end
        @(posedge clk) begin crc_in <= 8'h00; data <= 8'h01; end
        @(posedge clk) begin crc_in <= 8'h00; data <= 8'hFF; end
        @(posedge clk) begin crc_in <= 8'hA5; data <= 8'h5A; end

        repeat(40) @(posedge clk) begin
            crc_in <= $random;
            data <= $random;
        end

        wavedrom_stop();
        repeat(120) @(posedge clk, negedge clk) begin
            crc_in <= $random;
            data <= $random;
        end
        $finish;
    end

endmodule

module tb();

    typedef struct packed {
        int errors;
        int errortime;
        int errors_crc_out;
        int errortime_crc_out;

        int clocks;
    } stats;

    stats stats1;


    wire[511:0] wavedrom_title;
    wire wavedrom_enable;
    int wavedrom_hide_after_time;

    reg clk=0;
    initial forever
        #5 clk = ~clk;

    logic [7:0] crc_in;
    logic [7:0] data;
    logic [7:0] crc_ref;
    logic [7:0] crc_dut;

    initial begin
        $dumpfile("wave.vcd");
        $dumpvars(1, stim1.clk, tb_mismatch ,crc_in,data,crc_ref,crc_dut );
    end


    wire tb_match;       // Verification
    wire tb_mismatch = ~tb_match;

    stimulus_gen stim1 (
        .clk,
        .* ,
        .crc_in,
        .data );
    RefModule good1 (
        .crc_in,
        .data,
        .crc_out(crc_ref) );

    TopModule top_module1 (
        .crc_in,
        .data,
        .crc_out(crc_dut) );


    bit strobe = 0;
    task wait_for_end_of_timestep;
        repeat(5) begin
            strobe <= !strobe;  // Try to delay until the very end of the time step.
            @(strobe);
        end
    endtask


    final begin
        if (stats1.errors_crc_out) $display("Hint: Output '%s' has %0d mismatches. First mismatch occurred at time %0d.", "crc_out", stats1.errors_crc_out, stats1.errortime_crc_out);
        else $display("Hint: Output '%s' has no mismatches.", "crc_out");

        $display("Hint: Total mismatched samples is %1d out of %1d samples\n", stats1.errors, stats1.clocks);
        $display("Simulation finished at %0d ps", $time);
        $display("Mismatches: %1d in %1d samples", stats1.errors, stats1.clocks);
    end

    // Verification: XORs on the right makes any X in good_vector match anything, but X in dut_vector will only match X.
    assign tb_match = ( { crc_ref } === ( { crc_ref } ^ { crc_dut } ^ { crc_ref } ) );
    // Use explicit sensitivity list here. @(*) causes NetProc::nex_input() to be called when trying to compute
    // the sensitivity list of the @(strobe) process, which isn't implemented.
    always @(posedge clk, negedge clk) begin

        stats1.clocks++;
        if (!tb_match) begin
            if (stats1.errors == 0) stats1.errortime = $time;
            stats1.errors++;
        end
        if (crc_ref !== ( crc_ref ^ crc_dut ^ crc_ref ))
        begin if (stats1.errors_crc_out == 0) stats1.errortime_crc_out = $time;
            stats1.errors_crc_out = stats1.errors_crc_out+1'b1; end

    end

   // add timeout after 100K cycles
   initial begin
     #1000000
     $display("TIMEOUT");
     $finish();
   end

endmodule

