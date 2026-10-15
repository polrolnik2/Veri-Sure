module or1200_ctrl_tb;

    localparam logic [31:0] VOID_WORD = 32'h0001_0000;
    localparam integer MAX_QUEUE_SIZE = 10;
    localparam integer OUTPUT_COUNT = 32;

    logic        clk;
    logic        rst;
    logic        id_freeze;
    logic        ex_freeze;
    logic        wb_freeze;
    logic        flushpipe;
    logic [31:0] if_insn;
    logic [31:0] ex_insn;
    logic [2:0]  branch_op;
    logic        branch_taken;
    logic [4:0]  rf_addra;
    logic [4:0]  rf_addrb;
    logic        rf_rda;
    logic        rf_rdb;
    logic [3:0]  alu_op;
    logic [1:0]  mac_op;
    logic [1:0]  shrot_op;
    logic [3:0]  comp_op;
    logic [4:0]  rf_addrw;
    logic [2:0]  rfwb_op;
    logic [31:0] wb_insn;
    logic [31:0] simm;
    logic [29:0] branch_addrofs;
    logic [31:0] lsu_addrofs;
    logic [1:0]  sel_a;
    logic [1:0]  sel_b;
    logic [3:0]  lsu_op;
    logic [4:0]  cust5_op;
    logic [5:0]  cust5_limm;
    logic [1:0]  multicycle;
    logic [15:0] spr_addrimm;
    logic        wbforw_valid;
    logic        du_hwbkpt;
    logic        sig_syscall;
    logic        sig_trap;
    logic        force_dslot_fetch;
    logic        no_more_dslot;
    logic        ex_void;
    logic        id_macrc_op;
    logic        ex_macrc_op;
    logic        rfe;
    logic        except_illegal;

    logic [31:0] model_id_insn;
    logic [31:0] model_ex_insn;
    logic [31:0] model_wb_insn;
    logic        model_du_trap;

    integer mismatch_count;
    integer sample_count;
    time first_mismatch_time;

    integer output_mismatch_count [0:OUTPUT_COUNT-1];
    time output_first_time [0:OUTPUT_COUNT-1];

    string output_names [0:OUTPUT_COUNT-1];
    string scenario_name;
    integer scenario_mismatch_count;
    time scenario_start_time;
    time scenario_end_time;
    time scenario_first_time;
    logic tb_started;
    logic first_context_done;

    logic [31:0] if_queue [$];
    logic [31:0] got_ex_queue [$];
    logic [31:0] exp_ex_queue [$];
    logic [31:0] got_wb_queue [$];
    logic [31:0] exp_wb_queue [$];
    logic        rst_queue [$];

    integer output_index;

    or1200_ctrl dut (
        .clk              (clk),
        .rst              (rst),
        .id_freeze        (id_freeze),
        .ex_freeze        (ex_freeze),
        .wb_freeze        (wb_freeze),
        .flushpipe        (flushpipe),
        .if_insn          (if_insn),
        .ex_insn          (ex_insn),
        .branch_op        (branch_op),
        .branch_taken     (branch_taken),
        .rf_addra         (rf_addra),
        .rf_addrb         (rf_addrb),
        .rf_rda           (rf_rda),
        .rf_rdb           (rf_rdb),
        .alu_op           (alu_op),
        .mac_op           (mac_op),
        .shrot_op         (shrot_op),
        .comp_op          (comp_op),
        .rf_addrw         (rf_addrw),
        .rfwb_op          (rfwb_op),
        .wb_insn          (wb_insn),
        .simm             (simm),
        .branch_addrofs   (branch_addrofs),
        .lsu_addrofs      (lsu_addrofs),
        .sel_a            (sel_a),
        .sel_b            (sel_b),
        .lsu_op           (lsu_op),
        .cust5_op         (cust5_op),
        .cust5_limm       (cust5_limm),
        .multicycle       (multicycle),
        .spr_addrimm      (spr_addrimm),
        .wbforw_valid     (wbforw_valid),
        .du_hwbkpt        (du_hwbkpt),
        .sig_syscall      (sig_syscall),
        .sig_trap         (sig_trap),
        .force_dslot_fetch(force_dslot_fetch),
        .no_more_dslot   (no_more_dslot),
        .ex_void          (ex_void),
        .id_macrc_op      (id_macrc_op),
        .ex_macrc_op      (ex_macrc_op),
        .rfe              (rfe),
        .except_illegal   (except_illegal)
    );

    initial begin
        clk = 1'b0;
        forever #5 clk = ~clk;
    end

    always @(posedge clk or posedge rst) begin
        if (rst) begin
            model_id_insn = VOID_WORD;
            model_ex_insn = VOID_WORD;
            model_wb_insn = VOID_WORD;
            model_du_trap = 1'b0;
        end
        else if (flushpipe) begin
            model_id_insn = VOID_WORD;
            model_ex_insn = VOID_WORD;
            model_wb_insn = VOID_WORD;
            model_du_trap = 1'b0;
        end
        else begin
            if (!wb_freeze)
                model_wb_insn = model_ex_insn;

            if (!ex_freeze) begin
                if (id_freeze) begin
                    model_ex_insn = VOID_WORD;
                    model_du_trap = 1'b0;
                end
                else begin
                    model_ex_insn = model_id_insn;
                    model_du_trap = du_hwbkpt;
                end
            end

            if (!id_freeze)
                model_id_insn = if_insn;
        end
    end

    task automatic show_window;
        integer k;
        begin
            $display("FIRST MISMATCH CONTEXT at time %0t", $time);
            $display("Recent samples:");
            for (k = 0; k < if_queue.size(); k = k + 1) begin
                $display("  window[%0d] rst=%b if_insn=%h got_ex=%h exp_ex=%h got_wb=%h exp_wb=%h",
                         k, rst_queue[k], if_queue[k],
                         got_ex_queue[k], exp_ex_queue[k],
                         got_wb_queue[k], exp_wb_queue[k]);
            end
        end
    endtask

    task automatic compare_value(
        input integer idx,
        input logic [63:0] got_value,
        input logic [63:0] expected_value
    );
        begin
            if (got_value !== expected_value) begin
                if (mismatch_count == 0)
                    first_mismatch_time = $time;
                if (scenario_mismatch_count == 0)
                    scenario_first_time = $time;
                if (output_mismatch_count[idx] == 0)
                    output_first_time[idx] = $time;

                mismatch_count = mismatch_count + 1;
                scenario_mismatch_count = scenario_mismatch_count + 1;
                output_mismatch_count[idx] = output_mismatch_count[idx] + 1;

                $display("MISMATCH %s at time %0t: if_insn=%h rst=%b id_freeze=%b ex_freeze=%b wb_freeze=%b flushpipe=%b | got=%h (%b) exp=%h (%b)",
                         output_names[idx], $time, if_insn, rst,
                         id_freeze, ex_freeze, wb_freeze, flushpipe,
                         got_value, got_value, expected_value, expected_value);

                if (!first_context_done) begin
                    show_window();
                    first_context_done = 1'b1;
                end
            end
        end
    endtask

    task automatic check_cycle;
        logic [29:0] expected_branch_offset;
        begin
            sample_count = sample_count + 1;

            if (if_queue.size() >= MAX_QUEUE_SIZE) begin
                if_queue.delete(0);
                got_ex_queue.delete(0);
                exp_ex_queue.delete(0);
                got_wb_queue.delete(0);
                exp_wb_queue.delete(0);
                rst_queue.delete(0);
            end

            if_queue.push_back(if_insn);
            got_ex_queue.push_back(ex_insn);
            exp_ex_queue.push_back(model_ex_insn);
            got_wb_queue.push_back(wb_insn);
            exp_wb_queue.push_back(model_wb_insn);
            rst_queue.push_back(rst);

            expected_branch_offset =
                {{4{model_ex_insn[25]}}, model_ex_insn[25:0]};

            compare_value(0,  ex_insn,           model_ex_insn);
            compare_value(1,  branch_op,         64'd0);
            compare_value(2,  rf_addra,           if_insn[20:16]);
            compare_value(3,  rf_addrb,           if_insn[15:11]);
            compare_value(4,  rf_rda,             if_insn[31]);
            compare_value(5,  rf_rdb,             if_insn[30]);
            compare_value(12, wb_insn,            model_wb_insn);
            compare_value(14, branch_addrofs,     expected_branch_offset);
            compare_value(24, sig_trap,           model_du_trap);
            compare_value(25, force_dslot_fetch,  64'd0);
            compare_value(27, ex_void,             (model_ex_insn == VOID_WORD));

            if ((model_id_insn == VOID_WORD) || (model_id_insn == 32'h0000_0000)) begin
                compare_value(13, simm,         64'd0);
                compare_value(28, id_macrc_op,  64'd0);
                compare_value(30, rfe,           64'd0);
                compare_value(26, no_more_dslot, 64'd0);
            end

            if ((model_ex_insn == VOID_WORD) || (model_ex_insn == 32'h0000_0000)) begin
                compare_value(15, lsu_addrofs, 64'd0);
                compare_value(29, ex_macrc_op, 64'd0);
                compare_value(30, rfe,          64'd0);
                compare_value(31, except_illegal, 64'd0);
            end

            if (rst || flushpipe || (model_ex_insn == VOID_WORD)) begin
                compare_value(1,  branch_op,       64'd0);
                compare_value(6,  alu_op,          64'd0);
                compare_value(7,  mac_op,          64'd0);
                compare_value(8,  shrot_op,        64'd0);
                compare_value(9,  comp_op,         64'd0);
                compare_value(11, rfwb_op,         64'd0);
                compare_value(18, lsu_op,          64'd0);
                compare_value(22, spr_addrimm,     64'd0);
                compare_value(23, sig_syscall,     64'd0);
                compare_value(24, sig_trap,        64'd0);
                compare_value(29, ex_macrc_op,     64'd0);
                compare_value(31, except_illegal,  64'd0);
            end

            if (rst) begin
                compare_value(10, rf_addrw, 64'd0);
            end
        end
    endtask

    task automatic begin_scenario(input string scen_label);
        begin
            scenario_name = scen_label;
            scenario_start_time = $time;
            scenario_mismatch_count = 0;
            scenario_first_time = 0;
            $display("[TEST %s] START at time %0t", scenario_name, scenario_start_time);
        end
    endtask

    task automatic end_scenario;
        begin
            scenario_end_time = $time;
            if (scenario_mismatch_count == 0) begin
                $display("[TEST %s] PASS (window %0t..%0t)",
                         scenario_name, scenario_start_time, scenario_end_time);
            end
            else begin
                $display("[TEST %s] FAIL (%0d mismatches, first at time %0t, window %0t..%0t)",
                         scenario_name, scenario_mismatch_count,
                         scenario_first_time, scenario_start_time,
                         scenario_end_time);
            end
        end
    endtask

    task automatic drive_word(input logic [31:0] next_word);
        begin
            @(negedge clk);
            #1;
            if_insn = next_word;
        end
    endtask

    task automatic reset_between;
        begin
            rst = 1'b1;
            #2;
            @(negedge clk);
            #1;
            rst = 1'b0;
            id_freeze = 1'b0;
            ex_freeze = 1'b0;
            wb_freeze = 1'b0;
            flushpipe = 1'b0;
            branch_taken = 1'b0;
            wbforw_valid = 1'b0;
            du_hwbkpt = 1'b0;
            if_insn = 32'h0000_0000;
        end
    endtask

    always @(negedge clk) begin
        if (tb_started)
            check_cycle();
    end

    initial begin
        output_names[0]  = "ex_insn";
        output_names[1]  = "branch_op";
        output_names[2]  = "rf_addra";
        output_names[3]  = "rf_addrb";
        output_names[4]  = "rf_rda";
        output_names[5]  = "rf_rdb";
        output_names[6]  = "alu_op";
        output_names[7]  = "mac_op";
        output_names[8]  = "shrot_op";
        output_names[9]  = "comp_op";
        output_names[10] = "rf_addrw";
        output_names[11] = "rfwb_op";
        output_names[12] = "wb_insn";
        output_names[13] = "simm";
        output_names[14] = "branch_addrofs";
        output_names[15] = "lsu_addrofs";
        output_names[16] = "sel_a";
        output_names[17] = "sel_b";
        output_names[18] = "lsu_op";
        output_names[19] = "cust5_op";
        output_names[20] = "cust5_limm";
        output_names[21] = "multicycle";
        output_names[22] = "spr_addrimm";
        output_names[23] = "sig_syscall";
        output_names[24] = "sig_trap";
        output_names[25] = "force_dslot_fetch";
        output_names[26] = "no_more_dslot";
        output_names[27] = "ex_void";
        output_names[28] = "id_macrc_op";
        output_names[29] = "ex_macrc_op";
        output_names[30] = "rfe";
        output_names[31] = "except_illegal";

        mismatch_count = 0;
        sample_count = 0;
        first_mismatch_time = 0;
        first_context_done = 1'b0;
        tb_started = 1'b0;
        scenario_name = "none";

        for (output_index = 0; output_index < OUTPUT_COUNT; output_index = output_index + 1) begin
            output_mismatch_count[output_index] = 0;
            output_first_time[output_index] = 0;
        end

        model_id_insn = VOID_WORD;
        model_ex_insn = VOID_WORD;
        model_wb_insn = VOID_WORD;
        model_du_trap = 1'b0;

        rst = 1'b0;
        id_freeze = 1'b0;
        ex_freeze = 1'b0;
        wb_freeze = 1'b0;
        flushpipe = 1'b0;
        if_insn = 32'h0000_0000;
        branch_taken = 1'b0;
        wbforw_valid = 1'b0;
        du_hwbkpt = 1'b0;
        tb_started = 1'b1;

        begin_scenario("reset_async");
        rst = 1'b1;
        #2;
        check_cycle();
        @(negedge clk);
        #1;
        rst = 1'b0;
        @(negedge clk);
        #1;
        end_scenario();

        begin_scenario("direct_register_fields");
        reset_between();
        drive_word(32'h0000_0000);
        repeat (1) @(negedge clk);
        drive_word(32'hffff_ffff);
        repeat (1) @(negedge clk);
        drive_word(32'h8000_0001);
        repeat (1) @(negedge clk);
        drive_word(32'h7fff_fff0);
        repeat (1) @(negedge clk);
        #1;
        end_scenario();

        begin_scenario("pipeline_latency");
        reset_between();
        drive_word(32'ha5a5_5aa5);
        repeat (2) @(negedge clk);
        drive_word(32'h1357_9bdf);
        repeat (2) @(negedge clk);
        drive_word(32'heca8_6420);
        repeat (2) @(negedge clk);
        #1;
        end_scenario();

        begin_scenario("freeze_controls");
        reset_between();
        drive_word(32'h1111_2222);
        repeat (1) @(negedge clk);

        id_freeze = 1'b1;
        drive_word(32'h3333_4444);
        repeat (1) @(negedge clk);
        id_freeze = 1'b0;

        ex_freeze = 1'b1;
        drive_word(32'h5555_6666);
        repeat (1) @(negedge clk);
        ex_freeze = 1'b0;

        wb_freeze = 1'b1;
        drive_word(32'h7777_8888);
        repeat (1) @(negedge clk);
        wb_freeze = 1'b0;

        id_freeze = 1'b1;
        ex_freeze = 1'b1;
        wb_freeze = 1'b1;
        drive_word(32'h9999_aaaa);
        repeat (1) @(negedge clk);
        id_freeze = 1'b0;
        ex_freeze = 1'b0;
        wb_freeze = 1'b0;
        repeat (2) @(negedge clk);
        #1;
        end_scenario();

        begin_scenario("flush_priority");
        reset_between();
        id_freeze = 1'b1;
        ex_freeze = 1'b1;
        wb_freeze = 1'b1;
        flushpipe = 1'b1;
        drive_word(32'hdead_beef);
        repeat (1) @(negedge clk);
        flushpipe = 1'b0;
        id_freeze = 1'b0;
        ex_freeze = 1'b0;
        wb_freeze = 1'b0;
        drive_word(32'h2468_ace0);
        repeat (2) @(negedge clk);
        #1;
        end_scenario();

        begin_scenario("offset_boundaries");
        reset_between();
        drive_word(32'h0000_0000);
        repeat (2) @(negedge clk);
        drive_word(32'h03ff_ffff);
        repeat (2) @(negedge clk);
        drive_word(32'h0200_0000);
        repeat (2) @(negedge clk);
        drive_word(32'h03ff_fc00);
        repeat (2) @(negedge clk);
        drive_word(32'h8200_07ff);
        repeat (2) @(negedge clk);
        #1;
        end_scenario();

        begin_scenario("debug_trap_sampling");
        reset_between();
        du_hwbkpt = 1'b1;
        drive_word(32'h1234_5678);
        repeat (2) @(negedge clk);
        du_hwbkpt = 1'b0;
        drive_word(32'h0000_0000);
        repeat (2) @(negedge clk);
        #1;
        end_scenario();

        $display("Mismatches: %0d in %0d samples", mismatch_count, sample_count);
        for (output_index = 0; output_index < OUTPUT_COUNT; output_index = output_index + 1) begin
            $display("Hint: Output '%s' has %0d mismatches. First mismatch occurred at time %0t.",
                     output_names[output_index],
                     output_mismatch_count[output_index],
                     output_first_time[output_index]);
        end

        if (mismatch_count == 0)
            $display("SIMULATION PASSED");
        else
            $display("SIMULATION FAILED - %0d MISMATCHES DETECTED, FIRST AT TIME %0t",
                     mismatch_count, first_mismatch_time);

        $finish;
    end

    initial begin
        $dumpfile("wave.vcd");
        $dumpvars(0, dut);
        $dumpvars(0, dut);
    end

endmodule