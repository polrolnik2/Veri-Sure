module i2c_master_bit_ctrl__probed (
    input clk,
    input rst,
    input nReset,
    input ena,
    input [15:0] clk_cnt,
    input [3:0] cmd,
    output reg cmd_ack,
    output reg busy,
    output reg al,
    input din,
    output reg dout,
    input scl_i,
    output scl_o,
    output reg scl_oen,
    input sda_i,
    output sda_o,
    output reg sda_oen,
    output cscl,
    output csda,
    output [2:0] fscl,
    output [2:0] fsda,
    output sscl,
    output ssda,
    output dscl,
    output dsda,
    output filter_cnt_expired,
    output filter_cnt_nonzero,
    output clk_en,
    output cnt_zero,
    output slave_wait,
    output scl_sync,
    output sta_condition,
    output sto_condition,
    output sda_chk,
    output idle,
    output fsm_active,
    output in_start_sequence,
    output in_stop_sequence,
    output in_read_sequence,
    output in_write_sequence,
    output write_high_phase
);

    localparam [3:0] I2C_CMD_START = 4'h1;
    localparam [3:0] I2C_CMD_STOP  = 4'h2;
    localparam [3:0] I2C_CMD_WRITE = 4'h4;
    localparam [3:0] I2C_CMD_READ  = 4'h8;

    localparam [3:0] ST_IDLE   = 4'h0,
                     ST_START_A = 4'h1,
                     ST_START_B = 4'h2,
                     ST_START_C = 4'h3,
                     ST_START_D = 4'h4,
                     ST_START_E = 4'h5,
                     ST_STOP_A  = 4'h6,
                     ST_STOP_B  = 4'h7,
                     ST_STOP_C  = 4'h8,
                     ST_WRITE_A = 4'h9,
                     ST_WRITE_B = 4'hA,
                     ST_WRITE_C = 4'hB,
                     ST_WRITE_D = 4'hC,
                     ST_READ_A  = 4'hD,
                     ST_READ_B  = 4'hE,
                     ST_READ_C  = 4'hF;

    reg [3:0] state_r;
    reg [15:0] cnt_r;
    reg clk_en_r;
    reg [15:0] filter_cnt_r;
    reg [2:0] fSCL_r, fSDA_r;
    reg cSCL_r, cSDA_r;
    reg dSCL_r, dSDA_r;
    reg sda_chk_r;

    wire sSCL_f;
    wire sSDA_f;
    wire slave_wait_i;
    wire scl_sync_i;
    wire sta_condition_i;
    wire sto_condition_i;
    wire stop_sequence_i;
    wire arbitration_lost_i;

    assign sSCL_f = (fSCL_r[2] & fSCL_r[1]) |
                    (fSCL_r[2] & fSCL_r[0]) |
                    (fSCL_r[1] & fSCL_r[0]);
    assign sSDA_f = (fSDA_r[2] & fSDA_r[1]) |
                    (fSDA_r[2] & fSDA_r[0]) |
                    (fSDA_r[1] & fSDA_r[0]);

    assign scl_o = 1'b0;
    assign sda_o = 1'b0;

    assign cscl = cSCL_r;
    assign csda = cSDA_r;
    assign fscl = fSCL_r;
    assign fsda = fSDA_r;
    assign sscl = sSCL_f;
    assign ssda = sSDA_f;
    assign dscl = dSCL_r;
    assign dsda = dSDA_r;

    assign filter_cnt_expired = (filter_cnt_r == 16'h0000);
    assign filter_cnt_nonzero = (filter_cnt_r != 16'h0000);
    assign clk_en = clk_en_r;
    assign cnt_zero = (cnt_r == 16'h0000);

    assign slave_wait_i = scl_oen && !sSCL_f;
    assign scl_sync_i = scl_oen && dSCL_r && !sSCL_f;
    assign slave_wait = slave_wait_i;
    assign scl_sync = scl_sync_i;

    assign sta_condition_i = !sSDA_f && dSDA_r && sSCL_f;
    assign sto_condition_i = sSDA_f && !dSDA_r && sSCL_f;
    assign sta_condition = sta_condition_i;
    assign sto_condition = sto_condition_i;

    assign sda_chk = sda_chk_r;

    assign idle = (state_r == ST_IDLE);
    assign fsm_active = (state_r != ST_IDLE);
    assign in_start_sequence = (state_r == ST_START_A) ||
                               (state_r == ST_START_B) ||
                               (state_r == ST_START_C) ||
                               (state_r == ST_START_D) ||
                               (state_r == ST_START_E);
    assign in_stop_sequence = (state_r == ST_STOP_A) ||
                              (state_r == ST_STOP_B) ||
                              (state_r == ST_STOP_C);
    assign in_read_sequence = (state_r == ST_READ_A) ||
                              (state_r == ST_READ_B) ||
                              (state_r == ST_READ_C);
    assign in_write_sequence = (state_r == ST_WRITE_A) ||
                               (state_r == ST_WRITE_B) ||
                               (state_r == ST_WRITE_C) ||
                               (state_r == ST_WRITE_D);
    assign write_high_phase = (state_r == ST_WRITE_C);

    assign stop_sequence_i = (state_r == ST_STOP_A) ||
                             (state_r == ST_STOP_B) ||
                             (state_r == ST_STOP_C);
    assign arbitration_lost_i = (sda_chk_r && !sSDA_f) ||
                                (sto_condition_i && !stop_sequence_i);

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
            filter_cnt_r <= 16'h0000;
            fSCL_r <= 3'b111;
            fSDA_r <= 3'b111;
        end else if (rst) begin
            filter_cnt_r <= 16'h0000;
            fSCL_r <= 3'b111;
            fSDA_r <= 3'b111;
        end else if (!ena) begin
            filter_cnt_r <= 16'h0000;
        end else if (filter_cnt_r == 16'h0000) begin
            filter_cnt_r <= clk_cnt >> 2;
            fSCL_r <= {fSCL_r[1:0], cSCL_r};
            fSDA_r <= {fSDA_r[1:0], cSDA_r};
        end else begin
            filter_cnt_r <= filter_cnt_r - 16'h0001;
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
            dSCL_r <= sSCL_f;
            dSDA_r <= sSDA_f;
        end
    end

    always @(posedge clk or negedge nReset) begin
        if (!nReset) begin
            cnt_r <= 16'h0000;
            clk_en_r <= 1'b1;
        end else if (rst) begin
            cnt_r <= 16'h0000;
            clk_en_r <= 1'b1;
        end else if (!ena) begin
            cnt_r <= clk_cnt;
            clk_en_r <= 1'b0;
        end else if (scl_sync_i) begin
            cnt_r <= clk_cnt;
            clk_en_r <= 1'b1;
        end else if (slave_wait_i) begin
            cnt_r <= cnt_r;
            clk_en_r <= 1'b0;
        end else if (cnt_r == 16'h0000) begin
            cnt_r <= clk_cnt;
            clk_en_r <= 1'b1;
        end else begin
            cnt_r <= cnt_r - 16'h0001;
            clk_en_r <= 1'b0;
        end
    end

    always @(posedge clk or negedge nReset) begin
        if (!nReset) begin
            busy <= 1'b0;
        end else if (rst) begin
            busy <= 1'b0;
        end else if (sta_condition_i) begin
            busy <= 1'b1;
        end else if (sto_condition_i) begin
            busy <= 1'b0;
        end
    end

    always @(posedge clk or negedge nReset) begin
        if (!nReset) begin
            al <= 1'b0;
        end else if (rst) begin
            al <= 1'b0;
        end else if (arbitration_lost_i) begin
            al <= 1'b1;
        end else if (clk_en_r && ena) begin
            al <= 1'b0;
        end
    end

    always @(posedge clk or negedge nReset) begin
        if (!nReset) begin
            dout <= 1'b0;
        end else if (rst) begin
            dout <= 1'b0;
        end else if (sSCL_f && !dSCL_r) begin
            dout <= sSDA_f;
        end
    end

    always @(posedge clk or negedge nReset) begin
        if (!nReset) begin
            state_r <= ST_IDLE;
            cmd_ack <= 1'b0;
            scl_oen <= 1'b1;
            sda_oen <= 1'b1;
            sda_chk_r <= 1'b0;
        end else if (rst) begin
            state_r <= ST_IDLE;
            cmd_ack <= 1'b0;
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
            end else if (clk_en_r && ena) begin
                case (state_r)
                    ST_IDLE: begin
                        case (cmd)
                            I2C_CMD_START: state_r <= ST_START_A;
                            I2C_CMD_STOP:  state_r <= ST_STOP_A;
                            I2C_CMD_WRITE: state_r <= ST_WRITE_A;
                            I2C_CMD_READ:  state_r <= ST_READ_A;
                            default:       state_r <= ST_IDLE;
                        endcase
                        sda_chk_r <= 1'b0;
                    end

                    ST_START_A: begin
                        state_r <= ST_START_B;
                        scl_oen <= 1'b1;
                        sda_oen <= 1'b1;
                        sda_chk_r <= 1'b0;
                    end
                    ST_START_B: begin
                        state_r <= ST_START_C;
                        scl_oen <= 1'b1;
                        sda_oen <= 1'b1;
                    end
                    ST_START_C: begin
                        state_r <= ST_START_D;
                        scl_oen <= 1'b1;
                        sda_oen <= 1'b0;
                    end
                    ST_START_D: begin
                        state_r <= ST_START_E;
                        scl_oen <= 1'b1;
                        sda_oen <= 1'b0;
                    end
                    ST_START_E: begin
                        state_r <= ST_IDLE;
                        scl_oen <= 1'b0;
                        sda_oen <= 1'b0;
                        cmd_ack <= 1'b1;
                    end

                    ST_STOP_A: begin
                        state_r <= ST_STOP_B;
                        scl_oen <= 1'b0;
                        sda_oen <= 1'b0;
                        sda_chk_r <= 1'b0;
                    end
                    ST_STOP_B: begin
                        state_r <= ST_STOP_C;
                        scl_oen <= 1'b1;
                        sda_oen <= 1'b0;
                    end
                    ST_STOP_C: begin
                        state_r <= ST_IDLE;
                        scl_oen <= 1'b1;
                        sda_oen <= 1'b1;
                        cmd_ack <= 1'b1;
                    end

                    ST_WRITE_A: begin
                        state_r <= ST_WRITE_B;
                        scl_oen <= 1'b0;
                        sda_oen <= din;
                        sda_chk_r <= 1'b0;
                    end
                    ST_WRITE_B: begin
                        state_r <= ST_WRITE_C;
                        scl_oen <= 1'b0;
                        sda_oen <= din;
                    end
                    ST_WRITE_C: begin
                        state_r <= ST_WRITE_D;
                        scl_oen <= 1'b1;
                        sda_oen <= din;
                        sda_chk_r <= din;
                    end
                    ST_WRITE_D: begin
                        state_r <= ST_IDLE;
                        scl_oen <= 1'b0;
                        sda_oen <= din;
                        sda_chk_r <= 1'b0;
                        cmd_ack <= 1'b1;
                    end

                    ST_READ_A: begin
                        state_r <= ST_READ_B;
                        scl_oen <= 1'b0;
                        sda_oen <= 1'b1;
                        sda_chk_r <= 1'b0;
                    end
                    ST_READ_B: begin
                        state_r <= ST_READ_C;
                        scl_oen <= 1'b1;
                        sda_oen <= 1'b1;
                    end
                    ST_READ_C: begin
                        state_r <= ST_IDLE;
                        scl_oen <= 1'b0;
                        sda_oen <= 1'b1;
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
