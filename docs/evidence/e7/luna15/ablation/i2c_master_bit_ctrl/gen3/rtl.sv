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

    output wire       clk_en,
    output wire       cnt_zero,
    output wire       slave_wait,
    output wire       scl_sync,
    output wire       cscl,
    output wire       csda,
    output wire       filter_cnt_expired,
    output wire [2:0] fscl,
    output wire [2:0] fsda,
    output wire       sscl,
    output wire       ssda,
    output wire       dscl,
    output wire       dsda,
    output wire       sta_condition,
    output wire       sto_condition,
    output wire       sscl_rise,
    output wire       sda_chk,
    output wire       in_idle,
    output wire       fsm_active,
    output wire       in_start_sequence,
    output wire       in_stop_sequence,
    output wire       in_read_sequence,
    output wire       in_write_sequence
);

    localparam [3:0] ST_IDLE     = 4'd0,
                     ST_START_A  = 4'd1,
                     ST_START_B  = 4'd2,
                     ST_START_C  = 4'd3,
                     ST_STOP_A   = 4'd4,
                     ST_STOP_B   = 4'd5,
                     ST_STOP_C   = 4'd6,
                     ST_READ_A   = 4'd7,
                     ST_READ_B   = 4'd8,
                     ST_READ_C   = 4'd9,
                     ST_WRITE_A  = 4'd10,
                     ST_WRITE_B  = 4'd11,
                     ST_WRITE_C  = 4'd12,
                     ST_WRITE_D  = 4'd13;

    reg [3:0]  state;
    reg [15:0] cnt;
    reg        clk_en_r;

    reg        cSCL_r;
    reg        cSDA_r;
    reg [15:0] filter_cnt;
    reg [2:0]  fSCL_r;
    reg [2:0]  fSDA_r;
    reg        dSCL_r;
    reg        dSDA_r;
    reg        sda_chk_r;

    wire sSCL_int;
    wire sSDA_int;
    wire cnt_zero_int;
    wire filter_cnt_expired_int;
    wire slave_wait_int;
    wire scl_sync_int;
    wire sta_condition_int;
    wire sto_condition_int;
    wire sscl_rise_int;
    wire state_active_int;
    wire state_stop_int;
    wire arbitration_lost_int;

    assign sSCL_int = (fSCL_r[2] & fSCL_r[1]) |
                      (fSCL_r[2] & fSCL_r[0]) |
                      (fSCL_r[1] & fSCL_r[0]);
    assign sSDA_int = (fSDA_r[2] & fSDA_r[1]) |
                      (fSDA_r[2] & fSDA_r[0]) |
                      (fSDA_r[1] & fSDA_r[0]);

    assign cnt_zero_int = (cnt == 16'h0000);
    assign filter_cnt_expired_int = (filter_cnt == 16'h0000);
    assign slave_wait_int = scl_oen && !sSCL_int;
    assign scl_sync_int = scl_oen && dSCL_r && !sSCL_int;
    assign sta_condition_int = !sSDA_int && dSDA_r && sSCL_int;
    assign sto_condition_int = sSDA_int && !dSDA_r && sSCL_int;
    assign sscl_rise_int = sSCL_int && !dSCL_r;

    assign state_active_int = (state != ST_IDLE);
    assign state_stop_int = (state == ST_STOP_A) ||
                            (state == ST_STOP_B) ||
                            (state == ST_STOP_C);
    assign arbitration_lost_int =
        (sda_chk_r && !sSDA_int) ||
        (state_active_int && !state_stop_int && sto_condition_int);

    assign scl_o = 1'b0;
    assign sda_o = 1'b0;

    assign clk_en = clk_en_r;
    assign cnt_zero = cnt_zero_int;
    assign slave_wait = slave_wait_int;
    assign scl_sync = scl_sync_int;
    assign cscl = cSCL_r;
    assign csda = cSDA_r;
    assign filter_cnt_expired = filter_cnt_expired_int;
    assign fscl = fSCL_r;
    assign fsda = fSDA_r;
    assign sscl = sSCL_int;
    assign ssda = sSDA_int;
    assign dscl = dSCL_r;
    assign dsda = dSDA_r;
    assign sta_condition = sta_condition_int;
    assign sto_condition = sto_condition_int;
    assign sscl_rise = sscl_rise_int;
    assign sda_chk = sda_chk_r;
    assign in_idle = (state == ST_IDLE);
    assign fsm_active = state_active_int;
    assign in_start_sequence = (state == ST_START_A) ||
                               (state == ST_START_B) ||
                               (state == ST_START_C);
    assign in_stop_sequence = state_stop_int;
    assign in_read_sequence = (state == ST_READ_A) ||
                              (state == ST_READ_B) ||
                              (state == ST_READ_C);
    assign in_write_sequence = (state == ST_WRITE_A) ||
                               (state == ST_WRITE_B) ||
                               (state == ST_WRITE_C) ||
                               (state == ST_WRITE_D);

    always @(posedge clk or negedge nReset) begin
        if (!nReset) begin
            cnt      <= 16'h0000;
            clk_en_r <= 1'b1;
        end else if (rst) begin
            cnt      <= 16'h0000;
            clk_en_r <= 1'b1;
        end else if (!ena) begin
            cnt      <= clk_cnt;
            clk_en_r <= 1'b1;
        end else if (scl_sync_int) begin
            cnt      <= clk_cnt;
            clk_en_r <= 1'b1;
        end else if (slave_wait_int) begin
            cnt      <= cnt;
            clk_en_r <= 1'b0;
        end else if (cnt_zero_int) begin
            cnt      <= clk_cnt;
            clk_en_r <= 1'b1;
        end else begin
            cnt      <= cnt - 16'd1;
            clk_en_r <= 1'b0;
        end
    end

    always @(posedge clk or negedge nReset) begin
        if (!nReset) begin
            cSCL_r <= 1'b1;
            cSDA_r <= 1'b1;
        end else if (rst) begin
            cSCL_r <= 1'b1;
            cSDA_r <= 1'b1;
        end else begin
            cSCL_r <= scl_i;
            cSDA_r <= sda_i;
        end
    end

    always @(posedge clk or negedge nReset) begin
        if (!nReset) begin
            filter_cnt <= 16'h0000;
            fSCL_r     <= 3'b111;
            fSDA_r     <= 3'b111;
        end else if (rst) begin
            filter_cnt <= 16'h0000;
            fSCL_r     <= 3'b111;
            fSDA_r     <= 3'b111;
        end else if (!ena) begin
            filter_cnt <= 16'h0000;
        end else if (filter_cnt_expired_int) begin
            filter_cnt <= {2'b00, clk_cnt[15:2]};
            fSCL_r     <= {fSCL_r[1:0], cSCL_r};
            fSDA_r     <= {fSDA_r[1:0], cSDA_r};
        end else begin
            filter_cnt <= filter_cnt - 16'd1;
        end
    end

    always @(posedge clk or negedge nReset) begin
        if (!nReset) begin
            dSCL_r <= 1'b1;
            dSDA_r <= 1'b1;
            dout   <= 1'b0;
        end else if (rst) begin
            dSCL_r <= 1'b1;
            dSDA_r <= 1'b1;
            dout   <= 1'b0;
        end else begin
            dSCL_r <= sSCL_int;
            dSDA_r <= sSDA_int;
            if (sscl_rise_int)
                dout <= sSDA_int;
        end
    end

    always @(posedge clk or negedge nReset) begin
        if (!nReset) begin
            busy <= 1'b0;
            al   <= 1'b0;
        end else if (rst) begin
            busy <= 1'b0;
            al   <= 1'b0;
        end else begin
            if (sta_condition_int)
                busy <= 1'b1;
            else if (sto_condition_int)
                busy <= 1'b0;

            if (arbitration_lost_int)
                al <= 1'b1;
        end
    end

    always @(posedge clk or negedge nReset) begin
        if (!nReset) begin
            state    <= ST_IDLE;
            cmd_ack  <= 1'b0;
            scl_oen  <= 1'b1;
            sda_oen  <= 1'b1;
            sda_chk_r <= 1'b0;
        end else if (rst) begin
            state    <= ST_IDLE;
            cmd_ack  <= 1'b0;
            scl_oen  <= 1'b1;
            sda_oen  <= 1'b1;
            sda_chk_r <= 1'b0;
        end else begin
            cmd_ack <= 1'b0;

            if (arbitration_lost_int) begin
                state     <= ST_IDLE;
                scl_oen   <= 1'b1;
                sda_oen   <= 1'b1;
                sda_chk_r <= 1'b0;
            end else if (ena && clk_en_r && !slave_wait_int &&
                         !scl_sync_int) begin
                case (state)
                    ST_IDLE: begin
                        case (cmd)
                            4'b0001: state <= ST_START_A;
                            4'b0010: state <= ST_STOP_A;
                            4'b0100: state <= ST_WRITE_A;
                            4'b1000: state <= ST_READ_A;
                            default: state <= ST_IDLE;
                        endcase
                    end

                    ST_START_A: begin
                        sda_oen <= 1'b1;
                        scl_oen <= 1'b1;
                        state   <= ST_START_B;
                    end
                    ST_START_B: begin
                        sda_oen <= 1'b0;
                        state   <= ST_START_C;
                    end
                    ST_START_C: begin
                        scl_oen <= 1'b0;
                        cmd_ack <= 1'b1;
                        state   <= ST_IDLE;
                    end

                    ST_STOP_A: begin
                        sda_oen <= 1'b0;
                        scl_oen <= 1'b0;
                        state   <= ST_STOP_B;
                    end
                    ST_STOP_B: begin
                        scl_oen <= 1'b1;
                        state   <= ST_STOP_C;
                    end
                    ST_STOP_C: begin
                        sda_oen <= 1'b1;
                        cmd_ack <= 1'b1;
                        state   <= ST_IDLE;
                    end

                    ST_READ_A: begin
                        sda_oen <= 1'b1;
                        state   <= ST_READ_B;
                    end
                    ST_READ_B: begin
                        scl_oen <= 1'b1;
                        state   <= ST_READ_C;
                    end
                    ST_READ_C: begin
                        scl_oen <= 1'b0;
                        cmd_ack <= 1'b1;
                        state   <= ST_IDLE;
                    end

                    ST_WRITE_A: begin
                        sda_oen <= din;
                        state   <= ST_WRITE_B;
                    end
                    ST_WRITE_B: begin
                        scl_oen <= 1'b1;
                        state   <= ST_WRITE_C;
                    end
                    ST_WRITE_C: begin
                        sda_chk_r <= din;
                        state     <= ST_WRITE_D;
                    end
                    ST_WRITE_D: begin
                        scl_oen   <= 1'b0;
                        sda_chk_r <= 1'b0;
                        cmd_ack   <= 1'b1;
                        state     <= ST_IDLE;
                    end

                    default: begin
                        state     <= ST_IDLE;
                        scl_oen   <= 1'b1;
                        sda_oen   <= 1'b1;
                        sda_chk_r <= 1'b0;
                    end
                endcase
            end
        end
    end

endmodule