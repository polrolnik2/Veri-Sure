`timescale 1 ps/1 ps
`define OK 12
`define INCORRECT 13


module stimulus_gen (
    input clk,
    output logic [3:0] data_in,
    output logic [6:0] code_in,
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

    function automatic logic [6:0] hamming_encode(input logic [3:0] d);
        logic p1, p2, p4;
        begin
            p1 = d[0] ^ d[1] ^ d[3];
            p2 = d[0] ^ d[2] ^ d[3];
            p4 = d[1] ^ d[2] ^ d[3];
            hamming_encode = {d[3], d[2], d[1], p4, d[0], p2, p1};
        end
    endfunction

    initial begin
        data_in <= 4'd0;
        code_in <= 7'd0;
        @(negedge clk) wavedrom_start("Hamming(7,4) encode + SEC decode");

        // Directed example with and without a single-bit error.
        @(posedge clk) begin
            data_in <= 4'hA;
            code_in <= hamming_encode(4'hA);
        end
        @(posedge clk) begin
            data_in <= 4'hA;
            code_in <= hamming_encode(4'hA) ^ 7'b0001000; // flip bit 3 (position 4)
        end

        repeat(80) @(posedge clk) begin
            logic [3:0] d;
            logic [6:0] c;
            int bitpos;

            d = $random;
            c = hamming_encode(d);

            // Inject a single-bit error about 50% of the time.
            if ($random & 1) begin
                bitpos = ($random % 7);
                if (bitpos < 0) bitpos = -bitpos;
                c = c ^ (7'b1 << bitpos);
            end

            data_in <= d;
            code_in <= c;
        end

        wavedrom_stop();
        repeat(80) @(posedge clk, negedge clk) begin
            data_in <= $random;
            code_in <= $random;
        end
        $finish;
    end

endmodule

module tb();

    typedef struct packed {
        int errors;
        int errortime;
        int errors_encoded;
        int errortime_encoded;
        int errors_corrected;
        int errortime_corrected;
        int errors_data_out;
        int errortime_data_out;
        int errors_err_pos;
        int errortime_err_pos;
        int errors_error;
        int errortime_error;

        int clocks;
    } stats;

    stats stats1;


    wire[511:0] wavedrom_title;
    wire wavedrom_enable;
    int wavedrom_hide_after_time;

    reg clk=0;
    initial forever
        #5 clk = ~clk;

    logic [3:0] data_in;
    logic [6:0] code_in;

    logic [6:0] encoded_ref;
    logic [6:0] corrected_ref;
    logic [3:0] data_out_ref;
    logic [2:0] err_pos_ref;
    logic error_ref;

    logic [6:0] encoded_dut;
    logic [6:0] corrected_dut;
    logic [3:0] data_out_dut;
    logic [2:0] err_pos_dut;
    logic error_dut;

    initial begin
        $dumpfile("wave.vcd");
        $dumpvars(
            1,
            stim1.clk,
            tb_mismatch,
            data_in,
            code_in,
            encoded_ref,
            corrected_ref,
            data_out_ref,
            err_pos_ref,
            error_ref,
            encoded_dut,
            corrected_dut,
            data_out_dut,
            err_pos_dut,
            error_dut
        );
    end


    wire tb_match;       // Verification
    wire tb_mismatch = ~tb_match;

    stimulus_gen stim1 (
        .clk,
        .* ,
        .data_in,
        .code_in );
    RefModule good1 (
        .data_in,
        .code_in,
        .encoded(encoded_ref),
        .corrected(corrected_ref),
        .data_out(data_out_ref),
        .err_pos(err_pos_ref),
        .error(error_ref) );

    TopModule top_module1 (
        .data_in,
        .code_in,
        .encoded(encoded_dut),
        .corrected(corrected_dut),
        .data_out(data_out_dut),
        .err_pos(err_pos_dut),
        .error(error_dut) );


    bit strobe = 0;
    task wait_for_end_of_timestep;
        repeat(5) begin
            strobe <= !strobe;  // Try to delay until the very end of the time step.
            @(strobe);
        end
    endtask


    final begin
        if (stats1.errors_encoded) $display("Hint: Output '%s' has %0d mismatches. First mismatch occurred at time %0d.", "encoded", stats1.errors_encoded, stats1.errortime_encoded);
        else $display("Hint: Output '%s' has no mismatches.", "encoded");

        if (stats1.errors_corrected) $display("Hint: Output '%s' has %0d mismatches. First mismatch occurred at time %0d.", "corrected", stats1.errors_corrected, stats1.errortime_corrected);
        else $display("Hint: Output '%s' has no mismatches.", "corrected");

        if (stats1.errors_data_out) $display("Hint: Output '%s' has %0d mismatches. First mismatch occurred at time %0d.", "data_out", stats1.errors_data_out, stats1.errortime_data_out);
        else $display("Hint: Output '%s' has no mismatches.", "data_out");

        if (stats1.errors_err_pos) $display("Hint: Output '%s' has %0d mismatches. First mismatch occurred at time %0d.", "err_pos", stats1.errors_err_pos, stats1.errortime_err_pos);
        else $display("Hint: Output '%s' has no mismatches.", "err_pos");

        if (stats1.errors_error) $display("Hint: Output '%s' has %0d mismatches. First mismatch occurred at time %0d.", "error", stats1.errors_error, stats1.errortime_error);
        else $display("Hint: Output '%s' has no mismatches.", "error");

        $display("Hint: Total mismatched samples is %1d out of %1d samples\n", stats1.errors, stats1.clocks);
        $display("Simulation finished at %0d ps", $time);
        $display("Mismatches: %1d in %1d samples", stats1.errors, stats1.clocks);
    end

    // Verification: XORs on the right makes any X in good_vector match anything, but X in dut_vector will only match X.
    assign tb_match = ( { encoded_ref, corrected_ref, data_out_ref, err_pos_ref, error_ref }
        === ( { encoded_ref, corrected_ref, data_out_ref, err_pos_ref, error_ref }
        ^ { encoded_dut, corrected_dut, data_out_dut, err_pos_dut, error_dut }
        ^ { encoded_ref, corrected_ref, data_out_ref, err_pos_ref, error_ref } ) );
    // Use explicit sensitivity list here. @(*) causes NetProc::nex_input() to be called when trying to compute
    // the sensitivity list of the @(strobe) process, which isn't implemented.
    always @(posedge clk, negedge clk) begin

        stats1.clocks++;
        if (!tb_match) begin
            if (stats1.errors == 0) stats1.errortime = $time;
            stats1.errors++;
        end
        if (encoded_ref !== ( encoded_ref ^ encoded_dut ^ encoded_ref ))
        begin if (stats1.errors_encoded == 0) stats1.errortime_encoded = $time;
            stats1.errors_encoded = stats1.errors_encoded+1'b1; end

        if (corrected_ref !== ( corrected_ref ^ corrected_dut ^ corrected_ref ))
        begin if (stats1.errors_corrected == 0) stats1.errortime_corrected = $time;
            stats1.errors_corrected = stats1.errors_corrected+1'b1; end

        if (data_out_ref !== ( data_out_ref ^ data_out_dut ^ data_out_ref ))
        begin if (stats1.errors_data_out == 0) stats1.errortime_data_out = $time;
            stats1.errors_data_out = stats1.errors_data_out+1'b1; end

        if (err_pos_ref !== ( err_pos_ref ^ err_pos_dut ^ err_pos_ref ))
        begin if (stats1.errors_err_pos == 0) stats1.errortime_err_pos = $time;
            stats1.errors_err_pos = stats1.errors_err_pos+1'b1; end

        if (error_ref !== ( error_ref ^ error_dut ^ error_ref ))
        begin if (stats1.errors_error == 0) stats1.errortime_error = $time;
            stats1.errors_error = stats1.errors_error+1'b1; end

    end

   // add timeout after 100K cycles
   initial begin
     #1000000
     $display("TIMEOUT");
     $finish();
   end

endmodule

