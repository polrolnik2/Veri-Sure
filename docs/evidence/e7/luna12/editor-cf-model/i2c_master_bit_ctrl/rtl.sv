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

    output            cnt_zero,
    output            cnt_reload,
    output            clk_en,
    output            slave_wait,
    output            scl_sync,
    output            cscl,
    output            csda,
    output            dscl,
    output            sta_condition,
    output            sto_condition,
    output            sda_chk,
    output            fsm_active,
    output            in_start_sequence,
    output            in_stop_sequence,
    output            in_read_sequence,
    output            in_write_sequence
);

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
    localparam [3:0] ST_WRITE_A = 4'd11;
    localparam [3:0] ST_WRITE_B = 4'd12;
    localparam [3:0] ST_WRITE_C = 4'd13;
    localparam [3:0] ST_WRITE_D = 4'd14;

    reg [15:0] cnt_r;
    reg        clk_en_r;
    reg [13:0] filter_cnt_r;
    reg        cSCL_r;
    reg        cSDA_r;
    reg [2:0]  fSCL_r;
    reg [2:0]  fSDA_r;
    reg        dSCL_r;
    reg        dSDA_r;
    reg [3:0]  state_r;
    reg        sda_chk_r;

    wire sSCL_r;
    wire sSDA_r;
    wire slave_wait_r;
    wire scl_sync_r;
    wire sta_condition_r;
    wire sto_condition_r;
    wire cnt_reload_r;

    assign sSCL_r = (fSCL_r[2] & fSCL_r[1]) |
                    (fSCL_r[1] & fSCL_r[0]) |
                    (fSCL_r[2] & fSCL_r[0]);
    assign sSDA_r = (fSDA_r[2] & fSDA_r[1]) |
                    (fSDA_r[1] & fSDA_r[0]) |
                    (fSDA_r[2] & fSDA_r[0]);

    assign slave_wait_r    = scl_oen & ~sSCL_r;
    assign scl_sync_r      = dSCL_r & ~sSCL_r & scl_oen;
    assign sta_condition_r = ~sSDA_r & dSDA_r & sSCL_r;
    assign sto_condition_r = sSDA_r & ~dSDA_r & sSCL_r;
    assign cnt_reload_r    = !ena || (cnt_r == 16'h0000) || scl_sync_r;

    assign scl_o = 1'b0;
    assign sda_o = 1'b0;

    assign cnt_zero         = (cnt_r == 16'h0000);
    assign cnt_reload       = cnt_reload_r;
    assign clk_en           = clk_en_r;
    assign slave_wait       = slave_wait_r;
    assign scl_sync         = scl_sync_r;
    assign cscl             = cSCL_r;
    assign csda             = cSDA_r;
    assign dscl             = dSCL_r;
    assign sta_condition    = sta_condition_r;
    assign sto_condition    = sto_condition_r;
    assign sda_chk          = sda_chk_r;
    assign fsm_active       = (state_r != ST_IDLE);
    assign in_start_sequence =
        (state_r == ST_START_A) || (state_r == ST_START_B) ||
        (state_r == ST_START_C) || (state_r == ST_START_D);
    assign in_stop_sequence =
        (state_r == ST_STOP_A) || (state_r == ST_STOP_B) ||
        (state_r == ST_STOP_C);
    assign in_read_sequence =
        (state_r == ST_READ_A) || (state_r == ST_READ_B) ||
        (state_r == ST_READ_C);
    assign in_write_sequence =
        (state_r == ST_WRITE_A) || (state_r == ST_WRITE_B) ||
        (state_r == ST_WRITE_C) || (state_r == ST_WRITE_D);

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
            filter_cnt_r <= 14'b0;
            fSCL_r       <= 3'b111;
            fSDA_r       <= 3'b111;
        end else if (rst) begin
            filter_cnt_r <= 14'b0;
            fSCL_r       <= 3'b111;
            fSDA_r       <= 3'b111;
        end else if (!ena) begin
            filter_cnt_r <= 14'b0;
        end else if (filter_cnt_r == 14'b0) begin
            filter_cnt_r <= clk_cnt[15:2];
            fSCL_r       <= {fSCL_r[1:0], cSCL_r};
            fSDA_r       <= {fSDA_r[1:0], cSDA_r};
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
            dSCL_r <= sSCL_r;
            dSDA_r <= sSDA_r;
        end
    end

    always @(posedge clk or negedge nReset) begin
        if (!nReset) begin
            cnt_r    <= 16'h0000;
            clk_en_r <= 1'b0;
        end else if (rst) begin
            cnt_r    <= 16'h0000;
            clk_en_r <= 1'b0;
        end else if (!ena) begin
            cnt_r    <= clk_cnt;
            clk_en_r <= 1'b1;
        end else if (scl_sync_r) begin
            cnt_r    <= clk_cnt;
            clk_en_r <= 1'b1;
        end else if (slave_wait_r) begin
            cnt_r    <= cnt_r;
            clk_en_r <= 1'b0;
        end else if (cnt_r == 16'h0000) begin
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
        end else if (sta_condition_r) begin
            busy <= 1'b1;
        end else if (sto_condition_r) begin
            busy <= 1'b0;
        end
    end

    always @(posedge clk or negedge nReset) begin
        if (!nReset) begin
            dout <= 1'b0;
        end else if (rst) begin
            dout <= 1'b0;
        end else if (sSCL_r && !dSCL_r) begin
            dout <= sSDA_r;
        end
    end

    always @(posedge clk or negedge nReset) begin
        if (!nReset) begin
            state_r   <= ST_IDLE;
            cmd_ack   <= 1'b0;
            al        <= 1'b0;
            scl_oen   <= 1'b1;
            sda_oen   <= 1'b1;
            sda_chk_r <= 1'b0;
        end else if (rst) begin
            state_r   <= ST_IDLE;
            cmd_ack   <= 1'b0;
            al        <= 1'b0;
            scl_oen   <= 1'b1;
            sda_oen   <= 1'b1;
            sda_chk_r <= 1'b0;
        end else begin
            cmd_ack <= 1'b0;
            if ((sda_chk_r && sda_oen && !sSDA_r) ||
                ((state_r != ST_IDLE) &&
                 (state_r != ST_STOP_A) &&
                 (state_r != ST_STOP_B) &&
                 (state_r != ST_STOP_C) && sto_condition_r)) begin
                al        <= 1'b1;
                state_r   <= ST_IDLE;
                scl_oen   <= 1'b1;
                sda_oen   <= 1'b1;
                sda_chk_r <= 1'b0;
            end else if (al) begin
                state_r   <= ST_IDLE;
                scl_oen   <= 1'b1;
                sda_oen   <= 1'b1;
                sda_chk_r <= 1'b0;
            end else if (ena && clk_en_r && !slave_wait_r && !scl_sync_r) begin
                case (state_r)
                    ST_IDLE: begin
                        sda_chk_r <= 1'b0;
                        case (cmd)
                            I2C_CMD_START: begin state_r <= ST_START_A; scl_oen <= 1'b1; sda_oen <= 1'b1; end
                            I2C_CMD_STOP:  begin state_r <= ST_STOP_A; scl_oen <= 1'b0; sda_oen <= 1'b0; end
                            I2C_CMD_READ:  begin state_r <= ST_READ_A; scl_oen <= 1'b0; sda_oen <= 1'b1; end
                            I2C_CMD_WRITE: begin state_r <= ST_WRITE_A; scl_oen <= 1'b0; sda_oen <= din; end
                            default: state_r <= ST_IDLE;
                        endcase
                    end
                    ST_START_A: begin scl_oen <= 1'b1; sda_oen <= 1'b1; state_r <= ST_START_B; end
                    ST_START_B: begin scl_oen <= 1'b1; sda_oen <= 1'b1; state_r <= ST_START_C; end
                    ST_START_C: begin scl_oen <= 1'b1; sda_oen <= 1'b0; state_r <= ST_START_D; end
                    ST_START_D: begin scl_oen <= 1'b0; sda_oen <= 1'b0; state_r <= ST_IDLE; cmd_ack <= 1'b1; end
                    ST_STOP_A: begin scl_oen <= 1'b0; sda_oen <= 1'b0; state_r <= ST_STOP_B; end
                    ST_STOP_B: begin scl_oen <= 1'b1; sda_oen <= 1'b0; state_r <= ST_STOP_C; end
                    ST_STOP_C: begin scl_oen <= 1'b1; sda_oen <= 1'b1; state_r <= ST_IDLE; cmd_ack <= 1'b1; end
                    ST_READ_A: begin scl_oen <= 1'b0; sda_oen <= 1'b1; state_r <= ST_READ_B; end
                    ST_READ_B: begin scl_oen <= 1'b1; sda_oen <= 1'b1; state_r <= ST_READ_C; end
                    ST_READ_C: begin scl_oen <= 1'b0; sda_oen <= 1'b1; state_r <= ST_IDLE; cmd_ack <= 1'b1; end
                    ST_WRITE_A: begin scl_oen <= 1'b0; sda_oen <= din; state_r <= ST_WRITE_B; end
                    ST_WRITE_B: begin scl_oen <= 1'b1; sda_oen <= din; state_r <= ST_WRITE_C; end
                    ST_WRITE_C: begin scl_oen <= 1'b1; sda_oen <= din; sda_chk_r <= din; state_r <= ST_WRITE_D; end
                    ST_WRITE_D: begin scl_oen <= 1'b0; sda_oen <= din; sda_chk_r <= 1'b0; state_r <= ST_IDLE; cmd_ack <= 1'b1; end
                    default: state_r <= ST_IDLE;
                endcase
            end
        end
    end

endmodule