/* verilator lint_off DECLFILENAME */
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
    output cnt_nonzero,
    output cnt_done,
    output core_ack,
    output core_txd,
    output core_rxd,
    output i2c_cmd_start,
    output i2c_cmd_stop,
    output i2c_cmd_read,
    output i2c_cmd_write,
    output core_cmd_is_nop,
    output bit_controller,
    output i2c_master_bit_ctrl,
    output core_cmd,
    output contentreference
);

    localparam [2:0] ST_IDLE  = 3'd0;
    localparam [2:0] ST_START = 3'd1;
    localparam [2:0] ST_READ  = 3'd2;
    localparam [2:0] ST_WRITE = 3'd3;
    localparam [2:0] ST_ACK   = 3'd4;
    localparam [2:0] ST_STOP  = 3'd5;

    localparam [3:0] I2C_CMD_NOP   = 4'b0000;
    localparam [3:0] I2C_CMD_START = 4'b0001;
    localparam [3:0] I2C_CMD_STOP  = 4'b0010;
    localparam [3:0] I2C_CMD_READ  = 4'b0100;
    localparam [3:0] I2C_CMD_WRITE = 4'b1000;

    reg [2:0] state;
    reg [2:0] dcnt;
    reg [7:0] sr;
    reg [3:0] core_cmd_r;

    wire core_ack_w;
    wire core_rxd_w;
    wire core_txd_w;
    wire go_w;
    wire ld_w;
    wire shift_w;

    assign go_w = (read | write | stop) & ~cmd_ack;
    assign ld_w = (state == ST_IDLE) & go_w;
    assign shift_w = ((state == ST_READ) | (state == ST_WRITE)) & core_ack_w;
    assign core_txd_w = (state == ST_ACK) ? ack_in : sr[7];

    assign dout = sr;
    assign st_idle = (state == ST_IDLE);
    assign st_start = (state == ST_START);
    assign st_read = (state == ST_READ);
    assign st_write = (state == ST_WRITE);
    assign st_ack = (state == ST_ACK);
    assign st_stop = (state == ST_STOP);
    assign go = go_w;
    assign ld = ld_w;
    assign shift = shift_w;
    assign cnt_nonzero = (dcnt != 3'b000);
    assign cnt_done = (dcnt == 3'b000);
    assign core_ack = core_ack_w;
    assign core_txd = core_txd_w;
    assign core_rxd = core_rxd_w;

    assign i2c_cmd_start = (core_cmd_r == I2C_CMD_START);
    assign i2c_cmd_stop = (core_cmd_r == I2C_CMD_STOP);
    assign i2c_cmd_read = (core_cmd_r == I2C_CMD_READ);
    assign i2c_cmd_write = (core_cmd_r == I2C_CMD_WRITE);
    assign core_cmd_is_nop = (core_cmd_r == I2C_CMD_NOP);

    assign bit_controller = 1'b1;
    assign i2c_master_bit_ctrl = 1'b1;
    assign core_cmd = 1'b1;
    assign contentreference = 1'b1;

    generate
        if (1) begin : g_bit_ctrl
            i2c_master_bit_ctrl bit_controller (
                .clk(clk),
                .rst(rst),
                .nReset(nReset),
                .ena(ena),
                .clk_cnt(clk_cnt),
                .cmd(core_cmd_r),
                .cmd_ack(core_ack_w),
                .busy(i2c_busy),
                .al(i2c_al),
                .din(core_txd_w),
                .dout(core_rxd_w),
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
            state <= ST_IDLE;
            dcnt <= 3'b000;
            sr <= 8'h00;
            core_cmd_r <= I2C_CMD_NOP;
            cmd_ack <= 1'b0;
            ack_out <= 1'b0;
        end else if (rst | i2c_al) begin
            state <= ST_IDLE;
            dcnt <= 3'b000;
            sr <= 8'h00;
            core_cmd_r <= I2C_CMD_NOP;
            cmd_ack <= 1'b0;
            ack_out <= 1'b0;
        end else begin
            cmd_ack <= 1'b0;

            if (ld_w) begin
                sr <= din;
                dcnt <= 3'd7;
            end else if (shift_w) begin
                sr <= {sr[6:0], core_rxd_w};
                dcnt <= dcnt - 1'b1;
            end

            if ((state == ST_ACK) && core_ack_w)
                ack_out <= core_rxd_w;

            case (state)
                ST_IDLE: begin
                    if (go_w) begin
                        if (start) begin
                            state <= ST_START;
                            core_cmd_r <= I2C_CMD_START;
                        end else if (read) begin
                            state <= ST_READ;
                            core_cmd_r <= I2C_CMD_READ;
                        end else if (write) begin
                            state <= ST_WRITE;
                            core_cmd_r <= I2C_CMD_WRITE;
                        end else begin
                            state <= ST_STOP;
                            core_cmd_r <= I2C_CMD_STOP;
                        end
                    end else begin
                        core_cmd_r <= I2C_CMD_NOP;
                    end
                end

                ST_START: begin
                    if (core_ack_w) begin
                        if (read) begin
                            state <= ST_READ;
                            core_cmd_r <= I2C_CMD_READ;
                        end else begin
                            state <= ST_WRITE;
                            core_cmd_r <= I2C_CMD_WRITE;
                        end
                    end
                end

                ST_READ: begin
                    if (core_ack_w) begin
                        if (dcnt == 3'b000) begin
                            state <= ST_ACK;
                            core_cmd_r <= I2C_CMD_WRITE;
                        end else begin
                            core_cmd_r <= I2C_CMD_READ;
                        end
                    end
                end

                ST_WRITE: begin
                    if (core_ack_w) begin
                        if (dcnt == 3'b000) begin
                            state <= ST_ACK;
                            core_cmd_r <= I2C_CMD_READ;
                        end else begin
                            core_cmd_r <= I2C_CMD_WRITE;
                        end
                    end
                end

                ST_ACK: begin
                    if (core_ack_w) begin
                        if (stop) begin
                            state <= ST_STOP;
                            core_cmd_r <= I2C_CMD_STOP;
                        end else begin
                            state <= ST_IDLE;
                            core_cmd_r <= I2C_CMD_NOP;
                            cmd_ack <= 1'b1;
                        end
                    end
                end

                ST_STOP: begin
                    if (core_ack_w) begin
                        state <= ST_IDLE;
                        core_cmd_r <= I2C_CMD_NOP;
                        cmd_ack <= 1'b1;
                    end
                end

                default: begin
                    state <= ST_IDLE;
                    core_cmd_r <= I2C_CMD_NOP;
                end
            endcase
        end
    end

endmodule

/* Minimal synthesizable stand-in; replace with the project bit controller for
   cycle-accurate I2C timing and bus arbitration behavior. */
module i2c_master_bit_ctrl (
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
    output dout,
    input scl_i,
    output scl_o,
    output scl_oen,
    input sda_i,
    output sda_o,
    output sda_oen
);
    localparam [3:0] I2C_CMD_NOP   = 4'b0000;
    localparam [3:0] I2C_CMD_START = 4'b0001;
    localparam [3:0] I2C_CMD_STOP  = 4'b0010;
    localparam [3:0] I2C_CMD_READ  = 4'b0100;
    localparam [3:0] I2C_CMD_WRITE = 4'b1000;

    reg ready_for_command;

    assign dout = sda_i;
    assign scl_o = 1'b0;
    assign scl_oen = 1'b1;
    assign sda_o = 1'b0;
    assign sda_oen = (cmd == I2C_CMD_START) ? 1'b0 :
                     ((cmd == I2C_CMD_WRITE) ? din : 1'b1);

    always @(posedge clk or negedge nReset) begin
        if (!nReset) begin
            cmd_ack <= 1'b0;
            busy <= 1'b0;
            al <= 1'b0;
            ready_for_command <= 1'b1;
        end else if (rst) begin
            cmd_ack <= 1'b0;
            busy <= 1'b0;
            al <= 1'b0;
            ready_for_command <= 1'b1;
        end else begin
            cmd_ack <= 1'b0;
            al <= 1'b0;

            if (!ena || (cmd == I2C_CMD_NOP)) begin
                ready_for_command <= 1'b1;
            end else if (ready_for_command) begin
                cmd_ack <= 1'b1;
                ready_for_command <= 1'b0;
            end else begin
                ready_for_command <= 1'b1;
            end

            if (cmd == I2C_CMD_START)
                busy <= 1'b1;
            else if (cmd == I2C_CMD_STOP)
                busy <= 1'b0;
        end
    end
endmodule
/* verilator lint_on DECLFILENAME */