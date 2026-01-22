`timescale 1ns/1ps

module tb;

    reg clk;
    reg rstn;
    reg rx;

    wire [7:0] rx_data;
    wire done;
    wire [7:0] rx_data_ref;
    wire done_ref;

    // Reference
    RefModule ref_inst (
        .clk(clk),
        .rstn(rstn),
        .rx(rx),
        .rx_data(rx_data_ref),
        .done(done_ref)
    );

    // DUT (TopModule) — assumed to be fixed 8-bit, no parameters
    TopModule dut_inst (
        .clk(clk),
        .rstn(rstn),
        .rx(rx),
        .rx_data(rx_data),
        .done(done)
    );

    integer errors = 0;
    integer samples = 0;

    // Bit time for 9600 baud with 100 MHz clock (10 ns period): 100_000_000 / 9600 cycles => 10416 cycles => 104160 ns.
    localparam integer BIT_TIME_NS = 104160;

    // Send one byte over rx with start, even parity, stop.
    task send_byte(input [7:0] data);
        integer i;
        reg parity_bit;
        begin
            parity_bit = ^data; // even parity bit

            // Start bit
            rx = 1'b0; #(BIT_TIME_NS);
            // Data bits LSB-first
            for (i = 0; i < 8; i = i + 1) begin
                rx = data[i]; #(BIT_TIME_NS);
            end
            // Parity bit (even)
            rx = parity_bit; #(BIT_TIME_NS);
            // Stop bit
            rx = 1'b1; #(BIT_TIME_NS);
        end
    endtask

    task check_after_done(input [7:0] expected_data);
    begin
        @(posedge done);
        samples = samples + 1;
        if (rx_data !== expected_data) begin
            errors = errors + 1;
            $display("Mismatch @%0t: expected=%h, received=%h", $time, expected_data, rx_data);
        end
    end
    endtask

    task send_and_check(input [7:0] data);
    begin
        fork
            send_byte(data);
            check_after_done(data);
        join
    end
    endtask

    always begin
        #5 clk = ~clk; // 100 MHz clock (10 ns period)
    end

    initial begin
        clk = 0;
        rstn = 0;
        rx = 1; // UART idle high

        #20 rstn = 1;
        #20;

        send_and_check(8'h55);
        send_and_check(8'hAA);
        send_and_check(8'hFF);
        send_and_check(8'h00);
        send_and_check(8'h77);

        $display("Simulation finished at %0t, errors=%0d", $time, errors);
        $finish;
    end

    initial begin
        $monitor("At time %t: rx_data = %h, done = %b", $time, rx_data, done);
    end

    final begin
        $display("Mismatches: %0d in %0d samples", errors, samples);
    end

endmodule

