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
    output wire       scl_o,
    output reg        scl_oen,
    output wire       sda_o,
    output reg        sda_oen,

    output wire       idle,
    output wire       fsm_active,
    output wire       in_start_sequence,
    output wire       in_stop_sequence,
    output wire       in_read_sequence,
    output wire       in_write_sequence,
    output wire       write_stable_high_phase,
    output wire       read_sample_window,
    output wire       cscl,
    output wire       csda,
    output wire       filter_cnt_expired,
    output wire [2:0] fscl,
    output wire [2:0] fsda,
    output wire       sscl,
    output wire       ssda,
    output wire       dscl,
    output wire       dsda,
    output wire       sscl_rise,
    output wire       sta_condition,
    output wire       sto_condition,
    output wire       slave_wait,
    output wire       scl_sync,
    output wire       cnt_zero,
    output wire       clk_en,
    output wire       sda_chk
);

    localparam [3:0] I2C_CMD_NOP   = 4'b0000;
    localparam [3:0] I2C_CMD_START = 4'b0001;
    localparam [3:0] I2C_CMD_STOP  = 4'b0010;
    localparam [3:0] I2C_CMD_WRITE = 4'b0100;
    localparam [3:0] I2C_CMD_READ  = 4'b1000;

    localparam [3:0] ST_IDLE    = 4'd0;
    localparam [3:0] ST_START_A = 4'd1;
    localparam [3:0] ST_START_B = 4'd2;
    localparam [3:0] ST_START_C = 4'd3;
    localparam [3:0] ST_START_D = 4'd4;
    localparam [3:0] ST_STOP_A  = 4'd5;
    localparam [3:0] ST_STOP_B  = 4'd6;
    localparam [3:0] ST_STOP_C  = 4'd7;
    localparam [3:0] ST_READ_A  = 4'd8;
    localparam [3:0] ST_READ_B  = 4'd9;
    localparam [3:0] ST_READ_C  = 4'd10;
    localparam [3:0] ST_READ_D  = 4'd11;
    localparam [3:0] ST_WRITE_A = 4'd12;
    localparam [3:0] ST_WRITE_B = 4'd13;
    localparam [3:0] ST_WRITE_C = 4'd14;
    localparam [3:0] ST_WRITE_D = 4'd15;

    reg [3:0]  state_r;
    reg [15:0] cnt_r;
    reg        clk_en_r;
    reg [15:0] filter_cnt_r;
    reg [1:0]  cSCL_pipe_r;
    reg [1:0]  cSDA_pipe_r;
    reg [2:0]  fSCL_r;
    reg [2:0]  fSDA_r;
    reg        dSCL_r;
    reg        dSDA_r;
    reg        sda_chk_r;

    wire filtered_scl;
    wire filtered_sda;
    wire filter_expired_cond;
    wire cnt_zero_cond;
    wire scl_rise_event;
    wire sta_event;
    wire sto_event;
    wire slave_wait_cond;
    wire scl_sync_cond;
    wire state_active;
    wire stop_state;

    assign scl_o = 1'b0;
    assign sda_o = 1'b0;

    assign filtered_scl = (fSCL_r[2] & fSCL_r[1]) |
                          (fSCL_r[2] & fSCL_r[0]) |
                          (fSCL_r[1] & fSCL_r[0]);
    assign filtered_sda = (fSDA_r[2] & fSDA_r[1]) |
                          (fSDA_r[2] & fSDA_r[0]) |
                          (fSDA_r[1] & fSDA_r[0]);

    assign filter_expired_cond = ena && (filter_cnt_r == 16'b0);
    assign cnt_zero_cond       = (cnt_r == 16'b0);
    assign scl_rise_event      = filtered_scl && !dSCL_r;
    assign sta_event           = !filtered_sda && dSDA_r && filtered_scl;
    assign sto_event           = filtered_sda && !dSDA_r && filtered_scl;
    assign slave_wait_cond     = scl_oen && !filtered_scl;
    assign scl_sync_cond       = dSCL_r && !filtered_scl && scl_oen;

    assign state_active = (state_r != ST_IDLE);
    assign stop_state = (state_r == ST_STOP_A) ||
                        (state_r == ST_STOP_B) ||
                        (state_r == ST_STOP_C);

    assign idle                    = (state_r == ST_IDLE);
    assign fsm_active              = state_active;
    assign in_start_sequence       = (state_r == ST_START_A) ||
                                     (state_r == ST_START_B) ||
                                     (state_r == ST_START_C) ||
                                     (state_r == ST_START_D);
    assign in_stop_sequence        = stop_state;
    assign in_read_sequence        = (state_r == ST_READ_A) ||
                                     (state_r == ST_READ_B) ||
                                     (state_r == ST_READ_C) ||
                                     (state_r == ST_READ_D);
    assign in_write_sequence       = (state_r == ST_WRITE_A) ||
                                     (state_r == ST_WRITE_B) ||
                                     (state_r == ST_WRITE_C) ||
                                     (state_r == ST_WRITE_D);
    assign write_stable_high_phase = (state_r == ST_WRITE_B);
    assign read_sample_window      = (state_r == ST_READ_B);
    assign cscl                    = cSCL_pipe_r[1];
    assign csda                    = cSDA_pipe_r[1];
    assign filter_cnt_expired      = filter_expired_cond;
    assign fscl                    = fSCL_r;
    assign fsda                    = fSDA_r;
    assign sscl                    = filtered_scl;
    assign ssda                    = filtered_sda;
    assign dscl                    = dSCL_r;
    assign dsda                    = dSDA_r;
    assign sscl_rise               = scl_rise_event;
    assign sta_condition           = sta_event;
    assign sto_condition           = sto_event;
    assign slave_wait              = slave_wait_cond;
    assign scl_sync                = scl_sync_cond;
    assign cnt_zero                = cnt_zero_cond;
    assign clk_en                  = clk_en_r;
    assign sda_chk                 = sda_chk_r;

    always @(posedge clk or negedge nReset) begin
        if (!nReset) begin
            cSCL_pipe_r <= 2'b11;
            cSDA_pipe_r <= 2'b11;
        end else if (rst) begin
            cSCL_pipe_r <= 2'b11;
            cSDA_pipe_r <= 2'b11;
        end else begin
            cSCL_pipe_r <= {cSCL_pipe_r[0], scl_i};
            cSDA_pipe_r <= {cSDA_pipe_r[0], sda_i};
        end
    end

    always @(posedge clk or negedge nReset) begin
        if (!nReset) begin
            filter_cnt_r <= 16'b0;
        end else if (rst) begin
            filter_cnt_r <= 16'b0;
        end else if (!ena) begin
            filter_cnt_r <= 16'b0;
        end else if (filter_cnt_r == 16'b0) begin
            filter_cnt_r <= clk_cnt >> 2;
        end else begin
            filter_cnt_r <= filter_cnt_r - 1'b1;
        end
    end

    always @(posedge clk or negedge nReset) begin
        if (!nReset) begin
            fSCL_r <= 3'b111;
            fSDA_r <= 3'b111;
        end else if (rst) begin
            fSCL_r <= 3'b111;
            fSDA_r <= 3'b111;
        end else if (filter_expired_cond) begin
            fSCL_r <= {fSCL_r[1:0], cSCL_pipe_r[1]};
            fSDA_r <= {fSDA_r[1:0], cSDA_pipe_r[1]};
        end
    end

    always @(posedge clk or negedge nReset) begin
        if (!nReset) begin
            dSCL_r <= 1'b1;
            dSDA_r <= 1'b1;
        end else if (rst) begin
            dSCL_r <= 1'b1;
            dSDA_r <= 1'b1;
        end else begin
            dSCL_r <= filtered_scl;
            dSDA_r <= filtered_sda;
        end
    end

    always @(posedge clk or negedge nReset) begin
        if (!nReset) begin
            cnt_r    <= 16'b0;
            clk_en_r <= 1'b1;
        end else if (rst) begin
            cnt_r    <= 16'b0;
            clk_en_r <= 1'b1;
        end else if (!ena || scl_sync_cond) begin
            cnt_r    <= clk_cnt;
            clk_en_r <= 1'b1;
        end else if (slave_wait_cond) begin
            cnt_r    <= cnt_r;
            clk_en_r <= 1'b0;
        end else if (cnt_zero_cond) begin
            cnt_r    <= clk_cnt;
            clk_en_r <= 1'b1;
        end else begin
            cnt_r    <= cnt_r - 1'b1;
            clk_en_r <= 1'b0;
        end
    end

    always @(posedge clk or negedge nReset) begin
        if (!nReset) begin
            busy <= 1'b0;
        end else if (rst) begin
            busy <= 1'b0;
        end else if (sta_event) begin
            busy <= 1'b1;
        end else if (sto_event) begin
            busy <= 1'b0;
        end
    end

    always @(posedge clk or negedge nReset) begin
        if (!nReset) begin
            dout <= 1'b0;
        end else if (rst) begin
            dout <= 1'b0;
        end else if (scl_rise_event) begin
            dout <= filtered_sda;
        end
    end

    always @(posedge clk or negedge nReset) begin
        if (!nReset) begin
            al <= 1'b0;
        end else if (rst) begin
            al <= 1'b0;
        end else begin
            al <= (sda_chk_r && !filtered_sda) ||
                  (sto_event && state_active && !stop_state);
        end
    end

    always @(posedge clk or negedge nReset) begin
        if (!nReset) begin
            state_r  <= ST_IDLE;
            cmd_ack  <= 1'b0;
            scl_oen  <= 1'b1;
            sda_oen  <= 1'b1;
            sda_chk_r <= 1'b0;
        end else if (rst) begin
            state_r  <= ST_IDLE;
            cmd_ack  <= 1'b0;
            scl_oen  <= 1'b1;
            sda_oen  <= 1'b1;
            sda_chk_r <= 1'b0;
        end else begin
            cmd_ack <= 1'b0;

            if (al) begin
                state_r   <= ST_IDLE;
                scl_oen   <= 1'b1;
                sda_oen   <= 1'b1;
                sda_chk_r <= 1'b0;
            end else if (ena && clk_en_r && !slave_wait_cond &&
                         !scl_sync_cond) begin
                case (state_r)
                    ST_IDLE: begin
                        case (cmd)
                            I2C_CMD_START: begin
                                state_r   <= ST_START_A;
                                scl_oen   <= 1'b1;
                                sda_oen   <= 1'b1;
                                sda_chk_r <= 1'b0;
                            end
                            I2C_CMD_STOP: begin
                                state_r   <= ST_STOP_A;
                                scl_oen   <= 1'b0;
                                sda_oen   <= 1'b0;
                                sda_chk_r <= 1'b0;
                            end
                            I2C_CMD_WRITE: begin
                                state_r   <= ST_WRITE_A;
                                scl_oen   <= 1'b0;
                                sda_oen   <= ~din;
                                sda_chk_r <= 1'b0;
                            end
                            I2C_CMD_READ: begin
                                state_r   <= ST_READ_A;
                                scl_oen   <= 1'b0;
                                sda_oen   <= 1'b1;
                                sda_chk_r <= 1'b0;
                            end
                            default: begin
                                state_r <= ST_IDLE;
                            end
                        endcase
                    end

                    ST_START_A: begin
                        state_r <= ST_START_B;
                        scl_oen <= 1'b1;
                        sda_oen <= 1'b1;
                    end
                    ST_START_B: begin
                        state_r <= ST_START_C;
                        sda_oen <= 1'b0;
                    end
                    ST_START_C: begin
                        state_r <= ST_START_D;
                        scl_oen <= 1'b0;
                    end
                    ST_START_D: begin
                        state_r <= ST_IDLE;
                        cmd_ack <= 1'b1;
                    end

                    ST_STOP_A: begin
                        state_r <= ST_STOP_B;
                        scl_oen <= 1'b1;
                    end
                    ST_STOP_B: begin
                        state_r <= ST_STOP_C;
                        sda_oen <= 1'b1;
                    end
                    ST_STOP_C: begin
                        state_r <= ST_IDLE;
                        cmd_ack <= 1'b1;
                    end

                    ST_READ_A: begin
                        state_r <= ST_READ_B;
                        scl_oen <= 1'b1;
                        sda_oen <= 1'b1;
                    end
                    ST_READ_B: begin
                        state_r <= ST_READ_C;
                    end
                    ST_READ_C: begin
                        state_r <= ST_READ_D;
                        scl_oen <= 1'b0;
                    end
                    ST_READ_D: begin
                        state_r <= ST_IDLE;
                        cmd_ack <= 1'b1;
                    end

                    ST_WRITE_A: begin
                        state_r   <= ST_WRITE_B;
                        scl_oen   <= 1'b1;
                        sda_oen   <= ~din;
                        sda_chk_r <= 1'b1;
                    end
                    ST_WRITE_B: begin
                        state_r   <= ST_WRITE_C;
                        sda_chk_r <= 1'b0;
                    end
                    ST_WRITE_C: begin
                        state_r <= ST_WRITE_D;
                        scl_oen <= 1'b0;
                    end
                    ST_WRITE_D: begin
                        state_r <= ST_IDLE;
                        cmd_ack <= 1'b1;
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