module or1200_ctrl (
    input  logic        clk,
    input  logic        rst,
    input  logic        id_freeze,
    input  logic        ex_freeze,
    input  logic        wb_freeze,
    input  logic        flushpipe,
    input  logic [31:0] if_insn,
    output logic [31:0] ex_insn,
    output logic [2:0]  branch_op,
    input  logic        branch_taken,
    output logic [4:0]  rf_addra,
    output logic [4:0]  rf_addrb,
    output logic        rf_rda,
    output logic        rf_rdb,
    output logic [3:0]  alu_op,
    output logic [1:0]  mac_op,
    output logic [1:0]  shrot_op,
    output logic [3:0]  comp_op,
    output logic [4:0]  rf_addrw,
    output logic [2:0]  rfwb_op,
    output logic [31:0] wb_insn,
    output logic [31:0] simm,
    output logic [29:0] branch_addrofs,
    output logic [31:0] lsu_addrofs,
    output logic [1:0]  sel_a,
    output logic [1:0]  sel_b,
    output logic [3:0]  lsu_op,
    output logic [4:0]  cust5_op,
    output logic [5:0]  cust5_limm,
    output logic [1:0]  multicycle,
    output logic [15:0] spr_addrimm,
    input  logic        wbforw_valid,
    input  logic        du_hwbkpt,
    output logic        sig_syscall,
    output logic        sig_trap,
    output logic        force_dslot_fetch,
    output logic        no_more_dslot,
    output logic        ex_void,
    output logic        id_macrc_op,
    output logic        ex_macrc_op,
    output logic        rfe,
    output logic        except_illegal
);

    localparam logic [31:0] VOID_WORD = 32'h0001_0000;

    localparam logic [5:0] OP_J      = 6'h01;
    localparam logic [5:0] OP_JAL    = 6'h03;
    localparam logic [5:0] OP_BNF    = 6'h04;
    localparam logic [5:0] OP_BF     = 6'h05;
    localparam logic [5:0] OP_SYS    = 6'h08;
    localparam logic [5:0] OP_TRAP   = 6'h09;
    localparam logic [5:0] OP_JR     = 6'h11;
    localparam logic [5:0] OP_JALR   = 6'h12;
    localparam logic [5:0] OP_RFE    = 6'h13;
    localparam logic [5:0] OP_ADDI   = 6'h17;
    localparam logic [5:0] OP_ADDIC  = 6'h18;
    localparam logic [5:0] OP_ANDI   = 6'h19;
    localparam logic [5:0] OP_ORI    = 6'h1a;
    localparam logic [5:0] OP_XORI   = 6'h1b;
    localparam logic [5:0] OP_SFXXI  = 6'h1f;
    localparam logic [5:0] OP_LWZ    = 6'h21;
    localparam logic [5:0] OP_LBZ    = 6'h23;
    localparam logic [5:0] OP_LBS    = 6'h24;
    localparam logic [5:0] OP_LHZ    = 6'h25;
    localparam logic [5:0] OP_LHS    = 6'h26;
    localparam logic [5:0] OP_MFSPR  = 6'h2d;
    localparam logic [5:0] OP_MULI   = 6'h2e;
    localparam logic [5:0] OP_MACI   = 6'h2f;
    localparam logic [5:0] OP_MTSPR  = 6'h31;
    localparam logic [5:0] OP_SW     = 6'h35;
    localparam logic [5:0] OP_SH     = 6'h36;
    localparam logic [5:0] OP_SB     = 6'h37;
    localparam logic [5:0] OP_ALU    = 6'h38;
    localparam logic [5:0] OP_SFXX   = 6'h39;

    localparam logic [2:0] BR_NONE = 3'd0;
    localparam logic [2:0] BR_J    = 3'd1;
    localparam logic [2:0] BR_JAL  = 3'd2;
    localparam logic [2:0] BR_JR   = 3'd3;
    localparam logic [2:0] BR_JALR = 3'd4;
    localparam logic [2:0] BR_BF   = 3'd5;
    localparam logic [2:0] BR_BNF  = 3'd6;
    localparam logic [2:0] BR_RFE  = 3'd7;

    localparam logic [3:0] ALU_ADD = 4'd0;
    localparam logic [3:0] ALU_SUB = 4'd1;
    localparam logic [3:0] ALU_AND = 4'd2;
    localparam logic [3:0] ALU_OR  = 4'd3;
    localparam logic [3:0] ALU_XOR = 4'd4;
    localparam logic [3:0] ALU_SHROT = 4'd5;
    localparam logic [3:0] ALU_MUL = 4'd8;

    localparam logic [2:0] RFWB_NONE = 3'd0;
    localparam logic [2:0] RFWB_ALU  = 3'd1;
    localparam logic [2:0] RFWB_LSU  = 3'd2;
    localparam logic [2:0] RFWB_SPR  = 3'd3;
    localparam logic [2:0] RFWB_LINK = 3'd4;
    localparam logic [2:0] RFWB_MAC  = 3'd5;

    localparam logic [3:0] LSU_NONE = 4'd0;
    localparam logic [3:0] LSU_LBZ  = 4'd1;
    localparam logic [3:0] LSU_LBS  = 4'd2;
    localparam logic [3:0] LSU_LHZ  = 4'd3;
    localparam logic [3:0] LSU_LHS  = 4'd4;
    localparam logic [3:0] LSU_LWZ  = 4'd5;
    localparam logic [3:0] LSU_SB   = 4'd6;
    localparam logic [3:0] LSU_SH   = 4'd7;
    localparam logic [3:0] LSU_SW   = 4'd8;

    localparam logic [1:0] SEL_RF  = 2'd0;
    localparam logic [1:0] SEL_EX  = 2'd1;
    localparam logic [1:0] SEL_WB  = 2'd2;
    localparam logic [1:0] SEL_IMM = 2'd3;

