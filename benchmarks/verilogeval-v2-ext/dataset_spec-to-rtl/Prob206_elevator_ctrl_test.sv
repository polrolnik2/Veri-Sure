`timescale 1 ps/1 ps
`define OK 12
`define INCORRECT 13


module stimulus_gen (
    input clk,
    output logic reset,
    output logic req0,
    output logic req1,
    output logic req2,
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
        {req2, req1, req0} <= 3'b000;
        @(negedge clk) wavedrom_start("3-floor elevator controller");

        repeat(3) @(posedge clk);
        @(negedge clk) reset <= 1'b0;

        // Directed requests.
        @(negedge clk) req2 <= 1'b1;
        @(negedge clk) req2 <= 1'b0;
        repeat(5) @(negedge clk);
        @(negedge clk) req0 <= 1'b1;
        @(negedge clk) req0 <= 1'b0;

        // Random request pulses.
        repeat(300) @(negedge clk) begin
            req0 <= !($random & 63);
            req1 <= !($random & 63);
            req2 <= !($random & 63);
        end

        wavedrom_stop();
        repeat(80) @(posedge clk, negedge clk) begin
            req0 <= $random;
            req1 <= $random;
            req2 <= $random;
        end
        $finish;
    end

endmodule

module tb();

    typedef struct packed {
        int errors;
        int errortime;
        int errors_floor;
        int errortime_floor;
        int errors_dir;
        int errortime_dir;
        int errors_door_open;
        int errortime_door_open;

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
    logic req0;
    logic req1;
    logic req2;

    logic [1:0] floor_ref;
    logic [1:0] dir_ref;
    logic door_ref;

    logic [1:0] floor_dut;
    logic [1:0] dir_dut;
    logic door_dut;

    initial begin
        $dumpfile("wave.vcd");
        $dumpvars(1, stim1.clk, tb_mismatch ,clk,reset,req0,req1,req2,floor_ref,dir_ref,door_ref,floor_dut,dir_dut,door_dut );
    end


    wire tb_match;       // Verification
    wire tb_mismatch = ~tb_match;

    stimulus_gen stim1 (
        .clk,
        .* ,
        .reset,
        .req0,
        .req1,
        .req2 );
    RefModule good1 (
        .clk,
        .reset,
        .req0,
        .req1,
        .req2,
        .floor(floor_ref),
        .dir(dir_ref),
        .door_open(door_ref) );

    TopModule top_module1 (
        .clk,
        .reset,
        .req0,
        .req1,
        .req2,
        .floor(floor_dut),
        .dir(dir_dut),
        .door_open(door_dut) );


    bit strobe = 0;
    task wait_for_end_of_timestep;
        repeat(5) begin
            strobe <= !strobe;  // Try to delay until the very end of the time step.
            @(strobe);
        end
    endtask


    final begin
        if (stats1.errors_floor) $display("Hint: Output '%s' has %0d mismatches. First mismatch occurred at time %0d.", "floor", stats1.errors_floor, stats1.errortime_floor);
        else $display("Hint: Output '%s' has no mismatches.", "floor");

        if (stats1.errors_dir) $display("Hint: Output '%s' has %0d mismatches. First mismatch occurred at time %0d.", "dir", stats1.errors_dir, stats1.errortime_dir);
        else $display("Hint: Output '%s' has no mismatches.", "dir");

        if (stats1.errors_door_open) $display("Hint: Output '%s' has %0d mismatches. First mismatch occurred at time %0d.", "door_open", stats1.errors_door_open, stats1.errortime_door_open);
        else $display("Hint: Output '%s' has no mismatches.", "door_open");

        $display("Hint: Total mismatched samples is %1d out of %1d samples\n", stats1.errors, stats1.clocks);
        $display("Simulation finished at %0d ps", $time);
        $display("Mismatches: %1d in %1d samples", stats1.errors, stats1.clocks);
    end

    // Verification: XORs on the right makes any X in good_vector match anything, but X in dut_vector will only match X.
    assign tb_match = ( { floor_ref, dir_ref, door_ref } === ( { floor_ref, dir_ref, door_ref } ^ { floor_dut, dir_dut, door_dut } ^ { floor_ref, dir_ref, door_ref } ) );
    // Use explicit sensitivity list here. @(*) causes NetProc::nex_input() to be called when trying to compute
    // the sensitivity list of the @(strobe) process, which isn't implemented.
    always @(posedge clk, negedge clk) begin

        stats1.clocks++;
        if (!tb_match) begin
            if (stats1.errors == 0) stats1.errortime = $time;
            stats1.errors++;
        end
        if (floor_ref !== ( floor_ref ^ floor_dut ^ floor_ref ))
        begin if (stats1.errors_floor == 0) stats1.errortime_floor = $time;
            stats1.errors_floor = stats1.errors_floor+1'b1; end

        if (dir_ref !== ( dir_ref ^ dir_dut ^ dir_ref ))
        begin if (stats1.errors_dir == 0) stats1.errortime_dir = $time;
            stats1.errors_dir = stats1.errors_dir+1'b1; end

        if (door_ref !== ( door_ref ^ door_dut ^ door_ref ))
        begin if (stats1.errors_door_open == 0) stats1.errortime_door_open = $time;
            stats1.errors_door_open = stats1.errors_door_open+1'b1; end

    end

   // add timeout after 100K cycles
   initial begin
     #1000000
     $display("TIMEOUT");
     $finish();
   end

endmodule

