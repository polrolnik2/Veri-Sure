module i2c_master_bit_ctrl (
    input clk,
    input rst,
    input nReset,
    input ena,
    input [15:0] clk_cnt,
    input [3:0] cmd,
    input din,
    input scl_i,
    input sda_i,
    output reg cmd_ack,
    output reg busy,
    output reg al,
    output reg dout,
    output wire scl_o,
    output reg scl_oen,
    output wire sda_o,
    output reg sda_oen,
    output wire cnt_zero,
    output wire cnt_reload,
    output wire clk_en,
    output wire slave_wait,
    output wire scl_sync,
    output wire cscl,
    output wire csda,
    output wire dscl,
    output wire sta_condition,
    output wire sto_condition,
    output wire sda_chk,
    output wire fsm_active,
    output wire in_start_sequence,
    output wire in_stop_sequence,
    output wire in_read_sequence,
    output wire in_write_sequence
);

    localparam [3:0] I2C_CMD_START = 4'h1;
    localparam [3:0] I2C_CMD_STOP  = 4'h2;
    localparam [3:0] I2C_CMD_WRITE = 4'h4;
    localparam [3:0] I2C_CMD_READ  = 4'h8;

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

    reg [4:0] state;
    reg [15:0] cnt;
    reg clk_en_r;
    reg [13:0] filter_cnt;
    reg [2:0] fSCL_r, fSDA_r;
    reg cSCL_r, cSDA_r;
    reg sSCL_d, sSDA_d;
    reg sda_chk_r;

    wire sSCL_w, sSDA_w;
    wire cnt_zero_w;
    wire slave_wait_w;
    wire scl_sync_w;
    wire sta_condition_w;
    wire sto_condition_w;
    wire fsm_active_w;
    wire in_start_sequence_w;
    wire in_stop_sequence_w;
    wire in_read_sequence_w;
    wire in_write_sequence_w;
    wire cnt_reload_w;

    assign sSCL_w = (fSCL_r[2] & fSCL_r[1]) |
                    (fSCL_r[1] & fSCL_r[0]) |
                    (fSCL_r[2] & fSCL_r[0]);
    assign sSDA_w = (fSDA_r[2] & fSDA_r[1]) |
                    (fSDA_r[1] & fSDA_r[0]) |
                    (fSDA_r[2] & fSDA_r[0]);

    assign cnt_zero_w = (cnt == 16'h0000);
    assign slave_wait_w = scl_oen && !sSCL_w;
    assign scl_sync_w = sSCL_d && !sSCL_w && scl_oen;
    assign sta_condition_w = !sSDA_w && sSDA_d && sSCL_w;
    assign sto_condition_w = sSDA_w && !sSDA_d && sSCL_w;
    assign fsm_active_w = (state != ST_IDLE);
    assign in_start_sequence_w = (state == ST_START_A) || (state == ST_START_B) ||
                                 (state == ST_START_C) || (state == ST_START_D);
    assign in_stop_sequence_w = (state == ST_STOP_A) || (state == ST_STOP_B) ||
                                (state == ST_STOP_C) || (state == ST_STOP_D);
    assign in_read_sequence_w = (state == ST_READ_A) || (state == ST_READ_B) ||
                                (state == ST_READ_C) || (state == ST_READ_D);
    assign in_write_sequence_w = (state == ST_WRITE_A) || (state == ST_WRITE_B) ||
                                 (state == ST_WRITE_C) || (state == ST_WRITE_D);
    assign cnt_reload_w = !ena || scl_sync_w || (cnt_zero_w && !slave_wait_w);

    assign scl_o = 1'b0;
    assign sda_o = 1'b0;

    assign cnt_zero = cnt_zero_w;
    assign cnt_reload = !nReset || rst || cnt_reload_w;
    assign clk_en = clk_en_r;
    assign slave_wait = slave_wait_w;
    assign scl_sync = scl_sync_w;
    assign cscl = cSCL_r;
    assign csda = cSDA_r;
    assign dscl = sSCL_d;
    assign sta_condition = sta_condition_w;
    assign sto_condition = sto_condition_w;
    assign sda_chk = sda_chk_r;
    assign fsm_active = fsm_active_w;
    assign in_start_sequence = in_start_sequence_w;
    assign in_stop_sequence = in_stop_sequence_w;
    assign in_read_sequence = in_read_sequence_w;
    assign in_write_sequence = in_write_sequence_w;

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
            filter_cnt <= 14'h0000;
            fSCL_r <= 3'b111;
            fSDA_r <= 3'b111;
        end else if (rst) begin
            filter_cnt <= 14'h0000;
            fSCL_r <= 3'b111;
            fSDA_r <= 3'b111;
        end else if (!ena) begin
            filter_cnt <= 14'h0000;
            fSCL_r <= 3'b111;
            fSDA_r <= 3'b111;
        end else if (filter_cnt == 14'h0000) begin
            filter_cnt <= clk_cnt[15:2];
            fSCL_r <= {fSCL_r[1:0], cSCL_r};
            fSDA_r <= {fSDA_r[1:0], cSDA_r};
        end else begin
            filter_cnt <= filter_cnt - 14'd1;
        end
    end

    always @(posedge clk or negedge nReset) begin
        if (!nReset) begin
            sSCL_d <= 1'b1;
            sSDA_d <= 1'b1;
        end else if (rst) begin
            sSCL_d <= 1'b1;
            sSDA_d <= 1'b1;
        end else begin
            sSCL_d <= sSCL_w;
            sSDA_d <= sSDA_w;
        end
    end

    always @(posedge clk or negedge nReset) begin
        if (!nReset) begin
            cnt <= 16'h0000;
            clk_en_r <= 1'b1;
        end else if (rst) begin
            cnt <= 16'h0000;
            clk_en_r <= 1'b1;
        end else if (!ena) begin
            cnt <= clk_cnt;
            clk_en_r <= 1'b1;
        end else if (slave_wait_w) begin
            if (scl_sync_w)
                cnt <= clk_cnt;
            clk_en_r <= 1'b0;
        end else if (cnt_zero_w || scl_sync_w) begin
            cnt <= clk_cnt;
            clk_en_r <= 1'b1;
        end else begin
            cnt <= cnt - 16'd1;
            clk_en_r <= 1'b0;
        end
    end

    always @(posedge clk or negedge nReset) begin
        if (!nReset) begin
            busy <= 1'b0;
        end else if (rst) begin
            busy <= 1'b0;
        end else if (sta_condition_w) begin
            busy <= 1'b1;
        end else if (sto_condition_w) begin
            busy <= 1'b0;
        end
    end

    always @(posedge clk or negedge nReset) begin
        if (!nReset) begin
            dout <= 1'b0;
        end else if (rst) begin
            dout <= 1'b0;
        end else if (sSCL_w && !sSCL_d) begin
            dout <= sSDA_w;
        end
    end

    always @(posedge clk or negedge nReset) begin
        if (!nReset) begin
            al <= 1'b0;
        end else if (rst) begin
            al <= 1'b0;
        end else if ((sda_chk_r && sda_oen && !sSDA_w) ||
                     (sto_condition_w && fsm_active_w && !in_stop_sequence_w)) begin
            al <= 1'b1;
        end
    end

    always @(posedge clk or negedge nReset) begin
        if (!nReset) begin
            state <= ST_IDLE;
            cmd_ack <= 1'b0;
            scl_oen <= 1'b1;
            sda_oen <= 1'b1;
            sda_chk_r <= 1'b0;
        end else if (rst) begin
            state <= ST_IDLE;
            cmd_ack <= 1'b0;
            scl_oen <= 1'b1;
            sda_oen <= 1'b1;
            sda_chk_r <= 1'b0;
        end else begin
            cmd_ack <= 1'b0;

            if (al) begin
                state <= ST_IDLE;
                scl_oen <= 1'b1;
                sda_oen <= 1'b1;
                sda_chk_r <= 1'b0;
            end else if (ena && clk_en_r && !slave_wait_w) begin
                case (state)
                    ST_IDLE: begin
                        sda_chk_r <= 1'b0;
                        case (cmd)
                            I2C_CMD_START: state <= ST_START_A;
                            I2C_CMD_STOP:  state <= ST_STOP_A;
                            I2C_CMD_READ:  state <= ST_READ_A;
                            I2C_CMD_WRITE: state <= ST_WRITE_A;
                            default:       state <= ST_IDLE;
                        endcase
                    end

                    ST_START_A: begin
                        scl_oen <= 1'b1;
                        sda_oen <= 1'b1;
                        state <= ST_START_B;
                    end
                    ST_START_B: begin
                        scl_oen <= 1'b1;
                        sda_oen <= 1'b0;
                        state <= ST_START_C;
                    end
                    ST_START_C: begin
                        scl_oen <= 1'b0;
                        sda_oen <= 1'b0;
                        state <= ST_START_D;
                    end
                    ST_START_D: begin
                        cmd_ack <= 1'b1;
                        sda_chk_r <= 1'b0;
                        state <= ST_IDLE;
                    end

                    ST_STOP_A: begin
                        scl_oen <= 1'b0;
                        sda_oen <= 1'b0;
                        state <= ST_STOP_B;
                    end
                    ST_STOP_B: begin
                        scl_oen <= 1'b1;
                        sda_oen <= 1'b0;
                        state <= ST_STOP_C;
                    end
                    ST_STOP_C: begin
                        scl_oen <= 1'b1;
                        sda_oen <= 1'b1;
                        state <= ST_STOP_D;
                    end
                    ST_STOP_D: begin
                        cmd_ack <= 1'b1;
                        sda_chk_r <= 1'b0;
                        state <= ST_IDLE;
                    end

                    ST_READ_A: begin
                        scl_oen <= 1'b0;
                        sda_oen <= 1'b1;
                        state <= ST_READ_B;
                    end
                    ST_READ_B: begin
                        scl_oen <= 1'b1;
                        sda_oen <= 1'b1;
                        state <= ST_READ_C;
                    end
                    ST_READ_C: begin
                        scl_oen <= 1'b1;
                        sda_oen <= 1'b1;
                        state <= ST_READ_D;
                    end
                    ST_READ_D: begin
                        scl_oen <= 1'b0;
                        sda_oen <= 1'b1;
                        cmd_ack <= 1'b1;
                        state <= ST_IDLE;
                    end

                    ST_WRITE_A: begin
                        scl_oen <= 1'b0;
                        sda_oen <= din;
                        sda_chk_r <= 1'b0;
                        state <= ST_WRITE_B;
                    end
                    ST_WRITE_B: begin
                        scl_oen <= 1'b1;
                        sda_chk_r <= 1'b1;
                        state <= ST_WRITE_C;
                    end
                    ST_WRITE_C: begin
                        scl_oen <= 1'b1;
                        sda_chk_r <= 1'b1;
                        state <= ST_WRITE_D;
                    end
                    ST_WRITE_D: begin
                        scl_oen <= 1'b0;
                        sda_chk_r <= 1'b0;
                        cmd_ack <= 1'b1;
                        state <= ST_IDLE;
                    end

                    default: begin
                        state <= ST_IDLE;
                        scl_oen <= 1'b1;
                        sda_oen <= 1'b1;
                        sda_chk_r <= 1'b0;
                    end
                endcase
            end
        end
    end

endmodule