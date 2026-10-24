module i2c_master_bit_ctrl__probed (
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
    output            scl_oen,
    output            sda_o,
    output            sda_oen,
    output            idle,
    output            fsm_active,
    output            in_start_sequence,
    output            in_stop_sequence,
    output            in_read_sequence,
    output            in_write_sequence,
    output            write_stable_high_phase,
    output            read_sample_window,
    output            cscl,
    output            csda,
    output            filter_cnt_expired,
    output     [2:0]  fscl,
    output     [2:0]  fsda,
    output            sscl,
    output            ssda,
    output            dscl,
    output            dsda,
    output            sscl_rise,
    output            sta_condition,
    output            sto_condition,
    output            slave_wait,
    output            scl_sync,
    output            cnt_zero,
    output            clk_en,
    output            sda_chk
);

    localparam [3:0] I2C_CMD_START = 4'h1;
    localparam [3:0] I2C_CMD_STOP  = 4'h2;
    localparam [3:0] I2C_CMD_WRITE = 4'h4;
    localparam [3:0] I2C_CMD_READ  = 4'h8;

    localparam [3:0] ST_IDLE   = 4'd0;
    localparam [3:0] ST_START_A = 4'd1;
    localparam [3:0] ST_START_B = 4'd2;
    localparam [3:0] ST_START_C = 4'd3;
    localparam [3:0] ST_STOP_A  = 4'd4;
    localparam [3:0] ST_STOP_B  = 4'd5;
    localparam [3:0] ST_STOP_C  = 4'd6;
    localparam [3:0] ST_READ_A  = 4'd7;
    localparam [3:0] ST_READ_B  = 4'd8;
    localparam [3:0] ST_READ_C  = 4'd9;
    localparam [3:0] ST_WRITE_A = 4'd10;
    localparam [3:0] ST_WRITE_B = 4'd11;
    localparam [3:0] ST_WRITE_C = 4'd12;

    reg [3:0] state_r;
    reg [15:0] cnt_r;
    reg [15:0] filter_cnt_r;
    reg clk_en_r;
    reg scl_oen_r;
    reg sda_oen_r;

    reg cSCL_meta;
    reg cSCL_r;
    reg cSDA_meta;
    reg cSDA_r;
    reg [2:0] fSCL_r;
    reg [2:0] fSDA_r;
    reg dSCL_r;
    reg dSDA_r;

    wire sSCL_int;
    wire sSDA_int;
    wire cnt_zero_int;
    wire filter_cnt_expired_int;
    wire sscl_rise_int;
    wire sta_condition_int;
    wire sto_condition_int;
    wire slave_wait_int;
    wire scl_sync_int;
    wire sda_chk_int;
    wire unexpected_stop_int;
    wire arbitration_lost_int;

    assign scl_o = 1'b0;
    assign sda_o = 1'b0;
    assign scl_oen = scl_oen_r;
    assign sda_oen = sda_oen_r;

    assign sSCL_int = (fSCL_r[2] & fSCL_r[1]) |
                      (fSCL_r[1] & fSCL_r[0]) |
                      (fSCL_r[2] & fSCL_r[0]);
    assign sSDA_int = (fSDA_r[2] & fSDA_r[1]) |
                      (fSDA_r[1] & fSDA_r[0]) |
                      (fSDA_r[2] & fSDA_r[0]);

    assign cnt_zero_int = (cnt_r == 16'h0000);
    assign filter_cnt_expired_int = (filter_cnt_r == 16'h0000);
    assign sscl_rise_int = sSCL_int & ~dSCL_r;
    assign sta_condition_int = ~sSDA_int & dSDA_r & sSCL_int;
    assign sto_condition_int = sSDA_int & ~dSDA_r & sSCL_int;
    assign slave_wait_int = scl_oen_r & ~sSCL_int;
    assign scl_sync_int = scl_oen_r & ~sSCL_int & dSCL_r;

    assign sda_chk_int = (state_r == ST_WRITE_B);
    assign unexpected_stop_int =
        sto_condition_int &&
        (state_r != ST_IDLE) &&
        (state_r != ST_STOP_A) &&
        (state_r != ST_STOP_B) &&
        (state_r != ST_STOP_C);
    assign arbitration_lost_int =
        (sda_chk_int && sda_oen_r && !sSDA_int) ||
        unexpected_stop_int;

    assign idle = (state_r == ST_IDLE);
    assign fsm_active = (state_r != ST_IDLE);
    assign in_start_sequence = (state_r == ST_START_A) ||
                               (state_r == ST_START_B) ||
                               (state_r == ST_START_C);
    assign in_stop_sequence = (state_r == ST_STOP_A) ||
                              (state_r == ST_STOP_B) ||
                              (state_r == ST_STOP_C);
    assign in_read_sequence = (state_r == ST_READ_A) ||
                              (state_r == ST_READ_B) ||
                              (state_r == ST_READ_C);
    assign in_write_sequence = (state_r == ST_WRITE_A) ||
                               (state_r == ST_WRITE_B) ||
                               (state_r == ST_WRITE_C);
    assign write_stable_high_phase = (state_r == ST_WRITE_B);
    assign read_sample_window = (state_r == ST_READ_B);

    assign cscl = cSCL_r;
    assign csda = cSDA_r;
    assign filter_cnt_expired = filter_cnt_expired_int;
    assign fscl = fSCL_r;
    assign fsda = fSDA_r;
    assign sscl = sSCL_int;
    assign ssda = sSDA_int;
    assign dscl = dSCL_r;
    assign dsda = dSDA_r;
    assign sscl_rise = sscl_rise_int;
    assign sta_condition = sta_condition_int;
    assign sto_condition = sto_condition_int;
    assign slave_wait = slave_wait_int;
    assign scl_sync = scl_sync_int;
    assign cnt_zero = cnt_zero_int;
    assign clk_en = clk_en_r;
    assign sda_chk = sda_chk_int;

    always @(posedge clk or negedge nReset) begin
        if (!nReset) begin
            cSCL_meta <= 1'b1;
            cSCL_r <= 1'b1;
            cSDA_meta <= 1'b1;
            cSDA_r <= 1'b1;
        end else if (rst) begin
            cSCL_meta <= 1'b1;
            cSCL_r <= 1'b1;
            cSDA_meta <= 1'b1;
            cSDA_r <= 1'b1;
        end else begin
            cSCL_meta <= scl_i;
            cSCL_r <= cSCL_meta;
            cSDA_meta <= sda_i;
            cSDA_r <= cSDA_meta;
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
        end else if (filter_cnt_expired_int) begin
            filter_cnt_r <= clk_cnt >> 2;
            fSCL_r <= {fSCL_r[1:0], cSCL_r};
            fSDA_r <= {fSDA_r[1:0], cSDA_r};
        end else begin
            filter_cnt_r <= filter_cnt_r - 1'b1;
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
            dSCL_r <= sSCL_int;
            dSDA_r <= sSDA_int;
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
            clk_en_r <= 1'b1;
        end else if (scl_sync_int) begin
            cnt_r <= clk_cnt;
            clk_en_r <= 1'b1;
        end else if (slave_wait_int) begin
            cnt_r <= cnt_r;
            clk_en_r <= 1'b0;
        end else if (cnt_zero_int) begin
            cnt_r <= clk_cnt;
            clk_en_r <= 1'b1;
        end else begin
            cnt_r <= cnt_r - 1'b1;
            clk_en_r <= 1'b0;
        end
    end

    always @(posedge clk or negedge nReset) begin
        if (!nReset) begin
            state_r <= ST_IDLE;
            cmd_ack <= 1'b0;
            busy <= 1'b0;
            al <= 1'b0;
            dout <= 1'b0;
            scl_oen_r <= 1'b1;
            sda_oen_r <= 1'b1;
        end else if (rst) begin
            state_r <= ST_IDLE;
            cmd_ack <= 1'b0;
            busy <= 1'b0;
            al <= 1'b0;
            dout <= 1'b0;
            scl_oen_r <= 1'b1;
            sda_oen_r <= 1'b1;
        end else begin
            cmd_ack <= 1'b0;

            if (sta_condition_int)
                busy <= 1'b1;
            if (sto_condition_int)
                busy <= 1'b0;
            if (sscl_rise_int)
                dout <= sSDA_int;

            if (arbitration_lost_int) begin
                al <= 1'b1;
                state_r <= ST_IDLE;
                scl_oen_r <= 1'b1;
                sda_oen_r <= 1'b1;
            end else if (al) begin
                state_r <= ST_IDLE;
                scl_oen_r <= 1'b1;
                sda_oen_r <= 1'b1;
            end else if (ena && clk_en_r) begin
                case (state_r)
                    ST_IDLE: begin
                        case (cmd)
                            I2C_CMD_START: begin
                                state_r <= ST_START_A;
                                scl_oen_r <= 1'b1;
                                sda_oen_r <= 1'b1;
                            end
                            I2C_CMD_STOP: begin
                                state_r <= ST_STOP_A;
                                scl_oen_r <= 1'b0;
                                sda_oen_r <= 1'b0;
                            end
                            I2C_CMD_READ: begin
                                state_r <= ST_READ_A;
                                scl_oen_r <= 1'b0;
                                sda_oen_r <= 1'b1;
                            end
                            I2C_CMD_WRITE: begin
                                state_r <= ST_WRITE_A;
                                scl_oen_r <= 1'b0;
                                sda_oen_r <= din;
                            end
                            default: begin
                                state_r <= ST_IDLE;
                            end
                        endcase
                    end

                    ST_START_A: begin
                        sda_oen_r <= 1'b0;
                        state_r <= ST_START_B;
                    end
                    ST_START_B: begin
                        scl_oen_r <= 1'b0;
                        state_r <= ST_START_C;
                    end
                    ST_START_C: begin
                        state_r <= ST_IDLE;
                        cmd_ack <= 1'b1;
                    end

                    ST_STOP_A: begin
                        scl_oen_r <= 1'b1;
                        state_r <= ST_STOP_B;
                    end
                    ST_STOP_B: begin
                        sda_oen_r <= 1'b1;
                        state_r <= ST_STOP_C;
                    end
                    ST_STOP_C: begin
                        state_r <= ST_IDLE;
                        cmd_ack <= 1'b1;
                    end

                    ST_READ_A: begin
                        scl_oen_r <= 1'b1;
                        state_r <= ST_READ_B;
                    end
                    ST_READ_B: begin
                        scl_oen_r <= 1'b0;
                        state_r <= ST_READ_C;
                    end
                    ST_READ_C: begin
                        state_r <= ST_IDLE;
                        cmd_ack <= 1'b1;
                    end

                    ST_WRITE_A: begin
                        scl_oen_r <= 1'b1;
                        state_r <= ST_WRITE_B;
                    end
                    ST_WRITE_B: begin
                        scl_oen_r <= 1'b0;
                        state_r <= ST_WRITE_C;
                    end
                    ST_WRITE_C: begin
                        state_r <= ST_IDLE;
                        cmd_ack <= 1'b1;
                    end

                    default: begin
                        state_r <= ST_IDLE;
                        scl_oen_r <= 1'b1;
                        sda_oen_r <= 1'b1;
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