`ifdef OR1200_MAC
    localparam integer MAC_ENABLED = 1;
`elsif OR1200_MAC_IMPLEMENTED
    localparam integer MAC_ENABLED = 1;
`else
    localparam integer MAC_ENABLED = 0;
`endif

`ifdef OR1200_MULT_IMPLEMENTED
    localparam integer MULT_ENABLED = 1;
`elsif OR1200_MULT
    localparam integer MULT_ENABLED = 1;
`else
    localparam integer MULT_ENABLED = 0;
`endif

`ifdef OR1200_CUSTOM_INSTRUCTIONS
    localparam integer CUSTOM_ENABLED = 1;
`else
    localparam integer CUSTOM_ENABLED = 0;
`endif

    logic [31:0] id_insn;
    logic [4:0]  wb_addrw_reg;
    logic [2:0]  wb_rfwb_reg;

    logic [3:0]  id_alu_op_d;
    logic [1:0]  id_mac_op_d;
    logic [1:0]  id_shrot_op_d;
    logic [3:0]  id_comp_op_d;
    logic [2:0]  id_branch_op_d;
    logic [2:0]  id_rfwb_op_d;
    logic [3:0]  id_lsu_op_d;
    logic [15:0] id_spr_addrimm_d;
    logic [4:0]  id_rf_addrw_d;
    logic [31:0] id_simm_d;
    logic [1:0]  id_multicycle_d;
    logic        id_macrc_op_d;
    logic        id_syscall_d;
    logic        id_trap_d;
    logic        id_illegal_d;
    logic        id_use_a_d;
    logic        id_use_b_d;
    logic        id_imm_sel_d;
    logic        id_void;

    assign rf_addra = if_insn[20:16];
    assign rf_addrb = if_insn[15:11];
    assign rf_rda   = if_insn[31];
    assign rf_rdb   = if_insn[30];

    assign force_dslot_fetch = 1'b0;
    assign ex_void = (ex_insn == VOID_WORD);

    assign branch_addrofs = {{4{ex_insn[25]}}, ex_insn[25:0]};

    assign cust5_op   = ex_insn[25:21];
    assign cust5_limm = ex_insn[10:5];

    always @(*) begin
        if ((ex_insn[31:26] == OP_SW) ||
            (ex_insn[31:26] == OP_SH) ||
            (ex_insn[31:26] == OP_SB))
            lsu_addrofs = {{16{ex_insn[25]}},
                           ex_insn[25:21],
                           ex_insn[10:0]};
        else
            lsu_addrofs = {{16{ex_insn[15]}},
                           ex_insn[15:11],
                           ex_insn[10:0]};
    end

always @(*) begin
        id_alu_op_d      = ALU_ADD;
        id_mac_op_d      = 2'd0;
        id_shrot_op_d    = 2'd0;
        id_comp_op_d     = 4'd0;
        id_branch_op_d   = BR_NONE;
        id_rfwb_op_d     = RFWB_NONE;
        id_lsu_op_d      = LSU_NONE;
        id_spr_addrimm_d = 16'd0;
        id_rf_addrw_d    = id_insn[25:21];
        id_simm_d        = {16'd0, id_insn[15:0]};
        id_multicycle_d  = 2'd1;
        id_macrc_op_d    = 1'b0;
        id_syscall_d     = 1'b0;
        id_trap_d        = 1'b0;
        id_illegal_d     = 1'b0;
        id_use_a_d       = 1'b0;
        id_use_b_d       = 1'b0;
        id_imm_sel_d     = 1'b0;

        id_void = (id_insn == VOID_WORD) || (id_insn == 32'd0) || id_insn[16];

        if (!id_void) begin
            case (id_insn[31:26])
                OP_J: begin
                    id_branch_op_d = BR_J;
                end

                OP_JAL: begin
                    id_branch_op_d = BR_JAL;
                    id_rfwb_op_d   = RFWB_LINK;
                    id_rf_addrw_d  = 5'd9;
                end

                OP_BNF: begin
                    id_branch_op_d = BR_BNF;
                end

                OP_BF: begin
                    id_branch_op_d = BR_BF;
                end

                OP_JR: begin
                    id_branch_op_d = BR_JR;
                    id_use_a_d     = 1'b1;
                end

                OP_JALR: begin
                    id_branch_op_d = BR_JALR;
                    id_use_a_d     = 1'b1;
                    id_rfwb_op_d   = RFWB_LINK;
                    id_rf_addrw_d  = 5'd9;
                end

                OP_RFE: begin
                    id_branch_op_d = BR_RFE;
                end

                OP_SYS: begin
                    id_syscall_d = 1'b1;
                end

                OP_TRAP: begin
                    id_trap_d = 1'b1;
                end

                OP_ADDI,
                OP_ADDIC: begin
                    id_alu_op_d  = ALU_ADD;
                    id_rfwb_op_d = RFWB_ALU;
                    id_use_a_d   = 1'b1;
                    id_imm_sel_d = 1'b1;
                    id_simm_d    = {{16{id_insn[15]}}, id_insn[15:0]};
                end

                OP_ANDI: begin
                    id_alu_op_d  = ALU_AND;
                    id_rfwb_op_d = RFWB_ALU;
                    id_use_a_d   = 1'b1;
                    id_imm_sel_d = 1'b1;
                end

                OP_ORI: begin
                    id_alu_op_d  = ALU_OR;
                    id_rfwb_op_d = RFWB_ALU;
                    id_use_a_d   = 1'b1;
                    id_imm_sel_d = 1'b1;
                end

                OP_XORI: begin
                    id_alu_op_d  = ALU_XOR;
                    id_rfwb_op_d = RFWB_ALU;
                    id_use_a_d   = 1'b1;
                    id_imm_sel_d = 1'b1;
                    id_simm_d    = {{16{id_insn[15]}}, id_insn[15:0]};
                end

                OP_SFXXI: begin
                    id_comp_op_d = id_insn[24:21];
                    id_use_a_d   = 1'b1;
                    id_imm_sel_d = 1'b1;
                    id_simm_d    = {{16{id_insn[15]}}, id_insn[15:0]};
                end

                OP_MULI: begin
                    if (MULT_ENABLED != 0) begin
                        id_alu_op_d  = ALU_MUL;
                        id_rfwb_op_d = RFWB_ALU;
                        id_use_a_d   = 1'b1;
                        id_imm_sel_d = 1'b1;
                        id_simm_d    = {{16{id_insn[15]}}, id_insn[15:0]};
                    end
                    else begin
                        id_illegal_d = 1'b1;
                    end
                end

                OP_MACI: begin
                    if (MAC_ENABLED != 0) begin
                        id_mac_op_d  = 2'd1;
                        id_rfwb_op_d = RFWB_MAC;
                        id_use_a_d   = 1'b1;
                        id_imm_sel_d = 1'b1;
                        id_simm_d    = {{16{id_insn[15]}}, id_insn[15:0]};
                    end
                    else begin
                        id_illegal_d = 1'b1;
                    end
                end

                OP_LBZ: begin
                    id_lsu_op_d  = LSU_LBZ;
                    id_rfwb_op_d = RFWB_LSU;
                    id_use_a_d   = 1'b1;
                    id_imm_sel_d = 1'b1;
                    id_simm_d    = {{16{id_insn[15]}}, id_insn[15:0]};
                end

                OP_LBS: begin
                    id_lsu_op_d  = LSU_LBS;
                    id_rfwb_op_d = RFWB_LSU;
                    id_use_a_d   = 1'b1;
                    id_imm_sel_d = 1'b1;
                    id_simm_d    = {{16{id_insn[15]}}, id_insn[15:0]};
                end

                OP_LHZ: begin
                    id_lsu_op_d  = LSU_LHZ;
                    id_rfwb_op_d = RFWB_LSU;
                    id_use_a_d   = 1'b1;
                    id_imm_sel_d = 1'b1;
                    id_simm_d    = {{16{id_insn[15]}}, id_insn[15:0]};
                end

                OP_LHS: begin
                    id_lsu_op_d  = LSU_LHS;
                    id_rfwb_op_d = RFWB_LSU;
                    id_imm_sel_d = 1'b1;
                    id_simm_d    = {{16{id_insn[15]}}, id_insn[15:0]};
                end

                OP_LWZ: begin
                    id_lsu_op_d  = LSU_LWZ;
                    id_rfwb_op_d = RFWB_LSU;
                    id_use_a_d   = 1'b1;
                    id_imm_sel_d = 1'b1;
                    id_simm_d    = {{16{id_insn[15]}}, id_insn[15:0]};
                end

                OP_SB: begin
                    id_lsu_op_d  = LSU_SB;
                    id_use_a_d   = 1'b1;
                    id_use_b_d   = 1'b1;
                    id_imm_sel_d = 1'b1;
                    id_simm_d    = {{16{id_insn[15]}}, id_insn[15:0]};
                end

                OP_SH: begin
                    id_lsu_op_d  = LSU_SH;
                    id_use_a_d   = 1'b1;
                    id_use_b_d   = 1'b1;
                    id_imm_sel_d = 1'b1;
                    id_simm_d    = {{16{id_insn[15]}}, id_insn[15:0]};
                end

                OP_SW: begin
                    id_lsu_op_d  = LSU_SW;
                    id_use_a_d   = 1'b1;
                    id_use_b_d   = 1'b1;
                    id_imm_sel_d = 1'b1;
                    id_simm_d    = {{16{id_insn[15]}}, id_insn[15:0]};
                end

                OP_MFSPR: begin
                    id_spr_addrimm_d = id_insn[15:0];
                    id_rfwb_op_d     = RFWB_SPR;
                end

                OP_MTSPR: begin
                    id_spr_addrimm_d = {id_insn[25:21], id_insn[10:0]};
                    id_use_a_d       = 1'b1;
                    id_use_b_d       = 1'b1;
                end

                OP_ALU: begin
                    id_use_a_d      = 1'b1;
                    id_use_b_d      = 1'b1;
                    id_rfwb_op_d    = RFWB_ALU;
                    id_shrot_op_d   = id_insn[7:6];
                    id_multicycle_d = id_insn[9:8];

                    case (id_insn[3:0])
                        4'h0: id_alu_op_d = ALU_ADD;
                        4'h2: id_alu_op_d = ALU_SUB;
                        4'h3: id_alu_op_d = ALU_AND;
                        4'h4: id_alu_op_d = ALU_OR;
                        4'h5: id_alu_op_d = ALU_XOR;
                        4'h6,
                        4'h9: begin
                            if (MULT_ENABLED != 0)
                                id_alu_op_d = ALU_MUL;
                            else
                                id_illegal_d = 1'b1;
                        end
                        default: begin
                            id_illegal_d = 1'b1;
                        end
                    endcase

                    if ((MAC_ENABLED != 0) &&
                        (id_insn[3:0] == 4'hb)) begin
                        id_mac_op_d   = 2'd1;
                        id_rfwb_op_d  = RFWB_MAC;
                        id_macrc_op_d = 1'b1;
                    end
                end

                OP_SFXX: begin
                    id_comp_op_d = id_insn[24:21];
                    id_use_a_d   = 1'b1;
                    id_use_b_d   = 1'b1;
                end

                default: begin
                    if (CUSTOM_ENABLED == 0)
                        id_illegal_d = 1'b1;
                end
            endcase
        end

        if (id_void) begin
            id_alu_op_d      = ALU_ADD;
            id_mac_op_d      = 2'd0;
            id_shrot_op_d    = 2'd0;
            id_comp_op_d     = 4'd0;
            id_branch_op_d   = BR_NONE;
            id_rfwb_op_d     = RFWB_NONE;
            id_lsu_op_d      = LSU_NONE;
            id_spr_addrimm_d = 16'd0;
            id_rf_addrw_d    = 5'd0;
            id_simm_d        = 32'd0;
            id_multicycle_d  = 2'd1;
            id_macrc_op_d    = 1'b0;
            id_syscall_d     = 1'b0;
            id_trap_d        = 1'b0;
            id_illegal_d     = 1'b0;
        end
    end

    always @(*) begin
        simm        = id_simm_d;
        multicycle  = id_multicycle_d;
        id_macrc_op = id_macrc_op_d;

        sel_a = SEL_RF;
        sel_b = SEL_RF;

        if (id_use_a_d && (id_insn[20:16] != 5'd0)) begin
            if ((rf_addrw != 5'd0) &&
                (rfwb_op != RFWB_NONE) &&
                (rf_addrw == id_insn[20:16]))
                sel_a = SEL_EX;
            else if (wbforw_valid &&
                     (wb_rfwb_reg != RFWB_NONE) &&
                     (wb_addrw_reg != 5'd0) &&
                     (wb_addrw_reg == id_insn[20:16]))
                sel_a = SEL_WB;
        end

        if (id_imm_sel_d) begin
            sel_b = SEL_IMM;
        end
        else if (id_use_b_d && (id_insn[15:11] != 5'd0)) begin
            if ((rf_addrw != 5'd0) &&
                (rfwb_op != RFWB_NONE) &&
                (rf_addrw == id_insn[15:11]))
                sel_b = SEL_EX;
            else if (wbforw_valid &&
                     (wb_rfwb_reg != RFWB_NONE) &&
                     (wb_addrw_reg != 5'd0) &&
                     (wb_addrw_reg == id_insn[15:11]))
                sel_b = SEL_WB;
        end
    end

    always @(*) begin
        rfe = (id_branch_op_d == BR_RFE) ||
              (branch_op == BR_RFE);

        no_more_dslot =
            ((branch_op != BR_NONE) &&
             !id_void &&
             branch_taken) ||
            (branch_op == BR_RFE);
    end

    always @(posedge clk or posedge rst) begin
        if (rst) begin
            id_insn        <= VOID_WORD;
            ex_insn        <= VOID_WORD;
            wb_insn        <= VOID_WORD;

            branch_op      <= BR_NONE;
            alu_op         <= ALU_ADD;
            mac_op         <= 2'd0;
            shrot_op       <= 2'd0;
            comp_op        <= 4'd0;
            rf_addrw       <= 5'd0;
            rfwb_op        <= RFWB_NONE;
            lsu_op         <= LSU_NONE;
            spr_addrimm    <= 16'd0;
            sig_syscall    <= 1'b0;
            sig_trap       <= 1'b0;
            ex_macrc_op    <= 1'b0;
            except_illegal <= 1'b0;

            wb_addrw_reg   <= 5'd0;
            wb_rfwb_reg    <= RFWB_NONE;
        end
        else if (flushpipe) begin
            id_insn        <= VOID_WORD;
            ex_insn        <= VOID_WORD;
            wb_insn        <= VOID_WORD;

            branch_op      <= BR_NONE;
            alu_op         <= ALU_ADD;
            mac_op         <= 2'd0;
            shrot_op       <= 2'd0;
            comp_op        <= 4'd0;
            rfwb_op        <= RFWB_NONE;
            lsu_op         <= LSU_NONE;
            spr_addrimm    <= 16'd0;
            sig_syscall    <= 1'b0;
            sig_trap       <= 1'b0;
            ex_macrc_op    <= 1'b0;
            except_illegal <= 1'b0;
        end
        else begin
            if (!wb_freeze) begin
                wb_insn      <= ex_insn;
                wb_addrw_reg <= rf_addrw;
                wb_rfwb_reg  <= rfwb_op;
            end

            if (!ex_freeze) begin
                if (id_freeze) begin
                    ex_insn        <= VOID_WORD;
                    branch_op      <= BR_NONE;
                    alu_op         <= ALU_ADD;
                    mac_op         <= 2'd0;
                    shrot_op       <= 2'd0;
                    comp_op        <= 4'd0;
                    rf_addrw       <= 5'd0;
                    rfwb_op         <= RFWB_NONE;
                    lsu_op         <= LSU_NONE;
                    spr_addrimm    <= 16'd0;
                    sig_syscall    <= 1'b0;
                    sig_trap       <= 1'b0;
                    ex_macrc_op    <= 1'b0;
                    except_illegal <= 1'b0;
                end
                else begin
                    ex_insn        <= id_insn;
                    branch_op      <= id_branch_op_d;
                    alu_op         <= id_alu_op_d;
                    mac_op         <= id_mac_op_d;
                    shrot_op       <= id_shrot_op_d;
                    comp_op        <= id_comp_op_d;
                    rf_addrw       <= id_rf_addrw_d;
                    rfwb_op        <= id_rfwb_op_d;
                    lsu_op         <= id_lsu_op_d;
                    spr_addrimm    <= id_spr_addrimm_d;
                    sig_syscall    <= id_syscall_d;
                    sig_trap       <= id_trap_d | du_hwbkpt;
                    ex_macrc_op    <= id_macrc_op_d;
                    except_illegal <= id_illegal_d;
                end
            end

            if (!id_freeze)
                id_insn <= if_insn;
        end
    end

endmodule