`timescale 1 ps/1 ps
`define OK 12
`define INCORRECT 13


module stimulus_gen (
    input  clk,
    input  in_ready_ref,
    output logic reset,
    output logic in_valid,
    output logic [7:0] in_data,
    output logic out_ready,
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

    always_ff @(posedge clk) begin
        if (reset) begin
            in_valid <= 1'b0;
            in_data <= 8'd0;
            out_ready <= 1'b0;
        end else begin
            // Downstream backpressure.
            out_ready <= $random;

            // Upstream source respects ready/valid: hold data while waiting.
            if (in_valid && !in_ready_ref) begin
                in_valid <= 1'b1;
                in_data <= in_data;
            end else begin
                in_valid <= $random;
                if ($random) begin
                    in_data <= $random;
                end else begin
                    in_data <= in_data;
                end
            end
        end
    end

    initial begin
        reset <= 1'b1;
        in_valid <= 1'b0;
        in_data <= 8'd0;
        out_ready <= 1'b0;

        @(negedge clk) wavedrom_start("Skid buffer (valid/ready)");
        repeat(2) @(posedge clk);
        reset <= 1'b0;

        repeat(800) @(posedge clk);

        wavedrom_stop();
        #1 $finish;
    end

endmodule

module tb();

    typedef struct packed {
        int errors;
        int errortime;
        int errors_in_ready;
        int errortime_in_ready;
        int errors_out_valid;
        int errortime_out_valid;
        int errors_out_data;
        int errortime_out_data;

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
    logic [7:0] in_data;
    logic in_ready_ref;
    logic in_ready_dut;
    logic out_valid_ref;
    logic out_valid_dut;
    logic [7:0] out_data_ref;
    logic [7:0] out_data_dut;
    logic out_ready;

    initial begin
        $dumpfile("wave.vcd");
        $dumpvars(1, tb_mismatch ,clk,reset,in_valid,in_data,in_ready_ref,in_ready_dut,out_valid_ref,out_valid_dut,out_data_ref,out_data_dut,out_ready );
    end


    wire tb_match;       // Verification
    wire tb_mismatch = ~tb_match;

    stimulus_gen stim1 (
        .clk,
        .in_ready_ref(in_ready_ref),
        .* );
    RefModule good1 (
        .clk,
        .reset,
        .in_valid,
        .in_data,
        .in_ready(in_ready_ref),
        .out_valid(out_valid_ref),
        .out_data(out_data_ref),
        .out_ready );

    TopModule top_module1 (
        .clk,
        .reset,
        .in_valid,
        .in_data,
        .in_ready(in_ready_dut),
        .out_valid(out_valid_dut),
        .out_data(out_data_dut),
        .out_ready );


    bit strobe = 0;
    task wait_for_end_of_timestep;
        repeat(5) begin
            strobe <= !strobe;  // Try to delay until the very end of the time step.
            @(strobe);
        end
    endtask


    final begin
        if (stats1.errors_in_ready) $display("Hint: Output '%s' has %0d mismatches. First mismatch occurred at time %0d.", "in_ready", stats1.errors_in_ready, stats1.errortime_in_ready);
        else $display("Hint: Output '%s' has no mismatches.", "in_ready");

        if (stats1.errors_out_valid) $display("Hint: Output '%s' has %0d mismatches. First mismatch occurred at time %0d.", "out_valid", stats1.errors_out_valid, stats1.errortime_out_valid);
        else $display("Hint: Output '%s' has no mismatches.", "out_valid");

        if (stats1.errors_out_data) $display("Hint: Output '%s' has %0d mismatches. First mismatch occurred at time %0d.", "out_data", stats1.errors_out_data, stats1.errortime_out_data);
        else $display("Hint: Output '%s' has no mismatches.", "out_data");

        $display("Hint: Total mismatched samples is %1d out of %1d samples\n", stats1.errors, stats1.clocks);
        $display("Simulation finished at %0d ps", $time);
        $display("Mismatches: %1d in %1d samples", stats1.errors, stats1.clocks);
    end

    // Verification: XORs on the right makes any X in good_vector match anything, but X in dut_vector will only match X.
    assign tb_match = ( { in_ready_ref, out_valid_ref, out_data_ref } === ( { in_ready_ref, out_valid_ref, out_data_ref } ^ { in_ready_dut, out_valid_dut, out_data_dut } ^ { in_ready_ref, out_valid_ref, out_data_ref } ) );
    // Use explicit sensitivity list here. @(*) causes NetProc::nex_input() to be called when trying to compute
    // the sensitivity list of the @(strobe) process, which isn't implemented.
    always @(posedge clk, negedge clk) begin

        stats1.clocks++;
        if (!tb_match) begin
            if (stats1.errors == 0) stats1.errortime = $time;
            stats1.errors++;
        end
        if (in_ready_ref !== ( in_ready_ref ^ in_ready_dut ^ in_ready_ref ))
        begin if (stats1.errors_in_ready == 0) stats1.errortime_in_ready = $time;
            stats1.errors_in_ready = stats1.errors_in_ready+1'b1; end

        if (out_valid_ref !== ( out_valid_ref ^ out_valid_dut ^ out_valid_ref ))
        begin if (stats1.errors_out_valid == 0) stats1.errortime_out_valid = $time;
            stats1.errors_out_valid = stats1.errors_out_valid+1'b1; end

        if (out_data_ref !== ( out_data_ref ^ out_data_dut ^ out_data_ref ))
        begin if (stats1.errors_out_data == 0) stats1.errortime_out_data = $time;
            stats1.errors_out_data = stats1.errors_out_data+1'b1; end

    end

   // add timeout after 100K cycles
   initial begin
     #2500000
     $display("TIMEOUT");
     $finish();
   end

endmodule

