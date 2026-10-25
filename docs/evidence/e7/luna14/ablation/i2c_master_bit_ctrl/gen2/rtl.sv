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
    output     [ 2:0] fscl,
    output     [ 2:0] fsda,
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

localparam [3:0] I2C_CMD_START = 4'd1;
localparam [3:0] I2C_CMD_STOP  = 4'd2;
localparam [3:0] I2C_CMD_WRITE = 4'd4;
localparam [3:0] I2C_CMD_READ  = 4'd8;

localparam [4:0] S_IDLE    = 5'd0,
                 S_START_A = 5'd1,
                 S_START_B = 5'd2,
                 S_START_C = 5'd3,
                 S_START_D = 5'd4,
                 S_START_E = 5'd5,
                 S_STOP_A  = 5'd6,
                 S_STOP_B  = 5'd7,
                 S_STOP_C  = 5'd8,
                 S_WR_A    = 5'd9,
                 S_WR_B    = 5'd10,
                 S_WR_C    = 5'd11,
                 S_WR_D    = 5'd12,
                 S_RD_A    = 5'd13,
                 S_RD_B    = 5'd14,
                 S_RD_C    = 5'd15,
                 S_RD_D    = 5'd16;

reg [4:0] state;
reg [1:0] cSCL_r;
reg [1:0] cSDA_r;
reg [2:0] fSCL_r;
reg [2:0] fSDA_r;
reg [15:0] filter_cnt_r;
reg [15:0] cnt_r;
reg clk_en_r;
reg dSCL_r;
reg dSDA_r;

wire sSCL_val;
wire sSDA_val;
wire cnt_zero_val;
wire filter_cnt_expired_val;
wire slave_wait_val;
wire scl_sync_val;
wire sta_condition_val;
wire sto_condition_val;
wire start_state_val;
wire stop_state_val;
wire read_state_val;
wire write_state_val;
wire fsm_active_val;
wire write_high_val;
wire sda_chk_active;
wire arb_lost_event;

assign sSCL_val = (fSCL_r[2] & fSCL_r[1]) |
                  (fSCL_r[1] & fSCL_r[0]) |
                  (fSCL_r[2] & fSCL_r[0]);
assign sSDA_val = (fSDA_r[2] & fSDA_r[1]) |
                  (fSDA_r[1] & fSDA_r[0]) |
                  (fSDA_r[2] & fSDA_r[0]);

