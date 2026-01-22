`timescale 1 ps/1 ps
`define OK 12
`define INCORRECT 13


module stimulus_gen (
    input clk,
    output logic reset,
    output logic car_side,
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

    initial begin
        reset <= 1'b1;
        car_side <= 1'b0;
        @(negedge clk) wavedrom_start("Traffic light with side sensor");

        repeat(3) @(posedge clk);
        @(negedge clk) reset <= 1'b0;

        // Inject a short request (latched).
        repeat(12) @(negedge clk);
        car_side <= 1'b1;
        @(negedge clk) car_side <= 1'b0;

        // Random requests.
        repeat(300) @(negedge clk) begin
            car_side <= !($random & 15);
        end

        wavedrom_stop();
        repeat(80) @(posedge clk, negedge clk) car_side <= $random;
        $finish;
    end

endmodule

module tb();

    typedef struct packed {
        int errors;
        int errortime;
        int errors_main_light;
        int errortime_main_light;
        int errors_side_light;
        int errortime_side_light;

        int clocks;
    } stats;

    stats stats1;


    wire[511:0] wavedrom_title;
    wire wavedrom_enable;
    int wavedrom_hide_after_time;

    reg clk=0;
    initial forever
        #5 clk = ~clk;

    logic reset;
    logic car_side;
    logic [1:0] main_ref;
    logic [1:0] side_ref;
    logic [1:0] main_dut;
    logic [1:0] side_dut;

    initial begin
        $dumpfile("wave.vcd");
        $dumpvars(1, stim1.clk, tb_mismatch ,clk,reset,car_side,main_ref,side_ref,main_dut,side_dut );
    end


    wire tb_match;       // Verification
    wire tb_mismatch = ~tb_match;

    stimulus_gen stim1 (
        .clk,
        .* ,
        .reset,
        .car_side );
    RefModule good1 (
        .clk,
        .reset,
        .car_side,
        .main_light(main_ref),
        .side_light(side_ref) );

    TopModule top_module1 (
        .clk,
        .reset,
        .car_side,
        .main_light(main_dut),
        .side_light(side_dut) );


    bit strobe = 0;
    task wait_for_end_of_timestep;
        repeat(5) begin
            strobe <= !strobe;  // Try to delay until the very end of the time step.
            @(strobe);
        end
    endtask


    final begin
        if (stats1.errors_main_light) $display("Hint: Output '%s' has %0d mismatches. First mismatch occurred at time %0d.", "main_light", stats1.errors_main_light, stats1.errortime_main_light);
        else $display("Hint: Output '%s' has no mismatches.", "main_light");

        if (stats1.errors_side_light) $display("Hint: Output '%s' has %0d mismatches. First mismatch occurred at time %0d.", "side_light", stats1.errors_side_light, stats1.errortime_side_light);
        else $display("Hint: Output '%s' has no mismatches.", "side_light");

        $display("Hint: Total mismatched samples is %1d out of %1d samples\n", stats1.errors, stats1.clocks);
        $display("Simulation finished at %0d ps", $time);
        $display("Mismatches: %1d in %1d samples", stats1.errors, stats1.clocks);
    end

    // Verification: XORs on the right makes any X in good_vector match anything, but X in dut_vector will only match X.
    assign tb_match = ( { main_ref, side_ref } === ( { main_ref, side_ref } ^ { main_dut, side_dut } ^ { main_ref, side_ref } ) );
    // Use explicit sensitivity list here. @(*) causes NetProc::nex_input() to be called when trying to compute
    // the sensitivity list of the @(strobe) process, which isn't implemented.
    always @(posedge clk, negedge clk) begin

        stats1.clocks++;
        if (!tb_match) begin
            if (stats1.errors == 0) stats1.errortime = $time;
            stats1.errors++;
        end
        if (main_ref !== ( main_ref ^ main_dut ^ main_ref ))
        begin if (stats1.errors_main_light == 0) stats1.errortime_main_light = $time;
            stats1.errors_main_light = stats1.errors_main_light+1'b1; end

        if (side_ref !== ( side_ref ^ side_dut ^ side_ref ))
        begin if (stats1.errors_side_light == 0) stats1.errortime_side_light = $time;
            stats1.errors_side_light = stats1.errors_side_light+1'b1; end

    end

   // add timeout after 100K cycles
   initial begin
     #1000000
     $display("TIMEOUT");
     $finish();
   end

endmodule

