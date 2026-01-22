`timescale 1 ps/1 ps
`define OK 12
`define INCORRECT 13


module stimulus_gen (
    input clk,
    output logic       reset,
    output logic       start,
    output logic [7:0] tx_data,
    output logic       miso,
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

    // Simple deterministic "slave" response generator based on cycle count
    // after start is accepted. This avoids depending on DUT outputs.
    logic active;
    int unsigned offset;
    logic [7:0] slave_data;

    always_ff @(posedge clk) begin
        if (reset) begin
            active <= 1'b0;
            offset <= 0;
            slave_data <= 8'h00;
            miso <= 1'b1;
        end else begin
            if (!active && start) begin
                active <= 1'b1;
                offset <= 0;
                slave_data <= $random;
            end else if (active) begin
                offset <= offset + 1;
                if (offset >= 16) begin
                    active <= 1'b0;
                end
            end

            // Update MISO during LOW half-cycles so it is stable for the next HIGH sample.
            if (active && (offset[0] == 1'b0) && (offset <= 14)) begin
                int bitpos;
                bitpos = 7 - (offset >> 1);
                miso <= slave_data[bitpos];
            end else if (!active) begin
                miso <= $random;
            end
        end
    end

    task automatic run_op(input logic [7:0] tx);
        @(negedge clk);
        tx_data <= tx;
        start <= 1'b1;
        @(negedge clk);
        start <= 1'b0;
    endtask

    initial begin
        reset <= 1'b1;
        start <= 1'b0;
        tx_data <= 8'd0;
        miso <= 1'b1;

        @(negedge clk) wavedrom_start("SPI master mode0 single-byte transfer");
        repeat(2) @(posedge clk);
        reset <= 1'b0;

        // Directed + random transactions. Inject spurious starts during busy.
        run_op(8'hA5);
        repeat(3) @(negedge clk) start <= 1'b1;
        @(negedge clk) start <= 1'b0;

        run_op(8'h00);
        run_op(8'hFF);
        repeat(20) run_op($random);

        wavedrom_stop();
        repeat(40) @(posedge clk, negedge clk) begin
            tx_data <= $random;
            start <= 1'b0;
        end
        $finish;
    end

endmodule

module tb();

    typedef struct packed {
        int errors;
        int errortime;
        int errors_mosi;
        int errortime_mosi;
        int errors_sclk;
        int errortime_sclk;
        int errors_cs_n;
        int errortime_cs_n;
        int errors_rx_data;
        int errortime_rx_data;
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
    initial forever
        #5 clk = ~clk;

    logic       reset;
    logic       start;
    logic [7:0] tx_data;
    logic       miso;

    logic       mosi_ref, mosi_dut;
    logic       sclk_ref, sclk_dut;
    logic       cs_n_ref, cs_n_dut;
    logic [7:0] rx_data_ref, rx_data_dut;
    logic       busy_ref, busy_dut;
    logic       done_ref, done_dut;

    initial begin
        $dumpfile("wave.vcd");
        $dumpvars(1, stim1.clk, tb_mismatch ,clk,reset,start,tx_data,miso,mosi_ref,mosi_dut,sclk_ref,sclk_dut,cs_n_ref,cs_n_dut,rx_data_ref,rx_data_dut,busy_ref,busy_dut,done_ref,done_dut );
    end


    wire tb_match;       // Verification
    wire tb_mismatch = ~tb_match;

    stimulus_gen stim1 (
        .clk,
        .* ,
        .reset,
        .start,
        .tx_data,
        .miso );
    RefModule good1 (
        .clk,
        .reset,
        .start,
        .tx_data,
        .miso,
        .mosi(mosi_ref),
        .sclk(sclk_ref),
        .cs_n(cs_n_ref),
        .rx_data(rx_data_ref),
        .busy(busy_ref),
        .done(done_ref) );

    TopModule top_module1 (
        .clk,
        .reset,
        .start,
        .tx_data,
        .miso,
        .mosi(mosi_dut),
        .sclk(sclk_dut),
        .cs_n(cs_n_dut),
        .rx_data(rx_data_dut),
        .busy(busy_dut),
        .done(done_dut) );


    bit strobe = 0;
    task wait_for_end_of_timestep;
        repeat(5) begin
            strobe <= !strobe;  // Try to delay until the very end of the time step.
            @(strobe);
        end
    endtask


    final begin
        if (stats1.errors_rx_data) $display("Hint: Output '%s' has %0d mismatches. First mismatch occurred at time %0d.", "rx_data", stats1.errors_rx_data, stats1.errortime_rx_data);
        else $display("Hint: Output '%s' has no mismatches.", "rx_data");

        $display("Hint: Total mismatched samples is %1d out of %1d samples\n", stats1.errors, stats1.clocks);
        $display("Simulation finished at %0d ps", $time);
        $display("Mismatches: %1d in %1d samples", stats1.errors, stats1.clocks);
    end

    assign tb_match =
        ( { mosi_ref, sclk_ref, cs_n_ref, rx_data_ref, busy_ref, done_ref }
          === ( { mosi_ref, sclk_ref, cs_n_ref, rx_data_ref, busy_ref, done_ref }
                ^ { mosi_dut, sclk_dut, cs_n_dut, rx_data_dut, busy_dut, done_dut }
                ^ { mosi_ref, sclk_ref, cs_n_ref, rx_data_ref, busy_ref, done_ref } ) );

    always @(posedge clk, negedge clk) begin
        stats1.clocks++;
        if (!tb_match) begin
            if (stats1.errors == 0) stats1.errortime = $time;
            stats1.errors++;
        end

        if (mosi_ref !== (mosi_ref ^ mosi_dut ^ mosi_ref))
        begin if (stats1.errors_mosi == 0) stats1.errortime_mosi = $time;
            stats1.errors_mosi = stats1.errors_mosi+1'b1; end
        if (sclk_ref !== (sclk_ref ^ sclk_dut ^ sclk_ref))
        begin if (stats1.errors_sclk == 0) stats1.errortime_sclk = $time;
            stats1.errors_sclk = stats1.errors_sclk+1'b1; end
        if (cs_n_ref !== (cs_n_ref ^ cs_n_dut ^ cs_n_ref))
        begin if (stats1.errors_cs_n == 0) stats1.errortime_cs_n = $time;
            stats1.errors_cs_n = stats1.errors_cs_n+1'b1; end
        if (rx_data_ref !== (rx_data_ref ^ rx_data_dut ^ rx_data_ref))
        begin if (stats1.errors_rx_data == 0) stats1.errortime_rx_data = $time;
            stats1.errors_rx_data = stats1.errors_rx_data+1'b1; end
        if (busy_ref !== (busy_ref ^ busy_dut ^ busy_ref))
        begin if (stats1.errors_busy == 0) stats1.errortime_busy = $time;
            stats1.errors_busy = stats1.errors_busy+1'b1; end
        if (done_ref !== (done_ref ^ done_dut ^ done_ref))
        begin if (stats1.errors_done == 0) stats1.errortime_done = $time;
            stats1.errors_done = stats1.errors_done+1'b1; end
    end

   initial begin
     #2000000
     $display("TIMEOUT");
     $finish();
   end

endmodule