assign cnt_zero_val = (cnt_r == 16'd0);
assign filter_cnt_expired_val = (filter_cnt_r == 16'd0);
assign slave_wait_val = scl_oen && !sSCL_val;
assign scl_sync_val = dSCL_r && !sSCL_val && scl_oen;
assign sta_condition_val = !sSDA_val && dSDA_r && sSCL_val;
assign sto_condition_val = sSDA_val && !dSDA_r && sSCL_val;

assign start_state_val = (state == S_START_A) ||
                         (state == S_START_B) ||
                         (state == S_START_C) ||
                         (state == S_START_D) ||
                         (state == S_START_E);
assign stop_state_val = (state == S_STOP_A) ||
                        (state == S_STOP_B) ||
                        (state == S_STOP_C);
assign read_state_val = (state == S_RD_A) ||
                        (state == S_RD_B) ||
                        (state == S_RD_C) ||
                        (state == S_RD_D);
assign write_state_val = (state == S_WR_A) ||
                         (state == S_WR_B) ||
                         (state == S_WR_C) ||
                         (state == S_WR_D);
assign fsm_active_val = (state != S_IDLE);
assign write_high_val = (state == S_WR_C) || (state == S_WR_D);
assign sda_chk_active = write_high_val;
assign arb_lost_event = (sda_chk_active && sda_oen && !sSDA_val) ||
                        (sto_condition_val && fsm_active_val &&
                         (cmd != I2C_CMD_STOP));

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
assign filter_cnt_expired = filter_cnt_expired_val;
assign filter_cnt_nonzero = (filter_cnt_r != 16'd0);
assign clk_en = clk_en_r;
assign cnt_zero = cnt_zero_val;
assign slave_wait = slave_wait_val;
assign scl_sync = scl_sync_val;
assign sta_condition = sta_condition_val;
assign sto_condition = sto_condition_val;
assign sda_chk = sda_chk_active;
assign idle = (state == S_IDLE);
assign fsm_active = fsm_active_val;
assign in_start_sequence = start_state_val;
assign in_stop_sequence = stop_state_val;
assign in_read_sequence = read_state_val;
assign in_write_sequence = write_state_val;
assign write_high_phase = write_high_val;

always @(posedge clk or negedge nReset) begin
    if (!nReset) begin
        cSCL_r <= 2'b11;
        cSDA_r <= 2'b11;
        fSCL_r <= 3'b111;
        fSDA_r <= 3'b111;
        filter_cnt_r <= 16'd0;
    end else if (rst) begin
        cSCL_r <= 2'b11;
        cSDA_r <= 2'b11;
        fSCL_r <= 3'b111;
        fSDA_r <= 3'b111;
        filter_cnt_r <= 16'd0;
    end else begin
        cSCL_r <= {cSCL_r[0], scl_i};
        cSDA_r <= {cSDA_r[0], sda_i};

        if (!ena) begin
            filter_cnt_r <= 16'd0;
        end else if (filter_cnt_expired_val) begin
            filter_cnt_r <= clk_cnt >> 2;
            fSCL_r <= {fSCL_r[1:0], cSCL_r[1]};
            fSDA_r <= {fSDA_r[1:0], cSDA_r[1]};
        end else begin
            filter_cnt_r <= filter_cnt_r - 16'd1;
        end
    end
end

always @(posedge clk or negedge nReset) begin
    if (!nReset) begin
        dSCL_r <= 1'b1;
        dSDA_r <= 1'b1;
        busy <= 1'b0;
        dout <= 1'b0;
    end else if (rst) begin
        dSCL_r <= 1'b1;
        dSDA_r <= 1'b1;
        busy <= 1'b0;
        dout <= 1'b0;
    end else begin
        dSCL_r <= sSCL_val;
        dSDA_r <= sSDA_val;

        if (sSCL_val && !dSCL_r)
            dout <= sSDA_val;

        if (sta_condition_val)
            busy <= 1'b1;
        else if (sto_condition_val)
            busy <= 1'b0;
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
    end else if (scl_sync_val) begin
        cnt_r <= clk_cnt;
        clk_en_r <= 1'b1;
    end else if (slave_wait_val) begin
        cnt_r <= cnt_r;
        clk_en_r <= 1'b0;
    end else if (cnt_zero_val) begin
        cnt_r <= clk_cnt;
        clk_en_r <= 1'b1;
    end else begin
        cnt_r <= cnt_r - 16'd1;
        clk_en_r <= 1'b0;
    end
end

always @(posedge clk or negedge nReset) begin
    if (!nReset)
        al <= 1'b0;
    else if (rst)
        al <= 1'b0;
    else if (sta_condition_val)
        al <= 1'b0;
    else if (arb_lost_event)
        al <= 1'b1;
end

always @(posedge clk or negedge nReset) begin
    if (!nReset) begin
        state <= S_IDLE;
        cmd_ack <= 1'b0;
        scl_oen <= 1'b1;
        sda_oen <= 1'b1;
    end else if (rst) begin
        state <= S_IDLE;
        cmd_ack <= 1'b0;
        scl_oen <= 1'b1;
        sda_oen <= 1'b1;
    end else begin
        cmd_ack <= 1'b0;

        if (arb_lost_event) begin
            state <= S_IDLE;
            scl_oen <= 1'b1;
            sda_oen <= 1'b1;
        end else if (clk_en_r && ena && !slave_wait_val) begin
            case (state)
                S_IDLE: begin
                    scl_oen <= 1'b1;
                    sda_oen <= 1'b1;
                    case (cmd)
                        I2C_CMD_START: state <= S_START_A;
                        I2C_CMD_STOP:  state <= S_STOP_A;
                        I2C_CMD_WRITE: state <= S_WR_A;
                        I2C_CMD_READ:  state <= S_RD_A;
                        default:       state <= S_IDLE;
                    endcase
                end

                S_START_A: begin
                    state <= S_START_B;
                    scl_oen <= 1'b1;
                    sda_oen <= 1'b1;
                end
                S_START_B: begin
                    state <= S_START_C;
                    scl_oen <= 1'b1;
                    sda_oen <= 1'b1;
                end
                S_START_C: begin
                    state <= S_START_D;
                    scl_oen <= 1'b1;
                    sda_oen <= 1'b0;
                end
                S_START_D: begin
                    state <= S_START_E;
                    scl_oen <= 1'b1;
                    sda_oen <= 1'b0;
                end
                S_START_E: begin
                    state <= S_IDLE;
                    scl_oen <= 1'b0;
                    sda_oen <= 1'b0;
                    cmd_ack <= 1'b1;
                end

                S_STOP_A: begin
                    state <= S_STOP_B;
                    scl_oen <= 1'b0;
                    sda_oen <= 1'b0;
                end
                S_STOP_B: begin
                    state <= S_STOP_C;
                    scl_oen <= 1'b1;
                    sda_oen <= 1'b0;
                end
                S_STOP_C: begin
                    state <= S_IDLE;
                    scl_oen <= 1'b1;
                    sda_oen <= 1'b1;
                    cmd_ack <= 1'b1;
                end

                S_WR_A: begin
                    state <= S_WR_B;
                    scl_oen <= 1'b0;
                    sda_oen <= din;
                end
                S_WR_B: begin
                    state <= S_WR_C;
                    scl_oen <= 1'b1;
                    sda_oen <= din;
                end
                S_WR_C: begin
                    state <= S_WR_D;
                    scl_oen <= 1'b1;
                    sda_oen <= din;
                end
                S_WR_D: begin
                    state <= S_IDLE;
                    scl_oen <= 1'b0;
                    sda_oen <= din;
                    cmd_ack <= 1'b1;
                end

                S_RD_A: begin
                    state <= S_RD_B;
                    scl_oen <= 1'b0;
                    sda_oen <= 1'b1;
                end
                S_RD_B: begin
                    state <= S_RD_C;
                    scl_oen <= 1'b1;
                    sda_oen <= 1'b1;
                end
                S_RD_C: begin
                    state <= S_RD_D;
                    scl_oen <= 1'b1;
                    sda_oen <= 1'b1;
                end
                S_RD_D: begin
                    state <= S_IDLE;
                    scl_oen <= 1'b0;
                    sda_oen <= 1'b1;
                    cmd_ack <= 1'b1;
                end

                default: begin
                    state <= S_IDLE;
                    scl_oen <= 1'b1;
                    sda_oen <= 1'b1;
                end
            endcase
        end
    end
end

endmodule