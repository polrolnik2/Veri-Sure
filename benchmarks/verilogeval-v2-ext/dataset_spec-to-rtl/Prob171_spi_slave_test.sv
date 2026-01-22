`timescale 1 ps/1 ps
`define OK 12
`define INCORRECT 13


module stimulus_gen (
    input clk,
    output logic sclk,
    output logic reset,
    output logic cs_n,
    output logic mosi,
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

    task automatic spi_send_byte(input logic [7:0] b);
        int i;
        for (i = 7; i >= 0; i = i - 1) begin
            @(negedge clk);
            mosi <= b[i];
            @(posedge clk);
            sclk <= 1'b1;   // rising edge: slave samples MOSI
            @(posedge clk);
            sclk <= 1'b0;   // falling edge: slave updates MISO
        end
    endtask

    task automatic spi_write_reg0(input logic [7:0] val);
        @(negedge clk);
        cs_n <= 1'b0;
        spi_send_byte(8'h02);
        spi_send_byte(val);
        @(negedge clk);
        cs_n <= 1'b1;
        mosi <= 1'b0;
    endtask

    task automatic spi_read_reg0;
        @(negedge clk);
        cs_n <= 1'b0;
        spi_send_byte(8'h03);
        spi_send_byte(8'h00); // clocks out response
        @(negedge clk);
        cs_n <= 1'b1;
        mosi <= 1'b0;
    endtask

    initial begin
        sclk <= 1'b0;
        reset <= 1'b1;
        cs_n <= 1'b1;
        mosi <= 1'b0;

        @(negedge clk) wavedrom_start("SPI slave (cmd parse, REG0 read/write)");
        repeat(2) @(posedge clk);
        reset <= 1'b0;

        // Directed: write then read.
        spi_write_reg0(8'h5A);
        spi_read_reg0();

        // Randomized sequences.
        repeat(10) begin
            spi_write_reg0($random);
            spi_read_reg0();
        end

        // Abort mid-command by deasserting CS.
        @(negedge clk) cs_n <= 1'b0;
        spi_send_byte(8'h03);
        @(negedge clk) cs_n <= 1'b1;  // abort before response
        repeat(4) @(posedge clk);
        spi_read_reg0();

        wavedrom_stop();
        repeat(40) @(posedge clk, negedge clk) begin
            cs_n <= 1'b1;
            sclk <= 1'b0;
            mosi <= $random;
        end
        $finish;
    end

endmodule

module tb();

    typedef struct packed {
        int errors;
        int errortime;
        int errors_miso;
        int errortime_miso;
        int errors_miso_oe;
        int errortime_miso_oe;

        int clocks;
    } stats;

    stats stats1;


    wire[511:0] wavedrom_title;
    wire wavedrom_enable;
    int wavedrom_hide_after_time;

    reg clk=0;
    initial forever
        #5 clk = ~clk;

    logic sclk;
    logic reset;
    logic cs_n;
    logic mosi;
    logic miso_ref, miso_dut;
    logic miso_oe_ref, miso_oe_dut;

    initial begin
        $dumpfile("wave.vcd");
        $dumpvars(1, stim1.clk, tb_mismatch ,clk,sclk,reset,cs_n,mosi,miso_ref,miso_dut,miso_oe_ref,miso_oe_dut );
    end


    wire tb_match;       // Verification
    wire tb_mismatch = ~tb_match;

    stimulus_gen stim1 (
        .clk,
        .* ,
        .sclk,
        .reset,
        .cs_n,
        .mosi );
    RefModule good1 (
        .sclk,
        .reset,
        .cs_n,
        .mosi,
        .miso(miso_ref),
        .miso_oe(miso_oe_ref) );

    TopModule top_module1 (
        .sclk,
        .reset,
        .cs_n,
        .mosi,
        .miso(miso_dut),
        .miso_oe(miso_oe_dut) );


    final begin
        if (stats1.errors_miso) $display("Hint: Output '%s' has %0d mismatches. First mismatch occurred at time %0d.", "miso", stats1.errors_miso, stats1.errortime_miso);
        else $display("Hint: Output '%s' has no mismatches.", "miso");

        if (stats1.errors_miso_oe) $display("Hint: Output '%s' has %0d mismatches. First mismatch occurred at time %0d.", "miso_oe", stats1.errors_miso_oe, stats1.errortime_miso_oe);
        else $display("Hint: Output '%s' has no mismatches.", "miso_oe");

        $display("Hint: Total mismatched samples is %1d out of %1d samples\n", stats1.errors, stats1.clocks);
        $display("Simulation finished at %0d ps", $time);
        $display("Mismatches: %1d in %1d samples", stats1.errors, stats1.clocks);
    end

    assign tb_match =
        ( { miso_ref, miso_oe_ref } === ( { miso_ref, miso_oe_ref } ^ { miso_dut, miso_oe_dut } ^ { miso_ref, miso_oe_ref } ) );

    always @(posedge clk, negedge clk) begin
        stats1.clocks++;
        if (!tb_match) begin
            if (stats1.errors == 0) stats1.errortime = $time;
            stats1.errors++;
        end
        if (miso_ref !== ( miso_ref ^ miso_dut ^ miso_ref ))
        begin if (stats1.errors_miso == 0) stats1.errortime_miso = $time;
            stats1.errors_miso = stats1.errors_miso+1'b1; end
        if (miso_oe_ref !== ( miso_oe_ref ^ miso_oe_dut ^ miso_oe_ref ))
        begin if (stats1.errors_miso_oe == 0) stats1.errortime_miso_oe = $time;
            stats1.errors_miso_oe = stats1.errors_miso_oe+1'b1; end
    end

   initial begin
     #4000000
     $display("TIMEOUT");
     $finish();
   end

endmodule

