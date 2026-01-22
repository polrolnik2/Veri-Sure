`timescale 1ns/1ps

module tb;

    reg  [31:0] a, b; 
    wire [31:0] c;    
    integer errors = 0;
    integer samples = 0;
    wire [31:0] ref_c;
    wire [31:0] dut_c;

    RefModule ref_inst (
        .src1(a),
        .src2(b),
        .out(ref_c)
    );

    TopModule dut_inst (
        .src1(a),
        .src2(b),
        .out(dut_c)
    );

    task check(input [31:0] a_in, input [31:0] b_in);
    begin
        a = a_in;    
        b = b_in;    
        #1;          
        samples = samples + 1;
        if (ref_c !== dut_c) begin
            errors = errors + 1;
            $display("Mismatch @%0t: a=%h b=%h ref=%h dut=%h", $time, a, b, ref_c, dut_c);
        end
    end
    endtask

    initial begin
        $dumpfile("fp32_adder_wave.vcd");
        $dumpvars(0, tb);

        check(32'b01000000000000000000000000000001, 32'b01000000000000000000000000000001); 
        check(32'b01111111111110000000000000000000, 32'b01000000000000000000000000000001); 
        check(32'b01111111100000000000000000000000, 32'b01000000000000000000000000000001); 
        check(32'b00000000000000000000000000000001, 32'b00000000000000000000000000000010); 
        check(32'b01000000000000000000000000000001, 32'b01000000000000000000000000000010); 
        check(32'b00000000000000000000000000000001, 32'b00000000000000000000000000000001); 
        check(32'b01111111000000000000000000000000, 32'b01111111000000000000000000000000); 

        $display("Simulation finished at %0t, errors=%0d", $time, errors);
        $finish;
    end

    final begin
        $display("Mismatches: %1d in %1d samples", errors, samples);
    end

endmodule




