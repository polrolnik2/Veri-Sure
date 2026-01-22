`timescale 1 ns / 1 ps

module tb;

    reg  [31:0] src1, src2;
    wire [31:0] out_ref;
    wire [31:0] out_dut;
    wire ex_ref, ovf_ref, udf_ref;
    wire ex_dut, ovf_dut, udf_dut;

    integer errors = 0;
    integer samples = 0;

    // Instantiate reference (ports: a, b, exception, overflow, underflow, out)
    RefModule ref_inst (
        .a(src1),
        .b(src2),
        .exception(ex_ref),
        .overflow(ovf_ref),
        .underflow(udf_ref),
        .out(out_ref)
    );

    // Instantiate DUT wrapper (TopModule has the same port list as RefModule)
    TopModule dut_inst (
        .a(src1),
        .b(src2),
        .exception(ex_dut),
        .overflow(ovf_dut),
        .underflow(udf_dut),
        .out(out_dut)
    );

    task check(input [31:0] a, input [31:0] b);
    begin
        src1 = a;
        src2 = b;
        #1; // allow combinational settle
        samples = samples + 1;
        if (out_ref !== out_dut) begin
            errors = errors + 1;
            $display("Mismatch @%0t: src1=%h src2=%h ref=%h dut=%h", $time, src1, src2, out_ref, out_dut);
        end
    end
    endtask

    initial begin
        $dumpfile("fp32_multiplier_wave.vcd");
        $dumpvars(0, tb);

        // Test vectors
        check(32'h3F800000, 32'h40000000); // 1.0 * 2.0
        check(32'h3F800000, 32'h40400000); // 1.0 * 3.0
        check(32'hC0000000, 32'hC0800000); // -2.0 * -4.0
        check(32'h7F800000, 32'hFF800000); // +INF * -INF
        check(32'h7FC00000, 32'h7FC00000); // NaN * NaN
        check(32'h00000000, 32'h3F800000); // 0 * 1.0
        check(32'h3F800000, 32'h3F800000); // 1.0 * 1.0

        $display("Simulation finished at %0t, errors=%0d", $time, errors);
        $finish;
    end

    // For checker: emit standardized mismatch summary
    final begin
        $display("Mismatches: %1d in %1d samples", errors, samples);
    end

endmodule

