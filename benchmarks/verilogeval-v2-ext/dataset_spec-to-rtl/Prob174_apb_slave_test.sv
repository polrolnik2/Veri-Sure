`timescale 1 ps/1 ps
`define OK 12
`define INCORRECT 13


module stimulus_gen (
    input clk,
    output logic        reset,
    output logic        psel,
    output logic        penable,
    output logic        pwrite,
    output logic [7:0]  paddr,
    output logic [31:0] pwdata,
    output reg[511:0]  wavedrom_title,
    output reg         wavedrom_enable
);

    task wavedrom_start(input[511:0] title = "");
    endtask

    task wavedrom_stop;
        #1;
    endtask

    task automatic apb_idle(input int cycles);
        repeat(cycles) @(posedge clk) begin
            psel <= 1'b0;
            penable <= 1'b0;
            pwrite <= 1'b0;
            paddr <= $random;
            pwdata <= $random;
        end
    endtask

    task automatic apb_write(input logic [7:0] addr_in, input logic [31:0] data_in);
        // SETUP
        @(posedge clk) begin
            psel <= 1'b1;
            penable <= 1'b0;
            pwrite <= 1'b1;
            paddr <= addr_in;
            pwdata <= data_in;
        end
        // ACCESS
        @(posedge clk) begin
            penable <= 1'b1;
        end
        // return to IDLE
        @(posedge clk) begin
            psel <= 1'b0;
            penable <= 1'b0;
            pwrite <= 1'b0;
        end
    endtask

    task automatic apb_read(input logic [7:0] addr_in);
        // SETUP
        @(posedge clk) begin
            psel <= 1'b1;
            penable <= 1'b0;
            pwrite <= 1'b0;
            paddr <= addr_in;
            pwdata <= $random;
        end
        // ACCESS
        @(posedge clk) begin
            penable <= 1'b1;
        end
        // return to IDLE
        @(posedge clk) begin
            psel <= 1'b0;
            penable <= 1'b0;
            pwrite <= 1'b0;
        end
    endtask

    initial begin
        reset <= 1'b1;
        psel <= 1'b0;
        penable <= 1'b0;
        pwrite <= 1'b0;
        paddr <= 8'd0;
        pwdata <= 32'd0;

        @(negedge clk) wavedrom_start("APB slave: 4-register read/write");
        repeat(2) @(posedge clk);
        reset <= 1'b0;

        apb_idle(2);
        apb_write(8'h00, 32'h1111_1111);
        apb_write(8'h04, 32'h2222_2222);
        apb_read(8'h00);
        apb_read(8'h04);
        apb_read(8'h10); // unmapped

        repeat(20) begin
            if ($random & 1) apb_write({$random} & 8'hFC, $random);
            else apb_read({$random} & 8'hFC);
        end

        // Mid-run reset
        @(posedge clk) reset <= 1'b1;
        @(posedge clk) reset <= 1'b0;
        apb_read(8'h00);

        wavedrom_stop();
        apb_idle(10);
        $finish;
    end

endmodule

module tb();
    typedef struct packed {
        int errors;
        int errortime;
        int errors_prdata;
        int errortime_prdata;
        int errors_pready;
        int errortime_pready;
        int errors_pslverr;
        int errortime_pslverr;
        int clocks;
    } stats;

    stats stats1;

    wire[511:0] wavedrom_title;
    wire wavedrom_enable;
    int wavedrom_hide_after_time;

    reg clk=0;
    initial forever #5 clk = ~clk;

    logic        reset;
    logic        psel;
    logic        penable;
    logic        pwrite;
    logic [7:0]  paddr;
    logic [31:0] pwdata;

    logic [31:0] prdata_ref, prdata_dut;
    logic        pready_ref, pready_dut;
    logic        pslverr_ref, pslverr_dut;

    initial begin
        $dumpfile("wave.vcd");
        $dumpvars(1, stim1.clk, tb_mismatch ,clk,reset,psel,penable,pwrite,paddr,pwdata,prdata_ref,prdata_dut,pready_ref,pready_dut,pslverr_ref,pslverr_dut );
    end

    wire tb_match;
    wire tb_mismatch = ~tb_match;

    stimulus_gen stim1 (
        .clk,
        .*,
        .reset,
        .psel,
        .penable,
        .pwrite,
        .paddr,
        .pwdata
    );

    RefModule good1 (
        .clk,
        .reset,
        .psel,
        .penable,
        .pwrite,
        .paddr,
        .pwdata,
        .prdata(prdata_ref),
        .pready(pready_ref),
        .pslverr(pslverr_ref)
    );

    TopModule top_module1 (
        .clk,
        .reset,
        .psel,
        .penable,
        .pwrite,
        .paddr,
        .pwdata,
        .prdata(prdata_dut),
        .pready(pready_dut),
        .pslverr(pslverr_dut)
    );

    final begin
        if (stats1.errors_prdata) $display("Hint: Output '%s' has %0d mismatches. First mismatch occurred at time %0d.", "prdata", stats1.errors_prdata, stats1.errortime_prdata);
        else $display("Hint: Output '%s' has no mismatches.", "prdata");

        $display("Hint: Total mismatched samples is %1d out of %1d samples\n", stats1.errors, stats1.clocks);
        $display("Simulation finished at %0d ps", $time);
        $display("Mismatches: %1d in %1d samples", stats1.errors, stats1.clocks);
    end

    assign tb_match =
        ( { prdata_ref, pready_ref, pslverr_ref }
          === ( { prdata_ref, pready_ref, pslverr_ref } ^ { prdata_dut, pready_dut, pslverr_dut } ^ { prdata_ref, pready_ref, pslverr_ref } ) );

    always @(posedge clk, negedge clk) begin
        stats1.clocks++;
        if (!tb_match) begin
            if (stats1.errors == 0) stats1.errortime = $time;
            stats1.errors++;
        end
        if (prdata_ref !== (prdata_ref ^ prdata_dut ^ prdata_ref))
        begin if (stats1.errors_prdata == 0) stats1.errortime_prdata = $time;
            stats1.errors_prdata = stats1.errors_prdata+1'b1; end
        if (pready_ref !== (pready_ref ^ pready_dut ^ pready_ref))
        begin if (stats1.errors_pready == 0) stats1.errortime_pready = $time;
            stats1.errors_pready = stats1.errors_pready+1'b1; end
        if (pslverr_ref !== (pslverr_ref ^ pslverr_dut ^ pslverr_ref))
        begin if (stats1.errors_pslverr == 0) stats1.errortime_pslverr = $time;
            stats1.errors_pslverr = stats1.errors_pslverr+1'b1; end
    end

   initial begin
     #3000000
     $display("TIMEOUT");
     $finish();
   end

endmodule

