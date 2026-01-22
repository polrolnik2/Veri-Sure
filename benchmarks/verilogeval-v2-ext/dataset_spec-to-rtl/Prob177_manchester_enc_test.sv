`timescale 1 ps/1 ps
`define OK 12
`define INCORRECT 13


module stimulus_gen (
    input clk,
    output logic       reset,
    output logic       start,
    output logic [7:0] data,
    output reg[511:0] wavedrom_title,
    output reg wavedrom_enable
);

    task wavedrom_start(input[511:0] title = "");
    endtask

    task wavedrom_stop;
        #1;
    endtask

    task automatic run_op(input logic [7:0] d);
        @(negedge clk);
        data <= d;
        start <= 1'b1;
        @(negedge clk);
        start <= 1'b0;

        // Try to restart while busy (should be ignored).
        repeat(5) @(negedge clk) start <= $random;
        @(negedge clk) start <= 1'b0;

        // Wait long enough for completion (16 cycles + done).
        repeat(25) @(posedge clk);
    endtask

    initial begin
        reset <= 1'b1;
        start <= 1'b0;
        data <= 8'd0;

        @(negedge clk) wavedrom_start("Manchester encoder (byte -> 16 half-bits)");
        repeat(2) @(posedge clk);
        reset <= 1'b0;

        run_op(8'h00);
        run_op(8'hFF);
        run_op(8'hA5);
        repeat(10) run_op($random);

        wavedrom_stop();
        repeat(30) @(posedge clk, negedge clk) begin
            start <= 1'b0;
            data <= $random;
        end
        $finish;
    end

endmodule

module tb();
    typedef struct packed {
        int errors;
        int errortime;
        int errors_man_out;
        int errortime_man_out;
        int errors_out_valid;
        int errortime_out_valid;
        int errors_busy;
        int errortime_busy;
        int errors_done;
        int errortime_done;
        int clocks;
    } stats;

    stats stats1;

    wire[511:0] wavedrom_title;
    wire wavedrom_enable;
    int wavedrom_hide_after_time;

    reg clk=0;
    initial forever #5 clk = ~clk;

    logic reset;
    logic start;
    logic [7:0] data;

    logic man_out_ref, man_out_dut;
    logic out_valid_ref, out_valid_dut;
    logic busy_ref, busy_dut;
    logic done_ref, done_dut;

    initial begin
        $dumpfile("wave.vcd");
        $dumpvars(1, stim1.clk, tb_mismatch ,clk,reset,start,data,man_out_ref,man_out_dut,out_valid_ref,out_valid_dut,busy_ref,busy_dut,done_ref,done_dut );
    end

    wire tb_match;
    wire tb_mismatch = ~tb_match;

    stimulus_gen stim1 (
        .clk,
        .*,
        .reset,
        .start,
        .data
    );

    RefModule good1 (
        .clk,
        .reset,
        .start,
        .data,
        .man_out(man_out_ref),
        .out_valid(out_valid_ref),
        .busy(busy_ref),
        .done(done_ref)
    );

    TopModule top_module1 (
        .clk,
        .reset,
        .start,
        .data,
        .man_out(man_out_dut),
        .out_valid(out_valid_dut),
        .busy(busy_dut),
        .done(done_dut)
    );

    final begin
        $display("Hint: Total mismatched samples is %1d out of %1d samples\n", stats1.errors, stats1.clocks);
        $display("Simulation finished at %0d ps", $time);
        $display("Mismatches: %1d in %1d samples", stats1.errors, stats1.clocks);
    end

    assign tb_match =
        ( { man_out_ref, out_valid_ref, busy_ref, done_ref }
          === ( { man_out_ref, out_valid_ref, busy_ref, done_ref }
                ^ { man_out_dut, out_valid_dut, busy_dut, done_dut }
                ^ { man_out_ref, out_valid_ref, busy_ref, done_ref } ) );

    always @(posedge clk, negedge clk) begin
        stats1.clocks++;
        if (!tb_match) begin
            if (stats1.errors == 0) stats1.errortime = $time;
            stats1.errors++;
        end
        if (man_out_ref !== (man_out_ref ^ man_out_dut ^ man_out_ref))
        begin if (stats1.errors_man_out == 0) stats1.errortime_man_out = $time;
            stats1.errors_man_out = stats1.errors_man_out+1'b1; end
        if (out_valid_ref !== (out_valid_ref ^ out_valid_dut ^ out_valid_ref))
        begin if (stats1.errors_out_valid == 0) stats1.errortime_out_valid = $time;
            stats1.errors_out_valid = stats1.errors_out_valid+1'b1; end
        if (busy_ref !== (busy_ref ^ busy_dut ^ busy_ref))
        begin if (stats1.errors_busy == 0) stats1.errortime_busy = $time;
            stats1.errors_busy = stats1.errors_busy+1'b1; end
        if (done_ref !== (done_ref ^ done_dut ^ done_ref))
        begin if (stats1.errors_done == 0) stats1.errortime_done = $time;
            stats1.errors_done = stats1.errors_done+1'b1; end
    end

   initial begin
     #2500000
     $display("TIMEOUT");
     $finish();
   end

endmodule

