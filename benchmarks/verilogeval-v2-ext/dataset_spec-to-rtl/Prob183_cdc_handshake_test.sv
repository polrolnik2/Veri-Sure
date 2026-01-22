`timescale 1 ps/1 ps
`define OK 12
`define INCORRECT 13


module stimulus_gen (
    input  src_clk,
    input  dst_clk,
    input  src_ready_ref,
    output logic src_reset,
    output logic dst_reset,
    output logic src_valid,
    output logic [7:0] src_data,
    output logic dst_ready,
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

    // Source driver: follow ready/valid protocol and hold data stable while waiting.
    always_ff @(posedge src_clk) begin
        if (src_reset) begin
            src_valid <= 1'b0;
            src_data <= 8'd0;
        end else begin
            if (src_valid && !src_ready_ref) begin
                // Hold.
                src_valid <= 1'b1;
                src_data <= src_data;
            end else begin
                src_valid <= !($random & 3); // ~25% chance
                if (!($random & 3)) begin
                    src_data <= $random;
                end else begin
                    src_data <= src_data;
                end
            end
        end
    end

    // Destination driver: random backpressure.
    always_ff @(posedge dst_clk) begin
        if (dst_reset) begin
            dst_ready <= 1'b0;
        end else begin
            dst_ready <= $random;
        end
    end

    initial begin
        src_reset <= 1'b1;
        dst_reset <= 1'b1;
        src_valid <= 1'b0;
        src_data <= 8'd0;
        dst_ready <= 1'b0;

        wavedrom_start("CDC Req/Ack handshake (byte transfer)");

        repeat(4) @(posedge src_clk);
        repeat(2) @(posedge dst_clk);
        @(negedge src_clk) src_reset <= 1'b0;
        @(negedge dst_clk) dst_reset <= 1'b0;

        // Run for a while.
        repeat(600) @(posedge src_clk);

        wavedrom_stop();
        #1 $finish;
    end

endmodule

module tb();

    typedef struct packed {
        int errors;
        int errortime;
        int errors_src_ready;
        int errortime_src_ready;
        int errors_dst_valid;
        int errortime_dst_valid;
        int errors_dst_data;
        int errortime_dst_data;

        int clocks;
    } stats;

    stats stats1;


    wire[511:0] wavedrom_title;
    wire wavedrom_enable;
    int wavedrom_hide_after_time;

    reg src_clk=0;
    reg dst_clk=0;
    initial forever #5 src_clk = ~src_clk;
    initial forever #9 dst_clk = ~dst_clk;

    logic src_reset;
    logic dst_reset;
    logic src_valid;
    logic [7:0] src_data;
    logic src_ready_ref;
    logic src_ready_dut;
    logic dst_valid_ref;
    logic dst_valid_dut;
    logic [7:0] dst_data_ref;
    logic [7:0] dst_data_dut;
    logic dst_ready;

    initial begin
        $dumpfile("wave.vcd");
        $dumpvars(1, tb_mismatch ,src_clk,dst_clk,src_reset,dst_reset,src_valid,src_ready_ref,src_ready_dut,src_data,dst_valid_ref,dst_valid_dut,dst_data_ref,dst_data_dut,dst_ready );
    end


    wire tb_match;       // Verification
    wire tb_mismatch = ~tb_match;

    stimulus_gen stim1 (
        .src_clk,
        .dst_clk,
        .src_ready_ref(src_ready_ref),
        .* );
    RefModule good1 (
        .src_clk,
        .src_reset,
        .src_valid,
        .src_data,
        .src_ready(src_ready_ref),
        .dst_clk,
        .dst_reset,
        .dst_valid(dst_valid_ref),
        .dst_data(dst_data_ref),
        .dst_ready );

    TopModule top_module1 (
        .src_clk,
        .src_reset,
        .src_valid,
        .src_data,
        .src_ready(src_ready_dut),
        .dst_clk,
        .dst_reset,
        .dst_valid(dst_valid_dut),
        .dst_data(dst_data_dut),
        .dst_ready );


    bit strobe = 0;
    task wait_for_end_of_timestep;
        repeat(5) begin
            strobe <= !strobe;  // Try to delay until the very end of the time step.
            @(strobe);
        end
    endtask


    final begin
        if (stats1.errors_src_ready) $display("Hint: Output '%s' has %0d mismatches. First mismatch occurred at time %0d.", "src_ready", stats1.errors_src_ready, stats1.errortime_src_ready);
        else $display("Hint: Output '%s' has no mismatches.", "src_ready");

        if (stats1.errors_dst_valid) $display("Hint: Output '%s' has %0d mismatches. First mismatch occurred at time %0d.", "dst_valid", stats1.errors_dst_valid, stats1.errortime_dst_valid);
        else $display("Hint: Output '%s' has no mismatches.", "dst_valid");

        if (stats1.errors_dst_data) $display("Hint: Output '%s' has %0d mismatches. First mismatch occurred at time %0d.", "dst_data", stats1.errors_dst_data, stats1.errortime_dst_data);
        else $display("Hint: Output '%s' has no mismatches.", "dst_data");

        $display("Hint: Total mismatched samples is %1d out of %1d samples\n", stats1.errors, stats1.clocks);
        $display("Simulation finished at %0d ps", $time);
        $display("Mismatches: %1d in %1d samples", stats1.errors, stats1.clocks);
    end

    // Verification: XORs on the right makes any X in good_vector match anything, but X in dut_vector will only match X.
    assign tb_match = ( { src_ready_ref, dst_valid_ref, dst_data_ref } === ( { src_ready_ref, dst_valid_ref, dst_data_ref } ^ { src_ready_dut, dst_valid_dut, dst_data_dut } ^ { src_ready_ref, dst_valid_ref, dst_data_ref } ) );
    // Use explicit sensitivity list here. @(*) causes NetProc::nex_input() to be called when trying to compute
    // the sensitivity list of the @(strobe) process, which isn't implemented.
    always @(posedge src_clk or negedge src_clk or posedge dst_clk or negedge dst_clk) begin

        stats1.clocks++;
        if (!tb_match) begin
            if (stats1.errors == 0) stats1.errortime = $time;
            stats1.errors++;
        end
        if (src_ready_ref !== ( src_ready_ref ^ src_ready_dut ^ src_ready_ref ))
        begin if (stats1.errors_src_ready == 0) stats1.errortime_src_ready = $time;
            stats1.errors_src_ready = stats1.errors_src_ready+1'b1; end

        if (dst_valid_ref !== ( dst_valid_ref ^ dst_valid_dut ^ dst_valid_ref ))
        begin if (stats1.errors_dst_valid == 0) stats1.errortime_dst_valid = $time;
            stats1.errors_dst_valid = stats1.errors_dst_valid+1'b1; end

        if (dst_data_ref !== ( dst_data_ref ^ dst_data_dut ^ dst_data_ref ))
        begin if (stats1.errors_dst_data == 0) stats1.errortime_dst_data = $time;
            stats1.errors_dst_data = stats1.errors_dst_data+1'b1; end

    end

   // add timeout after 100K cycles
   initial begin
     #2500000
     $display("TIMEOUT");
     $finish();
   end

endmodule

