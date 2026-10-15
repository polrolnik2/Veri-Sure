`timescale 1ns/1ps

module i2c_master_bit_ctrl_tb;

    localparam integer MAX_QUEUE_SIZE = 10;

    localparam logic [3:0] CMD_NOP   = 4'b0000;
    localparam logic [3:0] CMD_START = 4'b0001;
    localparam logic [3:0] CMD_STOP  = 4'b0010;
    localparam logic [3:0] CMD_WRITE = 4'b0100;
    localparam logic [3:0] CMD_READ  = 4'b1000;

    logic        clk;
    logic        rst;
    logic        nReset;
    logic        ena;
    logic [15:0] clk_cnt;
    logic [3:0]  cmd;
    logic        cmd_ack;
    logic        busy;
    logic        al;
    logic        din;
    logic        dout;
    logic        scl_i;
    logic        scl_o;
    logic        scl_oen;
    logic        sda_i;
    logic        sda_o;
    logic        sda_oen;

    logic ext_scl_low;
    logic ext_sda_low;

    integer mismatch_count;
    integer sample_count;
    time first_mismatch_time;
    logic history_dumped;

    integer cmd_ack_mismatches;
    integer busy_mismatches;
    integer al_mismatches;
    integer dout_mismatches;
    integer scl_o_mismatches;
    integer scl_oen_mismatches;
    integer sda_o_mismatches;
    integer sda_oen_mismatches;

    time cmd_ack_first_time;
    time busy_first_time;
    time al_first_time;
    time dout_first_time;
    time scl_o_first_time;
    time scl_oen_first_time;
    time sda_o_first_time;
    time sda_oen_first_time;

    logic previous_cmd_ack;
    logic al_seen;

    logic cmd_hist[$];
    logic din_hist[$];
    logic ena_hist[$];
    logic rst_hist[$];
    logic nreset_hist[$];

    logic cmd_ack_got_hist[$];
    logic cmd_ack_exp_hist[$];
    logic busy_got_hist[$];
    logic busy_exp_hist[$];
    logic al_got_hist[$];
    logic al_exp_hist[$];
    logic dout_got_hist[$];
    logic dout_exp_hist[$];
    logic scl_o_got_hist[$];
    logic scl_o_exp_hist[$];
    logic scl_oen_got_hist[$];
    logic scl_oen_exp_hist[$];
    logic sda_o_got_hist[$];
    logic sda_o_exp_hist[$];
    logic sda_oen_got_hist[$];
    logic sda_oen_exp_hist[$];

    logic scenario_active;
    integer scenario_base_mismatches;
    time scenario_start_time;
    time scenario_first_mismatch_time;

    i2c_master_bit_ctrl dut (
        .clk     (clk),
        .rst     (rst),
        .nReset  (nReset),
        .ena     (ena),
        .clk_cnt (clk_cnt),
        .cmd     (cmd),
        .cmd_ack (cmd_ack),
        .busy    (busy),
        .al      (al),
        .din     (din),
        .dout    (dout),
        .scl_i   (scl_i),
        .scl_o   (scl_o),
        .scl_oen (scl_oen),
        .sda_i   (sda_i),
        .sda_o   (sda_o),
        .sda_oen (sda_oen)
    );

    assign scl_i = ((!scl_oen) || ext_scl_low) ? 1'b0 : 1'b1;
    assign sda_i = ((!sda_oen) || ext_sda_low) ? 1'b0 : 1'b1;

    initial begin
        clk = 1'b0;
        forever #5 clk = ~clk;
    end

    initial begin
        $dumpfile("wave.vcd");
        $dumpvars(0, dut);
        $dumpvars(0, dut);
    end

    task automatic dump_history;
        integer h;
        begin
            $display("FIRST MISMATCH HISTORY, newest samples last:");
            for (h = 0; h < cmd_hist.size(); h = h + 1) begin
                $display("HIST %0d rst=%b nReset=%b ena=%b cmd=%b din=%b ack=%b/%b busy=%b/%b al=%b/%b dout=%b/%b scl_o=%b/%b scl_oen=%b/%b sda_o=%b/%b sda_oen=%b/%b",
                         h,
                         rst_hist[h],
                         nreset_hist[h],
                         ena_hist[h],
                         cmd_hist[h],
                         din_hist[h],
                         cmd_ack_got_hist[h],
                         cmd_ack_exp_hist[h],
                         busy_got_hist[h],
                         busy_exp_hist[h],
                         al_got_hist[h],
                         al_exp_hist[h],
                         dout_got_hist[h],
                         dout_exp_hist[h],
                         scl_o_got_hist[h],
                         scl_o_exp_hist[h],
                         scl_oen_got_hist[h],
                         scl_oen_exp_hist[h],
                         sda_o_got_hist[h],
                         sda_o_exp_hist[h],
                         sda_oen_got_hist[h],
                         sda_oen_exp_hist[h]);
            end
        end
    endtask

    task automatic note_mismatch(
        input integer sig_id,
        input string sig_label,
        input logic actual_value,
        input logic expected_value
    );
        begin
            if (actual_value !== expected_value) begin
                if (mismatch_count == 0) begin
                    first_mismatch_time = $time;
                end
                if (scenario_active &&
                    (mismatch_count == scenario_base_mismatches)) begin
                    scenario_first_mismatch_time = $time;
                end

                $display("MISMATCH %s at time %0t: rst=%b nReset=%b ena=%b clk_cnt=%h cmd=%b din=%b scl_i=%b sda_i=%b | got=%b exp=%b",
                         sig_label,
                         $time,
                         rst,
                         nReset,
                         ena,
                         clk_cnt,
                         cmd,
                         din,
                         scl_i,
                         sda_i,
                         actual_value,
                         expected_value);

                if (!history_dumped) begin
                    history_dumped = 1'b1;
                    dump_history();
                end

                case (sig_id)
                    0: begin
                        cmd_ack_mismatches = cmd_ack_mismatches + 1;
                        if (cmd_ack_mismatches == 1)
                            cmd_ack_first_time = $time;
                    end
                    1: begin
                        busy_mismatches = busy_mismatches + 1;
                        if (busy_mismatches == 1)
                            busy_first_time = $time;
                    end
                    2: begin
                        al_mismatches = al_mismatches + 1;
                        if (al_mismatches == 1)
                            al_first_time = $time;
                    end
                    3: begin
                        dout_mismatches = dout_mismatches + 1;
                        if (dout_mismatches == 1)
                            dout_first_time = $time;
                    end
                    4: begin
                        scl_o_mismatches = scl_o_mismatches + 1;
                        if (scl_o_mismatches == 1)
                            scl_o_first_time = $time;
                    end
                    5: begin
                        scl_oen_mismatches = scl_oen_mismatches + 1;
                        if (scl_oen_mismatches == 1)
                            scl_oen_first_time = $time;
                    end
                    6: begin
                        sda_o_mismatches = sda_o_mismatches + 1;
                        if (sda_o_mismatches == 1)
                            sda_o_first_time = $time;
                    end
                    7: begin
                        sda_oen_mismatches = sda_oen_mismatches + 1;
                        if (sda_oen_mismatches == 1)
                            sda_oen_first_time = $time;
                    end
                    default: begin
                    end
                endcase

                mismatch_count = mismatch_count + 1;
            end
        end
    endtask

    task automatic check_outputs;
        logic exp_cmd_ack;
        logic exp_busy;
        logic exp_al;
        logic exp_dout;
        logic exp_scl_o;
        logic exp_scl_oen;
        logic exp_sda_o;
        logic exp_sda_oen;
        begin
            if (cmd_hist.size() >= MAX_QUEUE_SIZE) begin
                cmd_hist.delete(0);
                din_hist.delete(0);
                ena_hist.delete(0);
                rst_hist.delete(0);
                nreset_hist.delete(0);
                cmd_ack_got_hist.delete(0);
                cmd_ack_exp_hist.delete(0);
                busy_got_hist.delete(0);
                busy_exp_hist.delete(0);
                al_got_hist.delete(0);
                al_exp_hist.delete(0);
                dout_got_hist.delete(0);
                dout_exp_hist.delete(0);
                scl_o_got_hist.delete(0);
                scl_o_exp_hist.delete(0);
                scl_oen_got_hist.delete(0);
                scl_oen_exp_hist.delete(0);
                sda_o_got_hist.delete(0);
                sda_o_exp_hist.delete(0);
                sda_oen_got_hist.delete(0);
                sda_oen_exp_hist.delete(0);
            end

            exp_cmd_ack = cmd_ack;
            exp_busy = busy;
            exp_al = al;
            exp_dout = dout;
            exp_scl_o = 1'b0;
            exp_scl_oen = scl_oen;
            exp_sda_o = 1'b0;
            exp_sda_oen = sda_oen;

            if (previous_cmd_ack)
                exp_cmd_ack = 1'b0;

            if (al_seen)
                exp_al = 1'b1;

            if (rst || !nReset) begin
                exp_cmd_ack = 1'b0;
                exp_busy = 1'b0;
                exp_al = 1'b0;
                exp_dout = 1'b0;
                exp_scl_oen = 1'b1;
                exp_sda_oen = 1'b1;
            end
            else if (al_seen) begin
                exp_scl_oen = 1'b1;
                exp_sda_oen = 1'b1;
            end

            cmd_hist.push_back(cmd);
            din_hist.push_back(din);
            ena_hist.push_back(ena);
            rst_hist.push_back(rst);
            nreset_hist.push_back(nReset);

            cmd_ack_got_hist.push_back(cmd_ack);
            cmd_ack_exp_hist.push_back(exp_cmd_ack);
            busy_got_hist.push_back(busy);
            busy_exp_hist.push_back(exp_busy);
            al_got_hist.push_back(al);
            al_exp_hist.push_back(exp_al);
            dout_got_hist.push_back(dout);
            dout_exp_hist.push_back(exp_dout);
            scl_o_got_hist.push_back(scl_o);
            scl_o_exp_hist.push_back(exp_scl_o);
            scl_oen_got_hist.push_back(scl_oen);
            scl_oen_exp_hist.push_back(exp_scl_oen);
            sda_o_got_hist.push_back(sda_o);
            sda_o_exp_hist.push_back(exp_sda_o);
            sda_oen_got_hist.push_back(sda_oen);
            sda_oen_exp_hist.push_back(exp_sda_oen);

            sample_count = sample_count + 1;

            note_mismatch(0, "cmd_ack", cmd_ack, exp_cmd_ack);
            note_mismatch(1, "busy", busy, exp_busy);
            note_mismatch(2, "al", al, exp_al);
            note_mismatch(3, "dout", dout, exp_dout);
            note_mismatch(4, "scl_o", scl_o, exp_scl_o);
            note_mismatch(5, "scl_oen", scl_oen, exp_scl_oen);
            note_mismatch(6, "sda_o", sda_o, exp_sda_o);
            note_mismatch(7, "sda_oen", sda_oen, exp_sda_oen);

            if (rst || !nReset)
                al_seen = 1'b0;
            else if (al === 1'b1)
                al_seen = 1'b1;

            previous_cmd_ack = (cmd_ack === 1'b1);
        end
    endtask

    always @(negedge clk) begin
        check_outputs();
    end

    always @(negedge nReset) begin
        #1 check_outputs();
    end

    task automatic scenario_start(input string scen_label);
        begin
            scenario_active = 1'b1;
            scenario_base_mismatches = mismatch_count;
            scenario_start_time = $time;
            scenario_first_mismatch_time = 0;
            $display("[TEST %s] START at time %0t", scen_label, $time);
        end
    endtask

    task automatic scenario_end(input string scen_label);
        integer scen_mismatches;
        time scen_end_time;
        begin
            scen_end_time = $time;
            scen_mismatches = mismatch_count - scenario_base_mismatches;
            if (scen_mismatches == 0) begin
                $display("[TEST %s] PASS (window %0t..%0t)",
                         scen_label, scenario_start_time, scen_end_time);
            end
            else begin
                $display("[TEST %s] FAIL (%0d mismatches, first at time %0t, window %0t..%0t)",
                         scen_label,
                         scen_mismatches,
                         scenario_first_mismatch_time,
                         scenario_start_time,
                         scen_end_time);
            end
            scenario_active = 1'b0;
        end
    endtask

    task automatic apply_reset;
        begin
            cmd = CMD_NOP;
            din = 1'b0;
            ena = 1'b1;
            rst = 1'b1;
            nReset = 1'b0;
            #2;
            nReset = 1'b1;
            repeat (2) @(posedge clk);
            @(negedge clk);
            rst = 1'b0;
        end
    endtask

    task automatic launch_command(
        input logic [3:0] command_value,
        input logic data_value
    );
        begin
            cmd = command_value;
            din = data_value;
        end
    endtask

    task automatic wait_for_ack(
        input integer max_cycles,
        output logic got_ack,
        output logic saw_sda_low,
        output logic saw_scl_low,
        output logic saw_scl_release,
        output logic saw_sda_release
    );
        integer k;
        begin
            got_ack = 1'b0;
            saw_sda_low = 1'b0;
            saw_scl_low = 1'b0;
            saw_scl_release = 1'b0;
            saw_sda_release = 1'b0;

            for (k = 0; k < max_cycles; k = k + 1) begin
                if (!got_ack) begin
                    @(posedge clk);
                    @(negedge clk);

                    if (sda_oen === 1'b0)
                        saw_sda_low = 1'b1;
                    if (scl_oen === 1'b0)
                        saw_scl_low = 1'b1;
                    if (saw_scl_low && (scl_oen === 1'b1))
                        saw_scl_release = 1'b1;
                    if (saw_sda_low && (sda_oen === 1'b1))
                        saw_sda_release = 1'b1;

                    if (cmd_ack === 1'b1) begin
                        got_ack = 1'b1;
                        cmd = CMD_NOP;
                    end
                end
            end
        end
    endtask

    task automatic check_no_ack(
        input logic [3:0] command_value,
        input integer cycles
    );
        integer k;
        begin
            cmd = command_value;
            for (k = 0; k < cycles; k = k + 1) begin
                @(posedge clk);
                @(negedge clk);
                if (cmd_ack === 1'b1)
                    note_mismatch(0, "cmd_ack", cmd_ack, 1'b0);
            end
            cmd = CMD_NOP;
        end
    endtask

    task automatic check_phase_missing(
        input integer sig_id,
        input string sig_label,
        input logic actual_value,
        input logic expected_value
    );
        begin
            note_mismatch(sig_id, sig_label, actual_value, expected_value);
        end
    endtask

    task automatic run_arbitration_loss;
        integer k;
        logic injected;
        logic saw_scl_low;
        logic got_ack;
        begin
            injected = 1'b0;
            saw_scl_low = 1'b0;
            got_ack = 1'b0;
            ext_sda_low = 1'b0;
            launch_command(CMD_WRITE, 1'b1);

            for (k = 0; k < 80; k = k + 1) begin
                if (!got_ack && !al) begin
                    @(posedge clk);
                    @(negedge clk);

                    if (scl_oen === 1'b0)
                        saw_scl_low = 1'b1;

                    if (!injected &&
                        ((saw_scl_low && (scl_oen === 1'b1)) ||
                         (k >= 8))) begin
                        ext_sda_low = 1'b1;
                        injected = 1'b1;
                    end

                    if (cmd_ack === 1'b1) begin
                        got_ack = 1'b1;
                        note_mismatch(0, "cmd_ack", cmd_ack, 1'b0);
                    end
                end
            end

            cmd = CMD_NOP;
            if (al !== 1'b1)
                note_mismatch(2, "al", al, 1'b1);
            if (scl_oen !== 1'b1)
                note_mismatch(5, "scl_oen", scl_oen, 1'b1);
            if (sda_oen !== 1'b1)
                note_mismatch(7, "sda_oen", sda_oen, 1'b1);
            ext_sda_low = 1'b0;
        end
    endtask

    initial begin : stimulus
        integer c;
        logic got_ack;
        logic saw_sda_low;
        logic saw_scl_low;
        logic saw_scl_release;
        logic saw_sda_release;

        rst = 1'b0;
        nReset = 1'b1;
        ena = 1'b1;
        clk_cnt = 16'h0000;
        cmd = CMD_NOP;
        din = 1'b0;
        ext_scl_low = 1'b0;
        ext_sda_low = 1'b0;

        mismatch_count = 0;
        sample_count = 0;
        first_mismatch_time = 0;
        history_dumped = 1'b0;

        cmd_ack_mismatches = 0;
        busy_mismatches = 0;
        al_mismatches = 0;
        dout_mismatches = 0;
        scl_o_mismatches = 0;
        scl_oen_mismatches = 0;
        sda_o_mismatches = 0;
        sda_oen_mismatches = 0;

        cmd_ack_first_time = 0;
        busy_first_time = 0;
        al_first_time = 0;
        dout_first_time = 0;
        scl_o_first_time = 0;
        scl_oen_first_time = 0;
        sda_o_first_time = 0;
        sda_oen_first_time = 0;

        previous_cmd_ack = 1'b0;
        al_seen = 1'b0;
        scenario_active = 1'b0;
        scenario_base_mismatches = 0;
        scenario_start_time = 0;
        scenario_first_mismatch_time = 0;

        scenario_start("async_and_sync_reset");
        #2 nReset = 1'b0;
        #2 nReset = 1'b1;
        rst = 1'b1;
        @(posedge clk);
        @(negedge clk);
        rst = 1'b0;
        scenario_end("async_and_sync_reset");

        scenario_start("nop_and_unsupported_commands");
        clk_cnt = 16'h0000;
        apply_reset();
        check_no_ack(CMD_NOP, 6);
        for (c = 1; c < 16; c = c + 1) begin
            if ((c != CMD_START) &&
                (c != CMD_STOP) &&
                (c != CMD_WRITE) &&
                (c != CMD_READ)) begin
                check_no_ack(c[3:0], 6);
            end
        end
        scenario_end("nop_and_unsupported_commands");

        scenario_start("start_and_stop");
        clk_cnt = 16'h0000;
        apply_reset();

        launch_command(CMD_START, 1'b0);
        wait_for_ack(80, got_ack, saw_sda_low, saw_scl_low,
                     saw_scl_release, saw_sda_release);
        if (!got_ack)
            note_mismatch(0, "cmd_ack", cmd_ack, 1'b1);
        if (!saw_sda_low)
            check_phase_missing(7, "sda_oen", sda_oen, 1'b0);
        if (!saw_scl_low)
            check_phase_missing(5, "scl_oen", scl_oen, 1'b0);

        repeat (10) @(posedge clk);
        @(negedge clk);
        if (busy !== 1'b1)
            note_mismatch(1, "busy", busy, 1'b1);

        launch_command(CMD_STOP, 1'b0);
        wait_for_ack(100, got_ack, saw_sda_low, saw_scl_low,
                     saw_scl_release, saw_sda_release);
        if (!got_ack)
            note_mismatch(0, "cmd_ack", cmd_ack, 1'b1);
        if (!saw_sda_low)
            check_phase_missing(7, "sda_oen", sda_oen, 1'b0);
        if (!saw_scl_release)
            check_phase_missing(5, "scl_oen", scl_oen, 1'b1);
        if (!saw_sda_release)
            check_phase_missing(7, "sda_oen", sda_oen, 1'b1);

        repeat (12) @(posedge clk);
        @(negedge clk);
        if (busy !== 1'b0)
            note_mismatch(1, "busy", busy, 1'b0);
        scenario_end("start_and_stop");

        scenario_start("write_zero_and_one");
        clk_cnt = 16'h0000;
        apply_reset();

        launch_command(CMD_WRITE, 1'b0);
        wait_for_ack(100, got_ack, saw_sda_low, saw_scl_low,
                     saw_scl_release, saw_sda_release);
        if (!got_ack)
            note_mismatch(0, "cmd_ack", cmd_ack, 1'b1);
        if (!saw_sda_low)
            check_phase_missing(7, "sda_oen", sda_oen, 1'b0);
        if (!saw_scl_release)
            check_phase_missing(5, "scl_oen", scl_oen, 1'b1);
        if (!saw_scl_low)
            check_phase_missing(5, "scl_oen", scl_oen, 1'b0);
        if (al !== 1'b0)
            note_mismatch(2, "al", al, 1'b0);

        launch_command(CMD_WRITE, 1'b1);
        wait_for_ack(100, got_ack, saw_sda_low, saw_scl_low,
                     saw_scl_release, saw_sda_release);
        if (!got_ack)
            note_mismatch(0, "cmd_ack", cmd_ack, 1'b1);
        if (!saw_scl_release)
            check_phase_missing(5, "scl_oen", scl_oen, 1'b1);
        if (!saw_scl_low)
            check_phase_missing(5, "scl_oen", scl_oen, 1'b0);
        if (al !== 1'b0)
            note_mismatch(2, "al", al, 1'b0);
        scenario_end("write_zero_and_one");

        scenario_start("read_zero_and_one");
        clk_cnt = 16'h0000;
        apply_reset();

        ext_sda_low = 1'b1;
        launch_command(CMD_READ, 1'b0);
        wait_for_ack(100, got_ack, saw_sda_low, saw_scl_low,
                     saw_scl_release, saw_sda_release);
        if (!got_ack)
            note_mismatch(0, "cmd_ack", cmd_ack, 1'b1);
        if (!saw_scl_release)
            check_phase_missing(5, "scl_oen", scl_oen, 1'b1);
        if (!saw_scl_low)
            check_phase_missing(5, "scl_oen", scl_oen, 1'b0);
        repeat (4) @(posedge clk);
        @(negedge clk);
        if (dout !== 1'b0)
            note_mismatch(3, "dout", dout, 1'b0);

        apply_reset();
        ext_sda_low = 1'b0;
        launch_command(CMD_READ, 1'b0);
        wait_for_ack(100, got_ack, saw_sda_low, saw_scl_low,
                     saw_scl_release, saw_sda_release);
        if (!got_ack)
            note_mismatch(0, "cmd_ack", cmd_ack, 1'b1);
        if (!saw_scl_release)
            check_phase_missing(5, "scl_oen", scl_oen, 1'b1);
        if (!saw_scl_low)
            check_phase_missing(5, "scl_oen", scl_oen, 1'b0);
        repeat (4) @(posedge clk);
        @(negedge clk);
        if (dout !== 1'b1)
            note_mismatch(3, "dout", dout, 1'b1);
        scenario_end("read_zero_and_one");

        scenario_start("arbitration_loss");
        clk_cnt = 16'h0000;
        apply_reset();
        run_arbitration_loss();
        scenario_end("arbitration_loss");

        scenario_start("clock_stretching");
        clk_cnt = 16'h0000;
        apply_reset();
        ext_scl_low = 1'b1;
        launch_command(CMD_READ, 1'b0);
        wait_for_ack(25, got_ack, saw_sda_low, saw_scl_low,
                     saw_scl_release, saw_sda_release);
        if (got_ack)
            note_mismatch(0, "cmd_ack", cmd_ack, 1'b0);
        ext_scl_low = 1'b0;
        wait_for_ack(120, got_ack, saw_sda_low, saw_scl_low,
                     saw_scl_release, saw_sda_release);
        if (!got_ack)
            note_mismatch(0, "cmd_ack", cmd_ack, 1'b1);
        scenario_end("clock_stretching");

        scenario_start("ena_pause");
        clk_cnt = 16'h0000;
        apply_reset();
        ena = 1'b0;
        launch_command(CMD_START, 1'b0);
        repeat (12) @(posedge clk);
        @(negedge clk);
        if (cmd_ack === 1'b1)
            note_mismatch(0, "cmd_ack", cmd_ack, 1'b0);
        if (scl_oen !== 1'b1)
            note_mismatch(5, "scl_oen", scl_oen, 1'b1);
        if (sda_oen !== 1'b1)
            note_mismatch(7, "sda_oen", sda_oen, 1'b1);
        ena = 1'b1;
        wait_for_ack(100, got_ack, saw_sda_low, saw_scl_low,
                     saw_scl_release, saw_sda_release);
        if (!got_ack)
            note_mismatch(0, "cmd_ack", cmd_ack, 1'b1);
        scenario_end("ena_pause");

        scenario_start("prescaler_zero_and_one");
        clk_cnt = 16'h0000;
        apply_reset();
        launch_command(CMD_START, 1'b0);
        wait_for_ack(100, got_ack, saw_sda_low, saw_scl_low,
                     saw_scl_release, saw_sda_release);
        if (!got_ack)
            note_mismatch(0, "cmd_ack", cmd_ack, 1'b1);

        clk_cnt = 16'h0001;
        apply_reset();
        launch_command(CMD_START, 1'b0);
        wait_for_ack(180, got_ack, saw_sda_low, saw_scl_low,
                     saw_scl_release, saw_sda_release);
        if (!got_ack)
            note_mismatch(0, "cmd_ack", cmd_ack, 1'b1);
        scenario_end("prescaler_zero_and_one");

        scenario_start("prescaler_maximum_boundary");
        clk_cnt = 16'hffff;
        apply_reset();
        launch_command(CMD_START, 1'b0);
        wait_for_ack(40, got_ack, saw_sda_low, saw_scl_low,
                     saw_scl_release, saw_sda_release);
        if (got_ack)
            note_mismatch(0, "cmd_ack", cmd_ack, 1'b0);
        if (scl_oen !== 1'b1)
            note_mismatch(5, "scl_oen", scl_oen, 1'b1);
        if (sda_oen !== 1'b1)
            note_mismatch(7, "sda_oen", sda_oen, 1'b1);
        cmd = CMD_NOP;
        scenario_end("prescaler_maximum_boundary");

        scenario_start("filtered_glitch_and_stable_edges");
        clk_cnt = 16'h0004;
        apply_reset();

        ext_sda_low = 1'b1;
        @(negedge clk);
        ext_sda_low = 1'b0;
        repeat (8) @(posedge clk);
        @(negedge clk);
        if (busy !== 1'b0)
            note_mismatch(1, "busy", busy, 1'b0);
        if (al !== 1'b0)
            note_mismatch(2, "al", al, 1'b0);

        ext_sda_low = 1'b1;
        repeat (12) @(posedge clk);
        @(negedge clk);
        if (busy !== 1'b1)
            note_mismatch(1, "busy", busy, 1'b1);

        ext_sda_low = 1'b0;
        repeat (12) @(posedge clk);
        @(negedge clk);
        if (busy !== 1'b0)
            note_mismatch(1, "busy", busy, 1'b0);
        scenario_end("filtered_glitch_and_stable_edges");

        #20;

        $display("Mismatches: %0d in %0d samples", mismatch_count, sample_count);
        $display("Hint: Output 'cmd_ack' has %0d mismatches. First mismatch occurred at time %0t.",
                 cmd_ack_mismatches, cmd_ack_first_time);
        $display("Hint: Output 'busy' has %0d mismatches. First mismatch occurred at time %0t.",
                 busy_mismatches, busy_first_time);
        $display("Hint: Output 'al' has %0d mismatches. First mismatch occurred at time %0t.",
                 al_mismatches, al_first_time);
        $display("Hint: Output 'dout' has %0d mismatches. First mismatch occurred at time %0t.",
                 dout_mismatches, dout_first_time);
        $display("Hint: Output 'scl_o' has %0d mismatches. First mismatch occurred at time %0t.",
                 scl_o_mismatches, scl_o_first_time);
        $display("Hint: Output 'scl_oen' has %0d mismatches. First mismatch occurred at time %0t.",
                 scl_oen_mismatches, scl_oen_first_time);
        $display("Hint: Output 'sda_o' has %0d mismatches. First mismatch occurred at time %0t.",
                 sda_o_mismatches, sda_o_first_time);
        $display("Hint: Output 'sda_oen' has %0d mismatches. First mismatch occurred at time %0t.",
                 sda_oen_mismatches, sda_oen_first_time);

        if (mismatch_count == 0)
            $display("SIMULATION PASSED");
        else
            $display("SIMULATION FAILED - %0d MISMATCHES DETECTED, FIRST AT TIME %0t",
                     mismatch_count, first_mismatch_time);

        $finish;
    end

endmodule