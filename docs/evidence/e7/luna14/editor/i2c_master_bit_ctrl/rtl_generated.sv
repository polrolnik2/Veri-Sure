module i2c_master_bit_ctrl (
    input             clk,
    input             rst,
    input             nReset,
    input             ena,
    input      [15:0] clk_cnt,
    input      [ 3:0] cmd,
    input             din,
    input             scl_i,
    input             sda_i,

    output reg        cmd_ack,
    output reg        busy,
    output reg        al,
    output reg        dout,
    output            scl_o,
    output reg        scl_oen,
    output            sda_o,
    output reg        sda_oen,

    output            cscl,
    output            csda,
    output      [2:0] fscl,
    output      [2:0] fsda,
    output            sscl,
    output            ssda,
    output            dscl,
    output            dsda,
    output            filter_cnt_expired,
    output            filter_cnt_nonzero,
    output            clk_en,
    output            cnt_zero,
    output            slave_wait,
    output            scl_sync,
    output            sta_condition,
    output            sto_condition,
    output            sda_chk,
    output            idle,
    output            fsm_active,
    output            in_start_sequence,
    output            in_stop_sequence,
    output            in_read_sequence,
    output            in_write_sequence,
    output            write_high_phase
);

    localparam [3:0] CMD_START = 4'h1;
    localparam [3:0] CMD_STOP  = 4'h2;
    localparam [3:0] CMD_WRITE = 4'h4;
    localparam [3:0] CMD_READ  = 4'h8;

    localparam [4:0] ST_IDLE   = 5'd0,
                     ST_START_A = 5'd1,
                     ST_START_B = 5'd2,
                     ST_START_C = 5'd3,
                     ST_START_D = 5'd4,
                     ST_STOP_A  = 5'd5,
                     ST_STOP_B  = 5'd6,
                     ST_STOP_C  = 5'd7,
                     ST_STOP_D  = 5'd8,
                     ST_READ_A  = 5'd9,
                     ST_READ_B  = 5'd10,
                     ST_READ_C  = 5'd11,
                     ST_READ_D  = 5'd12,
                     ST_WRITE_A = 5'd13,
                     ST_WRITE_B = 5'd14,
                     ST_WRITE_C = 5'd15,
                     ST_WRITE_D = 5'd16;

    reg [4:0] state_r;
    reg [3:0] cmd_r;

    reg [15:0] cnt_r;
    reg        clk_en_r;
    reg [13:0] filter_cnt_r;

    reg [1:0] cSCL_r;
    reg [1:0] cSDA_r;
    reg [2:0] fSCL_r;
    reg [2:0] fSDA_r;
    reg        dSCL_r;
    reg        dSDA_r;
    reg        sda_chk_r;

    wire sSCL_val;
    wire sSDA_val;
    wire slave_wait_cond;
    wire scl_sync_cond;
    wire sta_condition_cond;
    wire sto_condition_cond;
    wire active_cond;
    wire unexpected_stop_cond;
    wire arbitration_loss_cond;
    wire abort_cond;

    assign sSCL_val = (fSCL_r[2] & fSCL_r[1]) |
                      (fSCL_r[2] & fSCL_r[0]) |
                      (fSCL_r[1] & fSCL_r[0]);
    assign sSDA_val = (fSDA_r[2] & fSDA_r[1]) |
                      (fSDA_r[2] & fSDA_r[0]) |
                      (fSDA_r[1] & fSDA_r[0]);

    assign slave_wait_cond = scl_oen && !sSCL_val;
    assign scl_sync_cond = dSCL_r && !sSCL_val && scl_oen;
    assign sta_condition_cond = !sSDA_val && dSDA_r && sSCL_val;
    assign sto_condition_cond = sSDA_val && !dSDA_r && sSCL_val;
    assign active_cond = (state_r != ST_IDLE);
    assign unexpected_stop_cond = active_cond &&
                                  (cmd_r != CMD_STOP) &&
                                  sto_condition_cond;
    assign arbitration_loss_cond = sda_chk_r && !sSDA_val;
    assign abort_cond = al || arbitration_loss_cond || unexpected_stop_cond;

    assign scl_o = 1'b0;
    assign sda_o = 1'b0;

    assign cscl = cSCL_r[1];
    assign csda = cSDA_r[1];
    assign fscl = fSCL_r;
    assign fsda = fSDA_r;
    assign sscl = sSCL_val;
    assign ssda = sSDA_val;
    assign dscl = dSCL_r;
    assign dsda = dSDA_r;
    assign filter_cnt_expired = (filter_cnt_r == 14'd0);
    assign filter_cnt_nonzero = (filter_cnt_r != 14'd0);
    assign clk_en = clk_en_r;
    assign cnt_zero = (cnt_r == 16'd0);
    assign slave_wait = slave_wait_cond;
    assign scl_sync = scl_sync_cond;
    assign sta_condition = sta_condition_cond;
    assign sto_condition = sto_condition_cond;
    assign sda_chk = sda_chk_r;

    assign idle = (state_r == ST_IDLE);
    assign fsm_active = active_cond;
    assign in_start_sequence = (state_r == ST_START_A) ||
                               (state_r == ST_START_B) ||
                               (state_r == ST_START_C) ||
                               (state_r == ST_START_D);
    assign in_stop_sequence = (state_r == ST_STOP_A) ||
                              (state_r == ST_STOP_B) ||
                              (state_r == ST_STOP_C) ||
                              (state_r == ST_STOP_D);
    assign in_read_sequence = (state_r == ST_READ_A) ||
                              (state_r == ST_READ_B) ||
                              (state_r == ST_READ_C) ||
                              (state_r == ST_READ_D);
    assign in_write_sequence = (state_r == ST_WRITE_A) ||
                               (state_r == ST_WRITE_B) ||
                               (state_r == ST_WRITE_C) ||
                               (state_r == ST_WRITE_D);
    assign write_high_phase = (state_r == ST_WRITE_C);

    always @(posedge clk or negedge nReset) begin
        if (!nReset) begin
            cnt_r    <= 16'd0;
            clk_en_r <= 1'b1;
        end else if (rst) begin
            cnt_r    <= 16'd0;
            clk_en_r <= 1'b1;
        end else if (!ena) begin
            cnt_r    <= clk_cnt;
            clk_en_r <= 1'b1;
        end else if (scl_sync_cond) begin
            cnt_r    <= clk_cnt;
            clk_en_r <= 1'b1;
        end else if (slave_wait_cond) begin
            cnt_r    <= cnt_r;
            clk_en_r <= 1'b0;
        end else if (cnt_r == 16'd0) begin
            cnt_r    <= clk_cnt;
            clk_en_r <= 1'b1;
        end else begin
            cnt_r    <= cnt_r - 16'd1;
            clk_en_r <= 1'b0;
        end
    end

    always @(posedge clk or negedge nReset) begin
        if (!nReset) begin
            filter_cnt_r <= 14'd0;
        end else if (rst) begin
            filter_cnt_r <= 14'd0;
        end else if (!ena) begin
            filter_cnt_r <= 14'd0;
        end else if (filter_cnt_r == 14'd0) begin
            filter_cnt_r <= clk_cnt[15:2];
        end else begin
            filter_cnt_r <= filter_cnt_r - 14'd1;
        end
    end

    always @(posedge clk or negedge nReset) begin
        if (!nReset) begin
            cSCL_r <= 2'b11;
            cSDA_r <= 2'b11;
            fSCL_r <= 3'b111;
            fSDA_r <= 3'b111;
            dSCL_r <= 1'b1;
            dSDA_r <= 1'b1;
            dout   <= 1'b0;
        end else if (rst) begin
            cSCL_r <= 2'b11;
            cSDA_r <= 2'b11;
            fSCL_r <= 3'b111;
            fSDA_r <= 3'b111;
            dSCL_r <= 1'b1;
            dSDA_r <= 1'b1;
            dout   <= 1'b0;
        end else begin
            cSCL_r <= {cSCL_r[0], scl_i};
            cSDA_r <= {cSDA_r[0], sda_i};

            if (ena && (filter_cnt_r == 14'd0)) begin
                fSCL_r <= {fSCL_r[1:0], cSCL_r[1]};
                fSDA_r <= {fSDA_r[1:0], cSDA_r[1]};
            end

            dSCL_r <= sSCL_val;
            dSDA_r <= sSDA_val;

            if (sSCL_val && !dSCL_r)
                dout <= sSDA_val;
        end
    end

    always @(posedge clk or negedge nReset) begin
        if (!nReset) begin
            busy <= 1'b0;
        end else if (rst) begin
            busy <= 1'b0;
        end else if (sta_condition_cond) begin
            busy <= 1'b1;
        end else if (sto_condition_cond) begin
            busy <= 1'b0;
        end
    end

    always @(posedge clk or negedge nReset) begin
        if (!nReset) begin
            al <= 1'b0;
        end else if (rst) begin
            al <= 1'b0;
        end else if (arbitration_loss_cond || unexpected_stop_cond) begin
            al <= 1'b1;
        end else if (sta_condition_cond) begin
            al <= 1'b0;
        end
    end

    always @(posedge clk or negedge nReset) begin
        if (!nReset) begin
            state_r  <= ST_IDLE;
            cmd_r    <= 4'h0;
            cmd_ack  <= 1'b0;
            scl_oen  <= 1'b1;
            sda_oen  <= 1'b1;
            sda_chk_r <= 1'b0;
        end else if (rst) begin
            state_r  <= ST_IDLE;
            cmd_r    <= 4'h0;
            cmd_ack  <= 1'b0;
            scl_oen  <= 1'b1;
            sda_oen  <= 1'b1;
            sda_chk_r <= 1'b0;
        end else begin
            cmd_ack <= 1'b0;

            if (abort_cond) begin
                state_r   <= ST_IDLE;
                scl_oen   <= 1'b1;
                sda_oen   <= 1'b1;
                sda_chk_r <= 1'b0;
            end else if (ena && clk_en_r) begin
                case (state_r)
                    ST_IDLE: begin
                        sda_chk_r <= 1'b0;
                        case (cmd)
                            CMD_START: begin
                                cmd_r   <= CMD_START;
                                state_r <= ST_START_A;
                            end
                            CMD_STOP: begin
                                cmd_r   <= CMD_STOP;
                                state_r <= ST_STOP_A;
                            end
                            CMD_READ: begin
                                cmd_r   <= CMD_READ;
                                state_r <= ST_READ_A;
                            end
                            CMD_WRITE: begin
                                cmd_r   <= CMD_WRITE;
                                state_r <= ST_WRITE_A;
                            end
                            default: state_r <= ST_IDLE;
                        endcase
                    end

                    ST_START_A: begin
                        scl_oen <= 1'b1;
                        sda_oen <= 1'b1;
                        state_r <= ST_START_B;
                    end
                    ST_START_B: begin
                        scl_oen <= 1'b1;
                        sda_oen <= 1'b1;
                        state_r <= ST_START_C;
                    end
                    ST_START_C: begin
                        scl_oen <= 1'b1;
                        sda_oen <= 1'b0;
                        state_r <= ST_START_D;
                    end
                    ST_START_D: begin
                        scl_oen <= 1'b0;
                        sda_oen <= 1'b0;
                        cmd_ack <= 1'b1;
                        state_r <= ST_IDLE;
                    end

                    ST_STOP_A: begin
                        scl_oen <= 1'b0;
                        sda_oen <= 1'b0;
                        state_r <= ST_STOP_B;
                    end
                    ST_STOP_B: begin
                        scl_oen <= 1'b1;
                        sda_oen <= 1'b0;
                        state_r <= ST_STOP_C;
                    end
                    ST_STOP_C: begin
                        scl_oen <= 1'b1;
                        sda_oen <= 1'b1;
                        state_r <= ST_STOP_D;
                    end
                    ST_STOP_D: begin
                        scl_oen <= 1'b1;
                        sda_oen <= 1'b1;
                        cmd_ack <= 1'b1;
                        state_r <= ST_IDLE;
                    end

                    ST_READ_A: begin
                        scl_oen   <= 1'b0;
                        sda_oen   <= 1'b1;
                        sda_chk_r <= 1'b0;
                        state_r   <= ST_READ_B;
                    end
                    ST_READ_B: begin
                        scl_oen <= 1'b1;
                        sda_oen <= 1'b1;
                        state_r <= ST_READ_C;
                    end
                    ST_READ_C: begin
                        scl_oen <= 1'b0;
                        sda_oen <= 1'b1;
                        state_r <= ST_READ_D;
                    end
                    ST_READ_D: begin
                        cmd_ack <= 1'b1;
                        state_r <= ST_IDLE;
                    end

                    ST_WRITE_A: begin
                        scl_oen   <= 1'b0;
                        sda_oen   <= din;
                        sda_chk_r <= 1'b0;
                        state_r   <= ST_WRITE_B;
                    end
                    ST_WRITE_B: begin
                        scl_oen   <= 1'b1;
                        sda_oen   <= din;
                        sda_chk_r <= 1'b1;
                        state_r   <= ST_WRITE_C;
                    end
                    ST_WRITE_C: begin
                        scl_oen   <= 1'b0;
                        sda_oen   <= din;
                        sda_chk_r <= 1'b0;
                        state_r   <= ST_WRITE_D;
                    end
                    ST_WRITE_D: begin
                        cmd_ack <= 1'b1;
                        state_r <= ST_IDLE;
                    end

                    default: begin
                        state_r   <= ST_IDLE;
                        scl_oen   <= 1'b1;
                        sda_oen   <= 1'b1;
                        sda_chk_r <= 1'b0;
                    end
                endcase
            end
        end
    end

endmodule