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

    localparam [3:0] I2C_CMD_NOP   = 4'b0000;
    localparam [3:0] I2C_CMD_START = 4'b0001;
    localparam [3:0] I2C_CMD_STOP  = 4'b0010;
    localparam [3:0] I2C_CMD_WRITE = 4'b0100;
    localparam [3:0] I2C_CMD_READ  = 4'b1000;

    localparam [3:0] ST_IDLE         = 4'd0;
    localparam [3:0] ST_START_RELEASE= 4'd1;
    localparam [3:0] ST_START_ASSERT = 4'd2;
    localparam [3:0] ST_STOP_LOW     = 4'd3;
    localparam [3:0] ST_STOP_RELEASE = 4'd4;
    localparam [3:0] ST_READ_LOW     = 4'd5;
    localparam [3:0] ST_READ_HIGH    = 4'd6;
    localparam [3:0] ST_WRITE_LOW    = 4'd7;
    localparam [3:0] ST_WRITE_HIGH   = 4'd8;

    reg [3:0]  state_r;
    reg [15:0] cnt_r;
    reg        clk_en_r;
    reg [13:0] filter_cnt_r;
    reg        cSCL_r;
    reg        cSDA_r;
    reg [2:0]  fSCL_r;
    reg [2:0]  fSDA_r;
    reg        dSCL_r;
    reg        dSDA_r;

    wire sSCL_w;
    wire sSDA_w;
    wire sta_condition_w;
    wire sto_condition_w;
    wire sscl_rise_w;
    wire slave_wait_w;
    wire scl_sync_w;
    wire sda_chk_w;
    wire stop_sequence_w;
    wire active_w;

    assign scl_o = 1'b0;
    assign sda_o = 1'b0;

    assign sSCL_w = (fSCL_r[2] & fSCL_r[1]) |
                    (fSCL_r[1] & fSCL_r[0]) |
                    (fSCL_r[2] & fSCL_r[0]);
    assign sSDA_w = (fSDA_r[2] & fSDA_r[1]) |
                    (fSDA_r[1] & fSDA_r[0]) |
                    (fSDA_r[2] & fSDA_r[0]);

    assign sta_condition_w = ~sSDA_w & dSDA_r & sSCL_w;
    assign sto_condition_w =  sSDA_w & ~dSDA_r & sSCL_w;
    assign sscl_rise_w = sSCL_w & ~dSCL_r;

    assign slave_wait_w = scl_oen & ~sSCL_w;
    assign scl_sync_w = scl_oen & dSCL_r & ~sSCL_w;
    assign sda_chk_w = (state_r == ST_WRITE_HIGH);
    assign stop_sequence_w = (state_r == ST_STOP_LOW) ||
                             (state_r == ST_STOP_RELEASE);
    assign active_w = (state_r != ST_IDLE);

    assign clk_en = clk_en_r;
    assign cnt_zero = (cnt_r == 16'd0);
    assign slave_wait = slave_wait_w;
    assign scl_sync = scl_sync_w;
    assign cscl = cSCL_r;
    assign csda = cSDA_r;
    assign filter_cnt_expired = (filter_cnt_r == 14'd0);
    assign fscl = fSCL_r;
    assign fsda = fSDA_r;
    assign sscl = sSCL_w;
    assign ssda = sSDA_w;
    assign dscl = dSCL_r;
    assign dsda = dSDA_r;
    assign sta_condition = sta_condition_w;
    assign sto_condition = sto_condition_w;
    assign sscl_rise = sscl_rise_w;
    assign sda_chk = sda_chk_w;

    assign in_idle = (state_r == ST_IDLE);
    assign fsm_active = active_w;
    assign in_start_sequence = (state_r == ST_START_RELEASE) ||
                               (state_r == ST_START_ASSERT);
    assign in_stop_sequence = stop_sequence_w;
    assign in_read_sequence = (state_r == ST_READ_LOW) ||
                              (state_r == ST_READ_HIGH);
    assign in_write_sequence = (state_r == ST_WRITE_LOW) ||
                               (state_r == ST_WRITE_HIGH);

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
        end else if (scl_sync_w) begin
            cnt_r    <= clk_cnt;
            clk_en_r <= 1'b1;
        end else if (slave_wait_w) begin
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
            cSCL_r       <= 1'b1;
            cSDA_r       <= 1'b1;
            fSCL_r       <= 3'b111;
            fSDA_r       <= 3'b111;
            filter_cnt_r <= 14'd0;
        end else if (rst) begin
            cSCL_r       <= 1'b1;
            cSDA_r       <= 1'b1;
            fSCL_r       <= 3'b111;
            fSDA_r       <= 3'b111;
            filter_cnt_r <= 14'd0;
        end else begin
            cSCL_r <= scl_i;
            cSDA_r <= sda_i;

            if (!ena) begin
                filter_cnt_r <= 14'd0;
            end else if (filter_cnt_r == 14'd0) begin
                filter_cnt_r <= clk_cnt[15:2];
                fSCL_r <= {fSCL_r[1:0], cSCL_r};
                fSDA_r <= {fSDA_r[1:0], cSDA_r};
            end else begin
                filter_cnt_r <= filter_cnt_r - 14'd1;
            end
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
            dSCL_r <= sSCL_w;
            dSDA_r <= sSDA_w;
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
            al <= 1'b0;
        end else if (rst) begin
            al <= 1'b0;
        end else if (sda_chk_w && !sSDA_w) begin
            al <= 1'b1;
        end else if (sto_condition_w && active_w && !stop_sequence_w) begin
            al <= 1'b1;
        end else begin
            al <= 1'b0;
        end
    end

    always @(posedge clk or negedge nReset) begin
        if (!nReset) begin
            dout <= 1'b0;
        end else if (rst) begin
            dout <= 1'b0;
        end else if (sscl_rise_w) begin
            dout <= sSDA_w;
        end
    end

    always @(posedge clk or negedge nReset) begin
        if (!nReset) begin
            state_r <= ST_IDLE;
            cmd_ack <= 1'b0;
            scl_oen <= 1'b1;
            sda_oen <= 1'b1;
        end else if (rst) begin
            state_r <= ST_IDLE;
            cmd_ack <= 1'b0;
            scl_oen <= 1'b1;
            sda_oen <= 1'b1;
        end else begin
            cmd_ack <= 1'b0;

            if (al) begin
                state_r <= ST_IDLE;
                scl_oen <= 1'b1;
                sda_oen <= 1'b1;
            end else if (ena && clk_en_r) begin
                case (state_r)
                    ST_IDLE: begin
                        case (cmd)
                            I2C_CMD_START: begin
                                state_r <= ST_START_RELEASE;
                                scl_oen <= 1'b1;
                                sda_oen <= 1'b1;
                            end
                            I2C_CMD_STOP: begin
                                state_r <= ST_STOP_LOW;
                                scl_oen <= 1'b0;
                                sda_oen <= 1'b0;
                            end
                            I2C_CMD_READ: begin
                                state_r <= ST_READ_LOW;
                                scl_oen <= 1'b0;
                                sda_oen <= 1'b1;
                            end
                            I2C_CMD_WRITE: begin
                                state_r <= ST_WRITE_LOW;
                                scl_oen <= 1'b0;
                                sda_oen <= din;
                            end
                            default: begin
                                state_r <= ST_IDLE;
                            end
                        endcase
                    end

                    ST_START_RELEASE: begin
                        state_r <= ST_START_ASSERT;
                        scl_oen <= 1'b1;
                        sda_oen <= 1'b0;
                    end

                    ST_START_ASSERT: begin
                        state_r <= ST_IDLE;
                        scl_oen <= 1'b0;
                        sda_oen <= 1'b0;
                        cmd_ack <= 1'b1;
                    end

                    ST_STOP_LOW: begin
                        state_r <= ST_STOP_RELEASE;
                        scl_oen <= 1'b1;
                        sda_oen <= 1'b0;
                    end

                    ST_STOP_RELEASE: begin
                        state_r <= ST_IDLE;
                        scl_oen <= 1'b1;
                        sda_oen <= 1'b1;
                        cmd_ack <= 1'b1;
                    end

                    ST_READ_LOW: begin
                        state_r <= ST_READ_HIGH;
                        scl_oen <= 1'b1;
                        sda_oen <= 1'b1;
                    end

                    ST_READ_HIGH: begin
                        state_r <= ST_IDLE;
                        scl_oen <= 1'b0;
                        sda_oen <= 1'b1;
                        cmd_ack <= 1'b1;
                    end

                    ST_WRITE_LOW: begin
                        state_r <= ST_WRITE_HIGH;
                        scl_oen <= 1'b1;
                        sda_oen <= din;
                    end

                    ST_WRITE_HIGH: begin
                        state_r <= ST_IDLE;
                        scl_oen <= 1'b0;
                        sda_oen <= din;
                        cmd_ack <= 1'b1;
                    end

                    default: begin
                        state_r <= ST_IDLE;
                        scl_oen <= 1'b1;
                        sda_oen <= 1'b1;
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
