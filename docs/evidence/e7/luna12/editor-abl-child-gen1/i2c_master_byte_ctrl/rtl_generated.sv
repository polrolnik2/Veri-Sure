module i2c_master_byte_ctrl (
    input clk,
    input rst,
    input nReset,
    input ena,
    input [15:0] clk_cnt,
    input start,
    input stop,
    input read,
    input write,
    input ack_in,
    input [7:0] din,
    output reg cmd_ack,
    output reg ack_out,
    output [7:0] dout,
    output i2c_busy,
    output i2c_al,
    input scl_i,
    output scl_o,
    output scl_oen,
    input sda_i,
    output sda_o,
    output sda_oen,
    output st_idle,
    output st_start,
    output st_read,
    output st_write,
    output st_ack,
    output st_stop,
    output go,
    output ld,
    output shift,
    output dcnt_nonzero,
    output cnt_done,
    output core_ack,
    output core_rxd,
    output core_txd,
    output core_cmd_start,
    output core_cmd_read,
    output core_cmd_write,
    output core_cmd_stop,
    output core_cmd_nop,
    output core_cmd,
    output bit_controller,
    output i2c_master_bit_ctrl,
    output contentreference
);

    localparam [2:0] ST_IDLE  = 3'd0,
                     ST_START = 3'd1,
                     ST_READ  = 3'd2,
                     ST_WRITE = 3'd3,
                     ST_ACK   = 3'd4,
                     ST_STOP  = 3'd5;

    localparam [3:0] I2C_CMD_NOP   = 4'b0000,
                     I2C_CMD_START = 4'b0001,
                     I2C_CMD_STOP  = 4'b0010,
                     I2C_CMD_READ  = 4'b0100,
                     I2C_CMD_WRITE = 4'b1000;

    reg [2:0] state_r;
    reg [2:0] dcnt_r;
    reg [7:0] sr_r;
    reg [3:0] core_cmd_r;
    reg ld_r;
    reg shift_r;
    reg core_txd_r;

    wire go_i;
    wire cnt_done_i;
    wire core_ack_i;
    wire core_rxd_i;

    assign go_i = (read | write | stop) & ~cmd_ack;
    assign cnt_done_i = (dcnt_r == 3'd0);

    assign go = go_i;
    assign ld = ld_r;
    assign shift = shift_r;
    assign dcnt_nonzero = (dcnt_r != 3'd0);
    assign cnt_done = cnt_done_i;

    assign core_ack = core_ack_i;
    assign core_rxd = core_rxd_i;
    assign core_txd = core_txd_r;

    assign dout = sr_r;

    assign st_idle  = (state_r == ST_IDLE);
    assign st_start = (state_r == ST_START);
    assign st_read  = (state_r == ST_READ);
    assign st_write = (state_r == ST_WRITE);
    assign st_ack   = (state_r == ST_ACK);
    assign st_stop  = (state_r == ST_STOP);

    assign core_cmd_start = (core_cmd_r == I2C_CMD_START);
    assign core_cmd_read  = (core_cmd_r == I2C_CMD_READ);
    assign core_cmd_write = (core_cmd_r == I2C_CMD_WRITE);
    assign core_cmd_stop  = (core_cmd_r == I2C_CMD_STOP);
    assign core_cmd_nop   = (core_cmd_r == I2C_CMD_NOP);
    assign core_cmd       = (core_cmd_r != I2C_CMD_NOP);

    assign bit_controller = 1'b1;
    assign i2c_master_bit_ctrl = 1'b1;
    assign contentreference = 1'b1;

    generate
        if (1'b1) begin : g_bit_controller
            i2c_master_bit_ctrl bit_controller (
                .clk(clk),
                .rst(rst),
                .nReset(nReset),
                .ena(ena),
                .clk_cnt(clk_cnt),
                .cmd(core_cmd_r),
                .cmd_ack(core_ack_i),
                .busy(i2c_busy),
                .al(i2c_al),
                .din(core_txd_r),
                .dout(core_rxd_i),
                .scl_i(scl_i),
                .scl_o(scl_o),
                .scl_oen(scl_oen),
                .sda_i(sda_i),
                .sda_o(sda_o),
                .sda_oen(sda_oen)
            );
        end
    endgenerate

    always @(posedge clk or negedge nReset) begin
        if (!nReset) begin
            state_r    <= ST_IDLE;
            dcnt_r     <= 3'd0;
            sr_r       <= 8'd0;
            core_cmd_r <= I2C_CMD_NOP;
            core_txd_r <= 1'b0;
            ld_r       <= 1'b0;
            shift_r    <= 1'b0;
            cmd_ack    <= 1'b0;
            ack_out    <= 1'b0;
        end else if (rst | i2c_al) begin
            state_r    <= ST_IDLE;
            dcnt_r     <= 3'd0;
            sr_r       <= 8'd0;
            core_cmd_r <= I2C_CMD_NOP;
            core_txd_r <= 1'b0;
            ld_r       <= 1'b0;
            shift_r    <= 1'b0;
            cmd_ack    <= 1'b0;
            ack_out    <= 1'b0;
        end else begin
            cmd_ack <= 1'b0;
            ld_r    <= 1'b0;
            shift_r <= 1'b0;

            if (ld_r)
                sr_r <= din;
            else if (shift_r)
                sr_r <= {sr_r[6:0], core_rxd_i};

            if (ld_r)
                dcnt_r <= 3'd7;
            else if (shift_r)
                dcnt_r <= dcnt_r - 3'd1;

            if ((state_r == ST_ACK) && (core_cmd_r == I2C_CMD_WRITE))
                core_txd_r <= ack_in;
            else
                core_txd_r <= sr_r[7];

            case (state_r)
                ST_IDLE: begin
                    if (go_i) begin
                        ld_r <= 1'b1;
                        if (start) begin
                            state_r    <= ST_START;
                            core_cmd_r <= I2C_CMD_START;
                        end else if (read) begin
                            state_r    <= ST_READ;
                            core_cmd_r <= I2C_CMD_READ;
                        end else if (write) begin
                            state_r    <= ST_WRITE;
                            core_cmd_r <= I2C_CMD_WRITE;
                        end else begin
                            state_r    <= ST_STOP;
                            core_cmd_r <= I2C_CMD_STOP;
                        end
                    end
                end

                ST_START: begin
                    if (core_ack_i) begin
                        if (read) begin
                            state_r    <= ST_READ;
                            core_cmd_r <= I2C_CMD_READ;
                        end else begin
                            state_r    <= ST_WRITE;
                            core_cmd_r <= I2C_CMD_WRITE;
                        end
                    end
                end

                ST_READ: begin
                    if (core_ack_i) begin
                        shift_r <= 1'b1;
                        if (cnt_done_i) begin
                            state_r    <= ST_ACK;
                            core_cmd_r <= I2C_CMD_WRITE;
                            core_txd_r <= ack_in;
                        end else begin
                            core_cmd_r <= I2C_CMD_READ;
                        end
                    end
                end

                ST_WRITE: begin
                    if (core_ack_i) begin
                        if (cnt_done_i) begin
                            state_r    <= ST_ACK;
                            core_cmd_r <= I2C_CMD_READ;
                        end else begin
                            shift_r    <= 1'b1;
                            core_cmd_r <= I2C_CMD_WRITE;
                        end
                    end
                end

                ST_ACK: begin
                    if (core_ack_i) begin
                        ack_out <= core_rxd_i;
                        if (stop) begin
                            state_r    <= ST_STOP;
                            core_cmd_r <= I2C_CMD_STOP;
                        end else begin
                            state_r    <= ST_IDLE;
                            core_cmd_r <= I2C_CMD_NOP;
                            cmd_ack    <= 1'b1;
                        end
                    end
                end

                ST_STOP: begin
                    if (core_ack_i) begin
                        state_r    <= ST_IDLE;
                        core_cmd_r <= I2C_CMD_NOP;
                        cmd_ack    <= 1'b1;
                    end
                end

                default: begin
                    state_r    <= ST_IDLE;
                    core_cmd_r <= I2C_CMD_NOP;
                end
            endcase
        end
    end

endmodule