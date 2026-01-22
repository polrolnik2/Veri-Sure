`timescale 1 ps/1 ps
`define OK 12
`define INCORRECT 13


module stimulus_gen (
    input clk,
    output logic reset,
    output logic [7:0] duty,
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
        duty <= 8'd0;
        @(negedge clk) wavedrom_start("PWM generator");

        repeat(2) @(posedge clk);
        @(negedge clk) reset <= 1'b0;

        // Directed duties.
        @(negedge clk) duty <= 8'd0;
        @(negedge clk) duty <= 8'd1;
        @(negedge clk) duty <= 8'd128;
        @(negedge clk) duty <= 8'd200;
        @(negedge clk) duty <= 8'd255;

        repeat(200) @(negedge clk) duty <= $random;

        wavedrom_stop();
        repeat(80) @(posedge clk, negedge clk) duty <= $random;
        $finish;
    end

endmodule

module tb();

    typedef struct packed {
        int errors;
        int errortime;
        int errors_pwm;
        int errortime_pwm;

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
    logic [7:0] duty;
    logic pwm_ref;
    logic pwm_dut;

    initial begin
        $dumpfile("wave.vcd");
        $dumpvars(1, stim1.clk, tb_mismatch ,clk,reset,duty,pwm_ref,pwm_dut );
    end


    wire tb_match;       // Verification
    wire tb_mismatch = ~tb_match;

    stimulus_gen stim1 (
        .clk,
        .* ,
        .reset,
        .duty );
    RefModule good1 (
        .clk,
        .reset,
        .duty,
        .pwm(pwm_ref) );

    TopModule top_module1 (
        .clk,
        .reset,
        .duty,
        .pwm(pwm_dut) );


    bit strobe = 0;
    task wait_for_end_of_timestep;
        repeat(5) begin
            strobe <= !strobe;  // Try to delay until the very end of the time step.
            @(strobe);
        end
    endtask


    final begin
        if (stats1.errors_pwm) $display("Hint: Output '%s' has %0d mismatches. First mismatch occurred at time %0d.", "pwm", stats1.errors_pwm, stats1.errortime_pwm);
        else $display("Hint: Output '%s' has no mismatches.", "pwm");

        $display("Hint: Total mismatched samples is %1d out of %1d samples\n", stats1.errors, stats1.clocks);
        $display("Simulation finished at %0d ps", $time);
        $display("Mismatches: %1d in %1d samples", stats1.errors, stats1.clocks);
    end

    // Verification: XORs on the right makes any X in good_vector match anything, but X in dut_vector will only match X.
    assign tb_match = ( { pwm_ref } === ( { pwm_ref } ^ { pwm_dut } ^ { pwm_ref } ) );
    // Use explicit sensitivity list here. @(*) causes NetProc::nex_input() to be called when trying to compute
    // the sensitivity list of the @(strobe) process, which isn't implemented.
    always @(posedge clk, negedge clk) begin

        stats1.clocks++;
        if (!tb_match) begin
            if (stats1.errors == 0) stats1.errortime = $time;
            stats1.errors++;
        end
        if (pwm_ref !== ( pwm_ref ^ pwm_dut ^ pwm_ref ))
        begin if (stats1.errors_pwm == 0) stats1.errortime_pwm = $time;
            stats1.errors_pwm = stats1.errors_pwm+1'b1; end

    end

   // add timeout after 100K cycles
   initial begin
     #1000000
     $display("TIMEOUT");
     $finish();
   end

endmodule

