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
    output               scl_o,
    output reg        scl_oen,
    output               sda_o,
    output reg        sda_oen,

    output               clk_en,
    output               cnt_zero,
    output               slave_wait,
    output               scl_sync,
    output               cscl,
    output               csda,
    output               filter_cnt_expired,
    output      [2:0]    fscl,
    output      [2:0]    fsda,
    output               sscl,
    output               ssda,
    output               dscl,
    output               dsda,
    output               sta_condition,
    output               sto_condition,
    output               sscl_rise,
    output               sda_chk,
    output               in_idle,
    output               fsm_active,
    output               in_start_sequence,
    output               in_stop_sequence,
    output               in_read_sequence,
    output               in_write_sequence
);

    localparam [3:0] I2C_CMD_START = 4'b0001;
    localparam [3:0] I2C_CMD_STOP  = 4'b0010;
    localparam [3:0] I2C_CMD_WRITE = 4'b0100;
    localparam [3:0] I2C_CMD_READ  = 4'b1000;

    localparam [3:0] S_IDLE   = 4'h0,
                     S_STA_A  = 4'h1,
                     S_STA_B  = 4'h2,
                     S_STA_C  = 4'h3,
                     S_STA_D  = 4'h4,
                     S_STO_A  = 4'h5,
                     S_STO_B  = 4'h6,
                     S_STO_C  = 4'h7,
                     S_STO_D  = 4'h8,
                     S_RD_A   = 4'h9,
                     S_RD_B   = 4'hA,
                     S_RD_C   = 4'hB,
                     S_WR_A   = 4'hC,
                     S_WR_B   = 4'hD,
                     S_WR_C   = 4'hE;

    reg [3:0] state;

    reg [15:0] cnt;
    reg        clk_en_r;

    reg [15:0] filter_cnt;
    reg [2:0]  fSCL_r;
    reg [2:0]  fSDA_r;

    reg cSCL_meta;
    reg cSDA_meta;
    reg cSCL_r;
    reg cSDA_r;

    reg dSCL_r;
    reg dSDA_r;
    reg sda_chk_r;

    wire cnt_zero_r;
    wire filter_cnt_expired_r;
    wire sSCL_r;
    wire sSDA_r;
    wire slave_wait_r;
    wire scl_sync_r;
    wire sta_condition_r;
    wire sto_condition_r;
    wire sscl_rise_r;
    wire in_stop_seq_r;
    wire unexpected_stop_r;
    wire arb_lost_now;

    assign cnt_zero_r           = (cnt == 16'h0000);
    assign filter_cnt_expired_r = (filter_cnt == 16'h0000);

    assign sSCL_r = (fSCL_r[2] & fSCL_r[1]) |
                    (fSCL_r[2] & fSCL_r[0]) |
                    (fSCL_r[1] & fSCL_r[0]);
    assign sSDA_r = (fSDA_r[2] & fSDA_r[1]) |
                    (fSDA_r[2] & fSDA_r[0]) |
                    (fSDA_r[1] & fSDA_r[0]);

    assign slave_wait_r = scl_oen & ~sSCL_r;
    assign scl_sync_r   = dSCL_r & ~sSCL_r & scl_oen;
    assign sta_condition_r = ~sSDA_r & dSDA_r & sSCL_r;
    assign sto_condition_r = sSDA_r & ~dSDA_r & sSCL_r;
    assign sscl_rise_r = sSCL_r & ~dSCL_r;

    assign in_stop_seq_r = (state == S_STO_A) |
                           (state == S_STO_B) |
                           (state == S_STO_C) |
                           (state == S_STO_D);
    assign unexpected_stop_r = sto_condition_r &
                               (state != S_IDLE) &
                               ~in_stop_seq_r;
    assign arb_lost_now = (sda_chk_r & ~sSDA_r) | unexpected_stop_r;

    assign scl_o = 1'b0;
    assign sda_o = 1'b0;

    assign clk_en             = clk_en_r;
    assign cnt_zero           = cnt_zero_r;
    assign slave_wait         = slave_wait_r;
    assign scl_sync           = scl_sync_r;
    assign cscl               = cSCL_r;
    assign csda               = cSDA_r;
    assign filter_cnt_expired = filter_cnt_expired_r;
    assign fscl               = fSCL_r;
    assign fsda               = fSDA_r;
    assign sscl               = sSCL_r;
    assign ssda               = sSDA_r;
    assign dscl               = dSCL_r;
    assign dsda               = dSDA_r;
    assign sta_condition      = sta_condition_r;
    assign sto_condition      = sto_condition_r;
    assign sscl_rise          = sscl_rise_r;
    assign sda_chk            = sda_chk_r;

    assign in_idle = (state == S_IDLE);
    assign fsm_active = (state != S_IDLE);
    assign in_start_sequence = (state == S_STA_A) |
                               (state == S_STA_B) |
                               (state == S_STA_C) |
                               (state == S_STA_D);
    assign in_stop_sequence = in_stop_seq_r;
    assign in_read_sequence = (state == S_RD_A) |
                              (state == S_RD_B) |
                              (state == S_RD_C);
    assign in_write_sequence = (state == S_WR_A) |
                               (state == S_WR_B) |
                               (state == S_WR_C);

    always @(posedge clk or negedge nReset) begin
        if (!nReset) begin
            cnt       <= 16'h0000;
            clk_en_r  <= 1'b1;
        end else if (rst) begin
            cnt       <= clk_cnt;
            clk_en_r  <= 1'b1;
        end else if (!ena) begin
            cnt       <= clk_cnt;
            clk_en_r  <= 1'b1;
        end else if (cnt_zero_r | scl_sync_r) begin
            cnt       <= clk_cnt;
            clk_en_r  <= 1'b1;
        end else if (slave_wait_r) begin
            cnt       <= cnt;
            clk_en_r  <= 1'b0;
        end else begin
            cnt       <= cnt - 16'h0001;
            clk_en_r  <= 1'b0;
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
        end else if (filter_cnt_expired_r) begin
            filter_cnt <= clk_cnt >> 2;
            fSCL_r     <= {fSCL_r[1:0], cSCL_r};
            fSDA_r     <= {fSDA_r[1:0], cSDA_r};
        end else begin
            filter_cnt <= filter_cnt - 16'h0001;
        end
    end

    always @(posedge clk or negedge nReset) begin
        if (!nReset) begin
            cSCL_meta <= 1'b1;
            cSDA_meta <= 1'b1;
            cSCL_r    <= 1'b1;
            cSDA_r    <= 1'b1;
        end else if (rst) begin
            cSCL_meta <= 1'b1;
            cSDA_meta <= 1'b1;
            cSCL_r    <= 1'b1;
            cSDA_r    <= 1'b1;
        end else begin
            cSCL_meta <= scl_i;
            cSDA_meta <= sda_i;
            cSCL_r    <= cSCL_meta;
            cSDA_r    <= cSDA_meta;
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
            dSCL_r <= sSCL_r;
            dSDA_r <= sSDA_r;
            if (sscl_rise_r)
                dout <= sSDA_r;
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
            al <= 1'b0;
        end else if (rst) begin
            al <= 1'b0;
        end else if (arb_lost_now) begin
            al <= 1'b1;
        end else if (clk_en_r & (state == S_IDLE)) begin
            al <= 1'b0;
        end
    end

    always @(posedge clk or negedge nReset) begin
        if (!nReset) begin
            state    <= S_IDLE;
            cmd_ack  <= 1'b0;
            scl_oen  <= 1'b1;
            sda_oen  <= 1'b1;
            sda_chk_r <= 1'b0;
        end else if (rst) begin
            state    <= S_IDLE;
            cmd_ack  <= 1'b0;
            scl_oen  <= 1'b1;
            sda_oen  <= 1'b1;
            sda_chk_r <= 1'b0;
        end else begin
            cmd_ack <= 1'b0;

            if (al | arb_lost_now) begin
                state     <= S_IDLE;
                scl_oen   <= 1'b1;
                sda_oen   <= 1'b1;
                sda_chk_r <= 1'b0;
            end else if (ena & clk_en_r) begin
                case (state)
                    S_IDLE: begin
                        case (cmd)
                            I2C_CMD_START: state <= S_STA_A;
                            I2C_CMD_STOP:  state <= S_STO_A;
                            I2C_CMD_READ:  state <= S_RD_A;
                            I2C_CMD_WRITE: state <= S_WR_A;
                            default:       state <= S_IDLE;
                        endcase
                    end

                    S_STA_A: begin
                        state   <= S_STA_B;
                        scl_oen <= 1'b1;
                        sda_oen <= 1'b1;
                    end
                    S_STA_B: begin
                        state   <= S_STA_C;
                        sda_oen <= 1'b0;
                    end
                    S_STA_C: begin
                        state   <= S_STA_D;
                        scl_oen <= 1'b0;
                    end
                    S_STA_D: begin
                        state   <= S_IDLE;
                        cmd_ack <= 1'b1;
                    end

                    S_STO_A: begin
                        state   <= S_STO_B;
                        scl_oen <= 1'b0;
                        sda_oen <= 1'b0;
                    end
                    S_STO_B: begin
                        state   <= S_STO_C;
                        scl_oen <= 1'b1;
                    end
                    S_STO_C: begin
                        state   <= S_STO_D;
                        sda_oen <= 1'b1;
                    end
                    S_STO_D: begin
                        state   <= S_IDLE;
                        cmd_ack <= 1'b1;
                    end

                    S_RD_A: begin
                        state   <= S_RD_B;
                        scl_oen <= 1'b0;
                        sda_oen <= 1'b1;
                    end
                    S_RD_B: begin
                        state   <= S_RD_C;
                        scl_oen <= 1'b1;
                    end
                    S_RD_C: begin
                        state   <= S_IDLE;
                        scl_oen <= 1'b0;
                        cmd_ack <= 1'b1;
                    end

                    S_WR_A: begin
                        state   <= S_WR_B;
                        scl_oen <= 1'b0;
                        sda_oen <= din;
                    end
                    S_WR_B: begin
                        state     <= S_WR_C;
                        scl_oen   <= 1'b1;
                        sda_chk_r <= 1'b1;
                    end
                    S_WR_C: begin
                        state     <= S_IDLE;
                        scl_oen   <= 1'b0;
                        sda_chk_r <= 1'b0;
                        cmd_ack   <= 1'b1;
                    end

                    default: begin
                        state <= S_IDLE;
                    end
                endcase
            end
        end
    end

endmodule