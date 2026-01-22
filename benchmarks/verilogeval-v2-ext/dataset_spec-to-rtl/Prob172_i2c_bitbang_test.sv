`timescale 1 ps/1 ps
`define OK 12
`define INCORRECT 13


module stimulus_gen (
    input clk,
    output logic       reset,
    output logic       start,
    output logic [6:0] addr,
    output logic [7:0] data,
    output logic       slave_sda_drive_low,
    output reg[511:0]  wavedrom_title,
    output reg         wavedrom_enable
);

    task wavedrom_start(input[511:0] title = "");
    endtask

    task wavedrom_stop;
        #1;
    endtask

    // Deterministic ACK schedule based on fixed transaction timing.
    localparam int unsigned TOTAL_CYCLES = 42;  // includes DONE cycle
    logic active;
    int unsigned t;
    logic ack_addr_ok;
    logic ack_data_ok;

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
        slave_sda_drive_low = 1'b0;
        if (active) begin
            // ACK for address at cycles 18-19; ACK for data at cycles 36-37.
            if ((t == 18) || (t == 19)) begin
                slave_sda_drive_low = ack_addr_ok;
            end else if ((t == 36) || (t == 37)) begin
                slave_sda_drive_low = ack_data_ok;
            end
        end
    end

    task automatic run_op(
        input logic [6:0] addr_in,
        input logic [7:0] data_in,
        input logic       ack_addr_in,
        input logic       ack_data_in
    );
        @(negedge clk);
        addr <= addr_in;
        data <= data_in;
        ack_addr_ok <= ack_addr_in;
        ack_data_ok <= ack_data_in;
        start <= 1'b1;

        // spurious starts while busy should be ignored
        repeat(3) @(negedge clk) begin
            start <= $random;
        end
        @(negedge clk);
        start <= 1'b0;

        // Wait until the fixed-length transaction completes.
        repeat(TOTAL_CYCLES+2) @(posedge clk);
    endtask

    initial begin
        reset <= 1'b1;
        start <= 1'b0;
        addr <= 7'd0;
        data <= 8'd0;
        ack_addr_ok <= 1'b1;
        ack_data_ok <= 1'b1;

        @(negedge clk) wavedrom_start("I2C bitbang master: START/STOP/ACK");
        repeat(2) @(posedge clk);
        reset <= 1'b0;

        // Directed + random transactions, including NACK cases.
        run_op(7'h12, 8'hA5, 1'b1, 1'b1);
        run_op(7'h55, 8'h5A, 1'b1, 1'b0); // NACK data
        run_op(7'h00, 8'h00, 1'b0, 1'b1); // NACK addr

        repeat(10) begin
            run_op($random, $random, 1'b1, $random);
        end

        wavedrom_stop();
        repeat(40) @(posedge clk, negedge clk) begin
            start <= 1'b0;
            addr <= $random;
            data <= $random;
        end
        $finish;
    end

endmodule

module tb();
    typedef struct packed {
        int errors;
        int errortime;
        int errors_scl_oe;
        int errortime_scl_oe;
        int errors_sda_oe;
        int errortime_sda_oe;
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

    logic       reset;
    logic       start;
    logic [6:0] addr;
    logic [7:0] data;
    logic       slave_sda_drive_low;

    logic scl_oe_ref, scl_oe_dut;
    logic sda_oe_ref, sda_oe_dut;
    logic busy_ref, busy_dut;
    logic done_ref, done_dut;
    logic ack_error_ref, ack_error_dut;

    // Compute separate SDA bus levels for ref and dut (open-drain).
    logic sda_in_ref;
    logic sda_in_dut;
    always_comb begin
        sda_in_ref = ~(slave_sda_drive_low | sda_oe_ref);
        sda_in_dut = ~(slave_sda_drive_low | sda_oe_dut);
    end

    initial begin
        $dumpfile("wave.vcd");
        $dumpvars(1, stim1.clk, tb_mismatch ,clk,reset,start,addr,data,slave_sda_drive_low,scl_oe_ref,scl_oe_dut,sda_oe_ref,sda_oe_dut,sda_in_ref,sda_in_dut,busy_ref,busy_dut,done_ref,done_dut,ack_error_ref,ack_error_dut );
    end

    wire tb_match;
    wire tb_mismatch = ~tb_match;

    stimulus_gen stim1 (
        .clk,
        .*,
        .reset,
        .start,
        .addr,
        .data,
        .slave_sda_drive_low
    );

    RefModule good1 (
        .clk,
        .reset,
        .start,
        .addr,
        .data,
        .sda_in(sda_in_ref),
        .scl_oe(scl_oe_ref),
        .sda_oe(sda_oe_ref),
        .busy(busy_ref),
        .done(done_ref),
        .ack_error(ack_error_ref)
    );

    TopModule top_module1 (
        .clk,
        .reset,
        .start,
        .addr,
        .data,
        .sda_in(sda_in_dut),
        .scl_oe(scl_oe_dut),
        .sda_oe(sda_oe_dut),
        .busy(busy_dut),
        .done(done_dut),
        .ack_error(ack_error_dut)
    );

    final begin
        if (stats1.errors_ack_error) $display("Hint: Output '%s' has %0d mismatches. First mismatch occurred at time %0d.", "ack_error", stats1.errors_ack_error, stats1.errortime_ack_error);
        else $display("Hint: Output '%s' has no mismatches.", "ack_error");

        $display("Hint: Total mismatched samples is %1d out of %1d samples\n", stats1.errors, stats1.clocks);
        $display("Simulation finished at %0d ps", $time);
        $display("Mismatches: %1d in %1d samples", stats1.errors, stats1.clocks);
    end

    assign tb_match =
        ( { scl_oe_ref, sda_oe_ref, busy_ref, done_ref, ack_error_ref }
          === ( { scl_oe_ref, sda_oe_ref, busy_ref, done_ref, ack_error_ref }
                ^ { scl_oe_dut, sda_oe_dut, busy_dut, done_dut, ack_error_dut }
                ^ { scl_oe_ref, sda_oe_ref, busy_ref, done_ref, ack_error_ref } ) );

    always @(posedge clk, negedge clk) begin
        stats1.clocks++;
        if (!tb_match) begin
            if (stats1.errors == 0) stats1.errortime = $time;
            stats1.errors++;
        end

        if (scl_oe_ref !== (scl_oe_ref ^ scl_oe_dut ^ scl_oe_ref))
        begin if (stats1.errors_scl_oe == 0) stats1.errortime_scl_oe = $time;
            stats1.errors_scl_oe = stats1.errors_scl_oe+1'b1; end
        if (sda_oe_ref !== (sda_oe_ref ^ sda_oe_dut ^ sda_oe_ref))
        begin if (stats1.errors_sda_oe == 0) stats1.errortime_sda_oe = $time;
            stats1.errors_sda_oe = stats1.errors_sda_oe+1'b1; end
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
     #6000000
     $display("TIMEOUT");
     $finish();
   end

endmodule

