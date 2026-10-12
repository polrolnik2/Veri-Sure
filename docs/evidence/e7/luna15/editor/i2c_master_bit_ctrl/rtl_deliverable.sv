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

    localparam [3:0] I2C_CMD_START = 4'b0001;
    localparam [3:0] I2C_CMD_STOP  = 4'b0010;
    localparam [3:0] I2C_CMD_WRITE = 4'b0100;
    localparam [3:0] I2C_CMD_READ  = 4'b1000;

    localparam [4:0] ST_IDLE    = 5'd0,
                     ST_START_A = 5'd1,
                     ST_START_B = 5'd2,
                     ST_START_C = 5'd3,
                     ST_START_D = 5'd4,
                     ST_STOP_A  = 5'd5,
                     ST_STOP_B  = 5'd6,
                     ST_STOP_C  = 5'd7,
                     ST_READ_A  = 5'd8,
                     ST_READ_B  = 5'd9,
                     ST_READ_C  = 5'd10,
                     ST_WRITE_A = 5'd11,
                     ST_WRITE_B = 5'd12,
                     ST_WRITE_C = 5'd13,
                     ST_WRITE_D = 5'd14;

    reg [4:0]  state_r;
    reg [15:0] cnt_r;
    reg        clk_en_r;

    reg [13:0] filter_cnt_r;
    reg [1:0]  cSCL_pipe_r;
    reg [1:0]  cSDA_pipe_r;
    reg [2:0]  fSCL_r;
    reg [2:0]  fSDA_r;
    reg        sSCL_r;
    reg        sSDA_r;
    reg        dSCL_r;
    reg        dSDA_r;
    reg        sda_chk_r;

    wire cnt_zero_i;
    wire filter_cnt_expired_i;
    wire slave_wait_i;
    wire scl_sync_i;
    wire sta_condition_i;
    wire sto_condition_i;
    wire sscl_rise_i;
    wire active_state_i;
    wire stop_state_i;

    assign cnt_zero_i            = (cnt_r == 16'h0000);
    assign filter_cnt_expired_i  = (filter_cnt_r == 14'h0000);
    assign slave_wait_i          = scl_oen && !sSCL_r;
    assign scl_sync_i            = scl_oen && dSCL_r && !sSCL_r;
    assign sta_condition_i       = !sSDA_r && dSDA_r && sSCL_r;
    assign sto_condition_i       = sSDA_r && !dSDA_r && sSCL_r;
    assign sscl_rise_i           = sSCL_r && !dSCL_r;
    assign active_state_i        = (state_r != ST_IDLE);
    assign stop_state_i          = (state_r == ST_STOP_A) ||
                                   (state_r == ST_STOP_B) ||
                                   (state_r == ST_STOP_C);

    assign scl_o = 1'b0;
    assign sda_o = 1'b0;

    assign clk_en             = clk_en_r;
    assign cnt_zero           = cnt_zero_i;
    assign slave_wait         = slave_wait_i;
    assign scl_sync           = scl_sync_i;
    assign cscl               = cSCL_pipe_r[1];
    assign csda               = cSDA_pipe_r[1];
    assign filter_cnt_expired = filter_cnt_expired_i;
    assign fscl               = fSCL_r;
    assign fsda               = fSDA_r;
    assign sscl = sSCL_r;
    assign ssda = sSDA_r;
    assign dscl               = dSCL_r;
    assign dsda               = dSDA_r;
    assign sta_condition      = sta_condition_i;
    assign sto_condition      = sto_condition_i;
    assign sscl_rise          = sscl_rise_i;
    assign sda_chk            = sda_chk_r;
    assign in_idle            = (state_r == ST_IDLE);
    assign fsm_active         = active_state_i;
    assign in_start_sequence  = (state_r == ST_START_A) ||
                                (state_r == ST_START_B) ||
                                (state_r == ST_START_C) ||
                                (state_r == ST_START_D);
    assign in_stop_sequence   = stop_state_i;
    assign in_read_sequence   = (state_r == ST_READ_A) ||
                                (state_r == ST_READ_B) ||
                                (state_r == ST_READ_C);
    assign in_write_sequence  = (state_r == ST_WRITE_A) ||
                                (state_r == ST_WRITE_B) ||
                                (state_r == ST_WRITE_C) ||
                                (state_r == ST_WRITE_D);

    always @(posedge clk or negedge nReset) begin
        if (!nReset)
            filter_cnt_r <= 14'h0000;
        else if (rst)
            filter_cnt_r <= 14'h0000;
        else if (!ena)
            filter_cnt_r <= 14'h0000;
        else if (filter_cnt_expired_i)
            filter_cnt_r <= clk_cnt[15:2];
        else
            filter_cnt_r <= filter_cnt_r - 14'd1;
    end

    always @(posedge clk or negedge nReset) begin
        if (!nReset) begin
            cSCL_pipe_r <= 2'b11;
            cSDA_pipe_r <= 2'b11;
            fSCL_r      <= 3'b111;
            fSDA_r      <= 3'b111;
            sSCL_r      <= 1'b1;
            sSDA_r      <= 1'b1;
            dSCL_r      <= 1'b1;
            dSDA_r      <= 1'b1;
        end else if (rst) begin
            cSCL_pipe_r <= 2'b11;
            cSDA_pipe_r <= 2'b11;
            fSCL_r      <= 3'b111;
            fSDA_r      <= 3'b111;
            sSCL_r      <= 1'b1;
            sSDA_r      <= 1'b1;
            dSCL_r      <= 1'b1;
            dSDA_r      <= 1'b1;
        end else begin
            cSCL_pipe_r <= {cSCL_pipe_r[0], scl_i};
            cSDA_pipe_r <= {cSDA_pipe_r[0], sda_i};
            if (ena && filter_cnt_expired_i) begin
                fSCL_r <= {fSCL_r[1:0], cSCL_pipe_r[1]};
                fSDA_r <= {fSDA_r[1:0], cSDA_pipe_r[1]};
                sSCL_r <= (fSCL_r[1] & fSCL_r[0]) |
                          (fSCL_r[1] & cSCL_pipe_r[1]) |
                          (fSCL_r[0] & cSCL_pipe_r[1]);
                sSDA_r <= (fSDA_r[1] & fSDA_r[0]) |
                          (fSDA_r[1] & cSDA_pipe_r[1]) |
                          (fSDA_r[0] & cSDA_pipe_r[1]);
            end else begin
                sSCL_r <= (fSCL_r[2] & fSCL_r[1]) |
                          (fSCL_r[2] & fSCL_r[0]) |
                          (fSCL_r[1] & fSCL_r[0]);
                sSDA_r <= (fSDA_r[2] & fSDA_r[1]) |
                          (fSDA_r[2] & fSDA_r[0]) |
                          (fSDA_r[1] & fSDA_r[0]);
            end
            dSCL_r <= sSCL_r;
            dSDA_r <= sSDA_r;
        end
    end

    always @(posedge clk or negedge nReset) begin
        if (!nReset) begin
            cnt_r    <= 16'h0000;
            clk_en_r <= 1'b1;
        end else if (rst) begin
            cnt_r    <= 16'h0000;
            clk_en_r <= 1'b1;
        end else if (!ena) begin
            cnt_r    <= clk_cnt;
            clk_en_r <= 1'b1;
        end else if (scl_sync_i) begin
            cnt_r    <= clk_cnt;
            clk_en_r <= 1'b1;
        end else if (slave_wait_i) begin
            cnt_r    <= cnt_r;
            clk_en_r <= 1'b0;
        end else if (cnt_zero_i) begin
            cnt_r    <= clk_cnt;
            clk_en_r <= 1'b1;
        end else begin
            cnt_r    <= cnt_r - 16'd1;
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
        end else if (sda_chk_r && sda_oen && !ssda) begin
            al <= 1'b1;
        end else if (sto_condition_i && active_state_i && !stop_state_i) begin
            al <= 1'b1;
        end else if (sta_condition_i) begin
            al <= 1'b0;
        end
    end

    always @(posedge clk or negedge nReset) begin
        if (!nReset) begin
            dout <= 1'b0;
        end else if (rst) begin
            dout <= 1'b0;
        end else if (sscl_rise_i) begin
            dout <= sSDA_r;
        end
    end

    always @(posedge clk or negedge nReset) begin
        if (!nReset) begin
            state_r   <= ST_IDLE;
            cmd_ack   <= 1'b0;
            scl_oen   <= 1'b1;
            sda_oen   <= 1'b1;
            sda_chk_r <= 1'b0;
        end else if (rst) begin
            state_r   <= ST_IDLE;
            cmd_ack   <= 1'b0;
            scl_oen   <= 1'b1;
            sda_oen   <= 1'b1;
            sda_chk_r <= 1'b0;
        end else begin
            cmd_ack <= 1'b0;

            if (al) begin
                state_r   <= ST_IDLE;
                scl_oen   <= 1'b1;
                sda_oen   <= 1'b1;
                sda_chk_r <= 1'b0;
            end else if (ena && clk_en_r && !slave_wait_i) begin
                case (state_r)
                    ST_IDLE: begin
                        sda_chk_r <= 1'b0;
                        case (cmd)
                            I2C_CMD_START: state_r <= ST_START_A;
                            I2C_CMD_STOP:  state_r <= ST_STOP_A;
                            I2C_CMD_READ:  state_r <= ST_READ_A;
                            I2C_CMD_WRITE: state_r <= ST_WRITE_A;
                            default:       state_r <= ST_IDLE;
                        endcase
                    end
                    ST_START_A: begin state_r <= ST_START_B; scl_oen <= 1'b1; sda_oen <= 1'b1; end
                    ST_START_B: state_r <= ST_START_C;
                    ST_START_C: begin state_r <= ST_START_D; sda_oen <= 1'b0; end
                    ST_START_D: begin state_r <= ST_IDLE; scl_oen <= 1'b0; cmd_ack <= 1'b1; end
                    ST_STOP_A: begin state_r <= ST_STOP_B; scl_oen <= 1'b0; sda_oen <= 1'b0; end
                    ST_STOP_B: begin
                        if (!scl_oen) begin
                            scl_oen <= 1'b1;
                        end else begin
                            state_r <= ST_STOP_C;
                        end
                    end
                    ST_STOP_C: begin state_r <= ST_IDLE; sda_oen <= 1'b1; cmd_ack <= 1'b1; end
                    ST_READ_A: begin state_r <= ST_READ_B; scl_oen <= 1'b0; sda_oen <= 1'b1; sda_chk_r <= 1'b0; end
                    ST_READ_B: begin state_r <= ST_READ_C; scl_oen <= 1'b1; end
                    ST_READ_C: begin state_r <= ST_IDLE; scl_oen <= 1'b0; cmd_ack <= 1'b1; end
                    ST_WRITE_A: begin state_r <= ST_WRITE_B; scl_oen <= 1'b0; sda_oen <= din; sda_chk_r <= 1'b0; end
                    ST_WRITE_B: begin state_r <= ST_WRITE_C; scl_oen <= 1'b1; end
                    ST_WRITE_C: begin state_r <= ST_WRITE_D; sda_chk_r <= 1'b1; end
                    ST_WRITE_D: begin state_r <= ST_IDLE; scl_oen <= 1'b0; sda_chk_r <= 1'b0; cmd_ack <= 1'b1; end
                    default: begin state_r <= ST_IDLE; scl_oen <= 1'b1; sda_oen <= 1'b1; sda_chk_r <= 1'b0; end
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
