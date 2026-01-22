`timescale 1 ps/1 ps
`define OK 12
`define INCORRECT 13


module stimulus_gen (
    input clk,
    output logic reset,
    output reg[511:0] wavedrom_title,
    output reg wavedrom_enable
);

    task wavedrom_start(input[511:0] title = "");
    endtask

    task wavedrom_stop;
        #1;
    endtask

    localparam int H_TOTAL = 800;
    localparam int V_TOTAL = 525;
    localparam int FRAME_CYCLES = H_TOTAL * V_TOTAL;

    initial begin
        reset <= 1'b1;
        @(negedge clk) wavedrom_start("VGA timing 640x480");
        repeat(2) @(posedge clk);
        reset <= 1'b0;

        // Run one full frame (+ a few cycles).
        repeat(FRAME_CYCLES + 20) @(posedge clk);

        // Mid-run reset and run a little more.
        @(posedge clk) reset <= 1'b1;
        @(posedge clk) reset <= 1'b0;
        repeat(2000) @(posedge clk);

        wavedrom_stop();
        $finish;
    end

endmodule

module tb();

    typedef struct packed {
        int errors;
        int errortime;
        int errors_x;
        int errortime_x;
        int errors_y;
        int errortime_y;
        int errors_hsync;
        int errortime_hsync;
        int errors_vsync;
        int errortime_vsync;
        int errors_active_video;
        int errortime_active_video;
        int clocks;
    } stats;

    stats stats1;

    wire[511:0] wavedrom_title;
    wire wavedrom_enable;
    int wavedrom_hide_after_time;

    reg clk=0;
    initial forever #5 clk = ~clk;

    logic reset;
    logic [9:0] x_ref, x_dut;
    logic [9:0] y_ref, y_dut;
    logic hsync_ref, hsync_dut;
    logic vsync_ref, vsync_dut;
    logic active_video_ref, active_video_dut;

    initial begin
        $dumpfile("wave.vcd");
        $dumpvars(1, stim1.clk, tb_mismatch ,clk,reset,x_ref,x_dut,y_ref,y_dut,hsync_ref,hsync_dut,vsync_ref,vsync_dut,active_video_ref,active_video_dut );
    end

    wire tb_match;
    wire tb_mismatch = ~tb_match;

    stimulus_gen stim1 (
        .clk,
        .*,
        .reset
    );

    RefModule good1 (
        .clk,
        .reset,
        .x(x_ref),
        .y(y_ref),
        .hsync(hsync_ref),
        .vsync(vsync_ref),
        .active_video(active_video_ref)
    );

    TopModule top_module1 (
        .clk,
        .reset,
        .x(x_dut),
        .y(y_dut),
        .hsync(hsync_dut),
        .vsync(vsync_dut),
        .active_video(active_video_dut)
    );

    final begin
        $display("Hint: Total mismatched samples is %1d out of %1d samples\n", stats1.errors, stats1.clocks);
        $display("Simulation finished at %0d ps", $time);
        $display("Mismatches: %1d in %1d samples", stats1.errors, stats1.clocks);
    end

    assign tb_match =
        ( { x_ref, y_ref, hsync_ref, vsync_ref, active_video_ref }
          === ( { x_ref, y_ref, hsync_ref, vsync_ref, active_video_ref }
                ^ { x_dut, y_dut, hsync_dut, vsync_dut, active_video_dut }
                ^ { x_ref, y_ref, hsync_ref, vsync_ref, active_video_ref } ) );

    always @(posedge clk, negedge clk) begin
        stats1.clocks++;
        if (!tb_match) begin
            if (stats1.errors == 0) stats1.errortime = $time;
            stats1.errors++;
        end
        if (x_ref !== (x_ref ^ x_dut ^ x_ref))
        begin if (stats1.errors_x == 0) stats1.errortime_x = $time;
            stats1.errors_x = stats1.errors_x+1'b1; end
        if (y_ref !== (y_ref ^ y_dut ^ y_ref))
        begin if (stats1.errors_y == 0) stats1.errortime_y = $time;
            stats1.errors_y = stats1.errors_y+1'b1; end
        if (hsync_ref !== (hsync_ref ^ hsync_dut ^ hsync_ref))
        begin if (stats1.errors_hsync == 0) stats1.errortime_hsync = $time;
            stats1.errors_hsync = stats1.errors_hsync+1'b1; end
        if (vsync_ref !== (vsync_ref ^ vsync_dut ^ vsync_ref))
        begin if (stats1.errors_vsync == 0) stats1.errortime_vsync = $time;
            stats1.errors_vsync = stats1.errors_vsync+1'b1; end
        if (active_video_ref !== (active_video_ref ^ active_video_dut ^ active_video_ref))
        begin if (stats1.errors_active_video == 0) stats1.errortime_active_video = $time;
            stats1.errors_active_video = stats1.errors_active_video+1'b1; end
    end

   initial begin
     #15000000
     $display("TIMEOUT");
     $finish();
   end

endmodule

