`timescale 1 ps/1 ps
`define OK 12
`define INCORRECT 13


module stimulus_gen (
    input clk,
    output logic       reset,
    output logic       start,
    output logic [7:0] data,
    output logic       dev_data_drive_low,
    output reg[511:0]  wavedrom_title,
    output reg         wavedrom_enable
);
    task wavedrom_start(input[511:0] title = "");
    endtask

    task wavedrom_stop;
        #1;
    endtask

    localparam int unsigned TOTAL_CYCLES = 29; // inhibit(4) + bits(22) + ack(2) + done(1)
    logic active;
    int unsigned t;
    logic ack_ok;

    always_ff @(posedge clk) begin
        if (reset) begin
            active <= 1'b0;
            t <= 0;
        end else begin
            if (!active && start) begin
                active <= 1'b1;
                t <= 0;
            end else if (active) begin
                t <= t + 1;
                if (t >= (TOTAL_CYCLES-1)) begin
                    active <= 1'b0;
                end
            end
        end
    end

    always_comb begin
        dev_data_drive_low = 1'b0;
        if (active) begin
            // ACK pulse occurs at cycles 26-27 relative to start accept.
            if ((t == 26) || (t == 27)) begin
                dev_data_drive_low = ack_ok;
            end
        end
    end

    task automatic run_op(input logic [7:0] d_in, input logic ack_in);
        @(negedge clk);
        data <= d_in;
        ack_ok <= ack_in;
        start <= 1'b1;

        // spurious starts while busy should be ignored
        repeat(4) @(negedge clk) start <= $random;
        @(negedge clk) start <= 1'b0;

        repeat(TOTAL_CYCLES+5) @(posedge clk);
    endtask

    initial begin
        reset <= 1'b1;
        start <= 1'b0;
        data <= 8'd0;
        ack_ok <= 1'b1;

        @(negedge clk) wavedrom_start("PS/2 host TX (open-drain, parity, ACK)");
        repeat(2) @(posedge clk);
        reset <= 1'b0;

        run_op(8'h55, 1'b1); // ACK
        run_op(8'hAA, 1'b0); // NACK
        repeat(8) run_op($random, $random);

        wavedrom_stop();
        repeat(40) @(posedge clk, negedge clk) begin
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
        int errors_ps2_clk_oe;
        int errortime_ps2_clk_oe;
        int errors_ps2_data_oe;
        int errortime_ps2_data_oe;
        int errors_busy;
        int errortime_busy;
        int errors_done;
        int errortime_done;
        int errors_ack_error;
        int errortime_ack_error;
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
    logic dev_data_drive_low;

    logic ps2_clk_oe_ref, ps2_clk_oe_dut;
    logic ps2_data_oe_ref, ps2_data_oe_dut;
    logic busy_ref, busy_dut;
    logic done_ref, done_dut;
    logic ack_error_ref, ack_error_dut;

    // Compute separate DATA bus levels for ref and dut (open-drain).
    logic ps2_data_in_ref;
    logic ps2_data_in_dut;
    always_comb begin
        ps2_data_in_ref = ~(dev_data_drive_low | ps2_data_oe_ref);
        ps2_data_in_dut = ~(dev_data_drive_low | ps2_data_oe_dut);
    end

    initial begin
        $dumpfile("wave.vcd");
        $dumpvars(1, stim1.clk, tb_mismatch ,clk,reset,start,data,dev_data_drive_low,ps2_clk_oe_ref,ps2_clk_oe_dut,ps2_data_oe_ref,ps2_data_oe_dut,ps2_data_in_ref,ps2_data_in_dut,busy_ref,busy_dut,done_ref,done_dut,ack_error_ref,ack_error_dut );
    end

    wire tb_match;
    wire tb_mismatch = ~tb_match;

    stimulus_gen stim1 (
        .clk,
        .*,
        .reset,
        .start,
        .data,
        .dev_data_drive_low
    );

    RefModule good1 (
        .clk,
        .reset,
        .start,
        .data,
        .ps2_data_in(ps2_data_in_ref),
        .ps2_clk_oe(ps2_clk_oe_ref),
        .ps2_data_oe(ps2_data_oe_ref),
        .busy(busy_ref),
        .done(done_ref),
        .ack_error(ack_error_ref)
    );

    TopModule top_module1 (
        .clk,
        .reset,
        .start,
        .data,
        .ps2_data_in(ps2_data_in_dut),
        .ps2_clk_oe(ps2_clk_oe_dut),
        .ps2_data_oe(ps2_data_oe_dut),
        .busy(busy_dut),
        .done(done_dut),
        .ack_error(ack_error_dut)
    );

    final begin
        $display("Hint: Total mismatched samples is %1d out of %1d samples\n", stats1.errors, stats1.clocks);
        $display("Simulation finished at %0d ps", $time);
        $display("Mismatches: %1d in %1d samples", stats1.errors, stats1.clocks);
    end

    assign tb_match =
        ( { ps2_clk_oe_ref, ps2_data_oe_ref, busy_ref, done_ref, ack_error_ref }
          === ( { ps2_clk_oe_ref, ps2_data_oe_ref, busy_ref, done_ref, ack_error_ref }
                ^ { ps2_clk_oe_dut, ps2_data_oe_dut, busy_dut, done_dut, ack_error_dut }
                ^ { ps2_clk_oe_ref, ps2_data_oe_ref, busy_ref, done_ref, ack_error_ref } ) );

    always @(posedge clk, negedge clk) begin
        stats1.clocks++;
        if (!tb_match) begin
            if (stats1.errors == 0) stats1.errortime = $time;
            stats1.errors++;
        end
        if (ps2_clk_oe_ref !== (ps2_clk_oe_ref ^ ps2_clk_oe_dut ^ ps2_clk_oe_ref))
        begin if (stats1.errors_ps2_clk_oe == 0) stats1.errortime_ps2_clk_oe = $time;
            stats1.errors_ps2_clk_oe = stats1.errors_ps2_clk_oe+1'b1; end
        if (ps2_data_oe_ref !== (ps2_data_oe_ref ^ ps2_data_oe_dut ^ ps2_data_oe_ref))
        begin if (stats1.errors_ps2_data_oe == 0) stats1.errortime_ps2_data_oe = $time;
            stats1.errors_ps2_data_oe = stats1.errors_ps2_data_oe+1'b1; end
        if (busy_ref !== (busy_ref ^ busy_dut ^ busy_ref))
        begin if (stats1.errors_busy == 0) stats1.errortime_busy = $time;
            stats1.errors_busy = stats1.errors_busy+1'b1; end
        if (done_ref !== (done_ref ^ done_dut ^ done_ref))
        begin if (stats1.errors_done == 0) stats1.errortime_done = $time;
            stats1.errors_done = stats1.errors_done+1'b1; end
        if (ack_error_ref !== (ack_error_ref ^ ack_error_dut ^ ack_error_ref))
        begin if (stats1.errors_ack_error == 0) stats1.errortime_ack_error = $time;
            stats1.errors_ack_error = stats1.errors_ack_error+1'b1; end
    end

   initial begin
     #8000000
     $display("TIMEOUT");
     $finish();
   end

endmodule
