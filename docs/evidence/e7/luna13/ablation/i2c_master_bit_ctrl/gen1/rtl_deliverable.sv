module i2c_master_bit_ctrl__probed (
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
    output scl_o,
    output reg scl_oen,
    output sda_o,
    output reg sda_oen,

    output idle,
    output fsm_active,
    output in_start_sequence,
    output in_stop_sequence,
    output in_read_sequence,
    output in_write_sequence,
    output write_stable_high_phase,
    output read_sample_window,
    output cscl,
    output csda,
    output filter_cnt_expired,
    output [2:0] fscl,
    output [2:0] fsda,
    output sscl,
    output ssda,
    output dscl,
    output dsda,
    output sscl_rise,
    output sta_condition,
    output sto_condition,
    output slave_wait,
    output scl_sync,
    output cnt_zero,
    output clk_en,
    output sda_chk
);

    localparam [3:0] I2C_CMD_START = 4'h1;
    localparam [3:0] I2C_CMD_STOP  = 4'h2;
    localparam [3:0] I2C_CMD_WRITE = 4'h4;
    localparam [3:0] I2C_CMD_READ  = 4'h8;

    localparam [3:0] ST_IDLE   = 4'd0,
                     ST_STA_A  = 4'd1,
                     ST_STA_B  = 4'd2,
                     ST_STA_C  = 4'd3,
                     ST_STO_A  = 4'd4,
                     ST_STO_B  = 4'd5,
                     ST_STO_C  = 4'd6,
                     ST_RD_A   = 4'd7,
                     ST_RD_B   = 4'd8,
                     ST_RD_C   = 4'd9,
                     ST_WR_A   = 4'd10,
                     ST_WR_B   = 4'd11,
                     ST_WR_C   = 4'd12;

    reg [3:0] state_r;
    reg [15:0] cnt_r;
    reg clk_en_r;

    reg [1:0] cSCL_r;
    reg [1:0] cSDA_r;
    reg [13:0] filter_cnt_r;
    reg [2:0] fSCL_r;
    reg [2:0] fSDA_r;
    reg dSCL_r;
    reg dSDA_r;
    reg sda_chk_r;

    wire sSCL_r;
    wire sSDA_r;
    wire filter_cnt_expired_r;
    wire sscl_rise_r;
    wire sta_condition_r;
    wire sto_condition_r;
    wire slave_wait_r;
    wire scl_sync_r;
    wire cnt_zero_r;
    wire stop_state_r;
    wire arbitration_lost_r;

    assign sSCL_r = (fSCL_r[2] & fSCL_r[1]) |
                    (fSCL_r[1] & fSCL_r[0]) |
                    (fSCL_r[2] & fSCL_r[0]);
    assign sSDA_r = (fSDA_r[2] & fSDA_r[1]) |
                    (fSDA_r[1] & fSDA_r[0]) |
                    (fSDA_r[2] & fSDA_r[0]);

    assign filter_cnt_expired_r = ena && (filter_cnt_r == 14'd0);
    assign sscl_rise_r = sSCL_r && !dSCL_r;
    assign sta_condition_r = !sSDA_r && dSDA_r && sSCL_r;
    assign sto_condition_r = sSDA_r && !dSDA_r && sSCL_r;
    assign slave_wait_r = scl_oen && !sSCL_r;
    assign scl_sync_r = dSCL_r && !sSCL_r && scl_oen;
    assign cnt_zero_r = (cnt_r == 16'd0);

    assign stop_state_r = (state_r == ST_STO_A) ||
                          (state_r == ST_STO_B) ||
                          (state_r == ST_STO_C);

    assign arbitration_lost_r =
        (sda_chk_r && sda_oen && !sSDA_r) ||
        (sto_condition_r && (state_r != ST_IDLE) && !stop_state_r);

    assign scl_o = 1'b0;
    assign sda_o = 1'b0;

    assign idle = (state_r == ST_IDLE);
    assign fsm_active = (state_r != ST_IDLE);
    assign in_start_sequence = (state_r == ST_STA_A) ||
                               (state_r == ST_STA_B) ||
                               (state_r == ST_STA_C);
    assign in_stop_sequence = stop_state_r;
    assign in_read_sequence = (state_r == ST_RD_A) ||
                              (state_r == ST_RD_B) ||
                              (state_r == ST_RD_C);
    assign in_write_sequence = (state_r == ST_WR_A) ||
                               (state_r == ST_WR_B) ||
                               (state_r == ST_WR_C);
    assign write_stable_high_phase = (state_r == ST_WR_B);
    assign read_sample_window = (state_r == ST_RD_B);

    assign cscl = cSCL_r[1];
    assign csda = cSDA_r[1];
    assign filter_cnt_expired = filter_cnt_expired_r;
    assign fscl = fSCL_r;
    assign fsda = fSDA_r;
    assign sscl = sSCL_r;
    assign ssda = sSDA_r;
    assign dscl = dSCL_r;
    assign dsda = dSDA_r;
    assign sscl_rise = sscl_rise_r;
    assign sta_condition = sta_condition_r;
    assign sto_condition = sto_condition_r;
    assign slave_wait = slave_wait_r;
    assign scl_sync = scl_sync_r;
    assign cnt_zero = cnt_zero_r;
    assign clk_en = clk_en_r;
    assign sda_chk = sda_chk_r;

    always @(posedge clk or negedge nReset) begin
        if (!nReset) begin
            cSCL_r <= 2'b11;
            cSDA_r <= 2'b11;
        end else if (rst) begin
            cSCL_r <= 2'b11;
            cSDA_r <= 2'b11;
        end else begin
            cSCL_r <= {cSCL_r[0], scl_i};
            cSDA_r <= {cSDA_r[0], sda_i};
        end
    end

    always @(posedge clk or negedge nReset) begin
        if (!nReset) begin
            filter_cnt_r <= 14'd0;
            fSCL_r <= 3'b111;
            fSDA_r <= 3'b111;
        end else if (rst) begin
            filter_cnt_r <= 14'd0;
            fSCL_r <= 3'b111;
            fSDA_r <= 3'b111;
        end else if (!ena) begin
            filter_cnt_r <= clk_cnt[15:2];
        end else if (filter_cnt_r == 14'd0) begin
            filter_cnt_r <= clk_cnt[15:2];
            fSCL_r <= {fSCL_r[1:0], cSCL_r[1]};
            fSDA_r <= {fSDA_r[1:0], cSDA_r[1]};
        end else begin
            filter_cnt_r <= filter_cnt_r - 1'b1;
        end
    end

    always @(posedge clk or negedge nReset) begin
        if (!nReset) begin
            dSCL_r <= 1'b1;
            dSDA_r <= 1'b1;
            dout <= 1'b0;
        end else if (rst) begin
            dSCL_r <= 1'b1;
            dSDA_r <= 1'b1;
            dout <= 1'b0;
        end else begin
            dSCL_r <= sSCL_r;
            dSDA_r <= sSDA_r;
            if (sscl_rise_r)
                dout <= sSDA_r;
        end
    end

    always @(posedge clk or negedge nReset) begin
        if (!nReset) begin
            cnt_r <= 16'd0;
            clk_en_r <= 1'b1;
        end else if (rst) begin
            cnt_r <= 16'd0;
            clk_en_r <= 1'b1;
        end else if (!ena) begin
            cnt_r <= clk_cnt;
            clk_en_r <= 1'b1;
        end else if (cnt_zero_r) begin
            cnt_r <= clk_cnt;
            clk_en_r <= 1'b1;
        end else if (scl_sync_r) begin
            cnt_r <= clk_cnt;
            clk_en_r <= 1'b1;
        end else if (slave_wait_r) begin
            cnt_r <= cnt_r;
            clk_en_r <= 1'b0;
        end else begin
            cnt_r <= cnt_r - 1'b1;
            clk_en_r <= 1'b0;
        end
    end

    always @(posedge clk or negedge nReset) begin
        if (!nReset) begin
            busy <= 1'b0;
        end else if (rst) begin
            busy <= 1'b0;
        end else if (sta_condition_r) begin
            busy <= 1'b1;
        end else if (sto_condition_r) begin
            busy <= 1'b0;
        end
    end

    always @(posedge clk or negedge nReset) begin
        if (!nReset) begin
            state_r <= ST_IDLE;
            cmd_ack <= 1'b0;
            al <= 1'b0;
            scl_oen <= 1'b1;
            sda_oen <= 1'b1;
            sda_chk_r <= 1'b0;
        end else if (rst) begin
            state_r <= ST_IDLE;
            cmd_ack <= 1'b0;
            al <= 1'b0;
            scl_oen <= 1'b1;
            sda_oen <= 1'b1;
            sda_chk_r <= 1'b0;
        end else begin
            cmd_ack <= 1'b0;

            if (al) begin
                state_r <= ST_IDLE;
                scl_oen <= 1'b1;
                sda_oen <= 1'b1;
                sda_chk_r <= 1'b0;
            end else if (arbitration_lost_r) begin
                state_r <= ST_IDLE;
                scl_oen <= 1'b1;
                sda_oen <= 1'b1;
                sda_chk_r <= 1'b0;
                al <= 1'b1;
            end else if (ena && clk_en_r) begin
                case (state_r)
                    ST_IDLE: begin
                        case (cmd)
                            I2C_CMD_START: state_r <= ST_STA_A;
                            I2C_CMD_STOP:  state_r <= ST_STO_A;
                            I2C_CMD_READ:  state_r <= ST_RD_A;
                            I2C_CMD_WRITE: state_r <= ST_WR_A;
                            default:       state_r <= ST_IDLE;
                        endcase
                    end

                    ST_STA_A: begin
                        scl_oen <= 1'b1;
                        sda_oen <= 1'b1;
                        sda_chk_r <= 1'b0;
                        state_r <= ST_STA_B;
                    end
                    ST_STA_B: begin
                        scl_oen <= 1'b1;
                        sda_oen <= 1'b0;
                        state_r <= ST_STA_C;
                    end
                    ST_STA_C: begin
                        scl_oen <= 1'b0;
                        sda_oen <= 1'b0;
                        state_r <= ST_IDLE;
                        cmd_ack <= 1'b1;
                    end

                    ST_STO_A: begin
                        scl_oen <= 1'b0;
                        sda_oen <= 1'b0;
                        state_r <= ST_STO_B;
                    end
                    ST_STO_B: begin
                        scl_oen <= 1'b1;
                        state_r <= ST_STO_C;
                    end
                    ST_STO_C: begin
                        sda_oen <= 1'b1;
                        state_r <= ST_IDLE;
                        cmd_ack <= 1'b1;
                    end

                    ST_RD_A: begin
                        scl_oen <= 1'b0;
                        sda_oen <= 1'b1;
                        state_r <= ST_RD_B;
                    end
                    ST_RD_B: begin
                        scl_oen <= 1'b1;
                        state_r <= ST_RD_C;
                    end
                    ST_RD_C: begin
                        scl_oen <= 1'b0;
                        state_r <= ST_IDLE;
                        cmd_ack <= 1'b1;
                    end

                    ST_WR_A: begin
                        scl_oen <= 1'b0;
                        sda_oen <= din;
                        sda_chk_r <= 1'b0;
                        state_r <= ST_WR_B;
                    end
                    ST_WR_B: begin
                        scl_oen <= 1'b1;
                        sda_chk_r <= 1'b1;
                        state_r <= ST_WR_C;
                    end
                    ST_WR_C: begin
                        scl_oen <= 1'b0;
                        sda_chk_r <= 1'b0;
                        state_r <= ST_IDLE;
                        cmd_ack <= 1'b1;
                    end

                    default: begin
                        state_r <= ST_IDLE;
                        scl_oen <= 1'b1;
                        sda_oen <= 1'b1;
                        sda_chk_r <= 1'b0;
                    end
                endcase
            end
        end
    end

endmodule

// Shipped interface: the contract's ports, probes left unconnected.
module i2c_master_bit_ctrl (
    input wire clk,
    input wire rst,
    input wire nReset,
    input wire ena,
    input wire [15:0] clk_cnt,
    input wire [3:0] cmd,
    input wire din,
    input wire scl_i,
    input wire sda_i,
    output wire cmd_ack,
    output wire busy,
    output wire al,
    output wire dout,
    output wire scl_o,
    output wire scl_oen,
    output wire sda_o,
    output wire sda_oen
);
    i2c_master_bit_ctrl__probed u_probed (
        .clk(clk),
        .rst(rst),
        .nReset(nReset),
        .ena(ena),
        .clk_cnt(clk_cnt),
        .cmd(cmd),
        .din(din),
        .scl_i(scl_i),
        .sda_i(sda_i),
        .cmd_ack(cmd_ack),
        .busy(busy),
        .al(al),
        .dout(dout),
        .scl_o(scl_o),
        .scl_oen(scl_oen),
        .sda_o(sda_o),
        .sda_oen(sda_oen)
    );
endmodule
