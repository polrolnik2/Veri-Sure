module i2c_master_byte_ctrl__probed (
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

    localparam [2:0] ST_IDLE  = 3'd0,
                     ST_START = 3'd1,
                     ST_READ  = 3'd2,
                     ST_WRITE = 3'd3,
                     ST_ACK   = 3'd4,
                     ST_STOP  = 3'd5;

    localparam [2:0] I2C_CMD_NOP   = 3'b000,
                     I2C_CMD_START = 3'b001,
                     I2C_CMD_STOP  = 3'b010,
                     I2C_CMD_READ  = 3'b100,
                     I2C_CMD_WRITE = 3'b101;

    reg [2:0] state;
    reg [2:0] core_cmd_r;
    reg [7:0] sr;
    reg [2:0] dcnt;
    reg ld_r;
    reg shift_r;

    wire core_ack_r;
    wire core_txd_r;
    wire core_rxd_r;
    wire go_r;
    wire cnt_nonzero_r;
    wire cnt_done_r;

    assign go_r = (read | write | stop) & ~cmd_ack;
    assign cnt_nonzero_r = |dcnt;
    assign cnt_done_r = (dcnt == 3'b000);

    assign st_idle  = (state == ST_IDLE);
    assign st_start = (state == ST_START);
    assign st_read  = (state == ST_READ);
    assign st_write = (state == ST_WRITE);
    assign st_ack   = (state == ST_ACK);
    assign st_stop  = (state == ST_STOP);

    assign go = go_r;
    assign ld = ld_r;
    assign shift = shift_r;
    assign cnt_nonzero = cnt_nonzero_r;
    assign cnt_done = cnt_done_r;
    assign core_ack = core_ack_r;
    assign core_txd = core_txd_r;
    assign core_rxd = core_rxd_r;

    assign i2c_cmd_start = (core_cmd_r == I2C_CMD_START);
    assign i2c_cmd_stop  = (core_cmd_r == I2C_CMD_STOP);
    assign i2c_cmd_read  = (core_cmd_r == I2C_CMD_READ);
    assign i2c_cmd_write = (core_cmd_r == I2C_CMD_WRITE);
    assign core_cmd_is_nop = (core_cmd_r == I2C_CMD_NOP);
    assign core_cmd = 1'b1;
    assign bit_controller = 1'b1;
    assign i2c_master_bit_ctrl = 1'b1;
    assign contentreference = 1'b1;

    assign dout = sr;
    assign core_txd_r = (state == ST_ACK) ? ack_in : sr[7];

    always @(posedge clk or negedge nReset) begin
        if (!nReset) begin
            sr   <= 8'h00;
            dcnt <= 3'b000;
        end else if (rst) begin
            sr   <= 8'h00;
            dcnt <= 3'b000;
        end else begin
            if (ld_r) begin
                sr   <= din;
                dcnt <= 3'd7;
            end else if (shift_r) begin
                sr   <= {sr[6:0], core_rxd_r};
                dcnt <= dcnt - 3'd1;
            end
        end
    end

    always @(posedge clk or negedge nReset) begin
        if (!nReset) begin
            state     <= ST_IDLE;
            core_cmd_r <= I2C_CMD_NOP;
            ld_r      <= 1'b0;
            shift_r   <= 1'b0;
            cmd_ack   <= 1'b0;
            ack_out   <= 1'b0;
        end else if (rst || i2c_al) begin
            state     <= ST_IDLE;
            core_cmd_r <= I2C_CMD_NOP;
            ld_r      <= 1'b0;
            shift_r   <= 1'b0;
            cmd_ack   <= 1'b0;
            ack_out   <= 1'b0;
        end else begin
            ld_r    <= 1'b0;
            shift_r <= 1'b0;
            cmd_ack <= 1'b0;

            case (state)
                ST_IDLE: begin
                    if (go_r) begin
                        ld_r <= 1'b1;
                        if (start) begin
                            state      <= ST_START;
                            core_cmd_r <= I2C_CMD_START;
                        end else if (read) begin
                            state      <= ST_READ;
                            core_cmd_r <= I2C_CMD_READ;
                        end else if (write) begin
                            state      <= ST_WRITE;
                            core_cmd_r <= I2C_CMD_WRITE;
                        end else begin
                            state      <= ST_STOP;
                            core_cmd_r <= I2C_CMD_STOP;
                        end
                    end
                end

                ST_START: begin
                    if (core_ack_r) begin
                        if (read) begin
                            state      <= ST_READ;
                            core_cmd_r <= I2C_CMD_READ;
                        end else begin
                            state      <= ST_WRITE;
                            core_cmd_r <= I2C_CMD_WRITE;
                        end
                    end
                end

                ST_READ: begin
                    if (core_ack_r) begin
                        if (cnt_done_r) begin
                            state      <= ST_ACK;
                            core_cmd_r <= I2C_CMD_WRITE;
                        end else begin
                            core_cmd_r <= I2C_CMD_READ;
                            shift_r    <= 1'b1;
                        end
                    end
                end

                ST_WRITE: begin
                    if (core_ack_r) begin
                        if (cnt_done_r) begin
                            state      <= ST_ACK;
                            core_cmd_r <= I2C_CMD_READ;
                        end else begin
                            core_cmd_r <= I2C_CMD_WRITE;
                            shift_r    <= 1'b1;
                        end
                    end
                end

                ST_ACK: begin
                    if (core_ack_r) begin
                        ack_out <= core_rxd_r;
                        if (stop) begin
                            state      <= ST_STOP;
                            core_cmd_r <= I2C_CMD_STOP;
                        end else begin
                            state      <= ST_IDLE;
                            core_cmd_r <= I2C_CMD_NOP;
                            cmd_ack    <= 1'b1;
                        end
                    end
                end

                ST_STOP: begin
                    if (core_ack_r) begin
                        state      <= ST_IDLE;
                        core_cmd_r <= I2C_CMD_NOP;
                        cmd_ack    <= 1'b1;
                    end
                end

                default: begin
                    state      <= ST_IDLE;
                    core_cmd_r <= I2C_CMD_NOP;
                end
            endcase
        end
    end

    generate
        if (1'b1) begin : g_bit_controller_scope
            i2c_master_bit_ctrl bit_controller (
                .clk(clk),
                .rst(rst),
                .nReset(nReset),
                .ena(ena),
                .clk_cnt(clk_cnt),
                .cmd(core_cmd_r),
                .cmd_ack(core_ack_r),
                .busy(i2c_busy),
                .al(i2c_al),
                .din(core_txd_r),
                .dout(core_rxd_r),
                .scl_i(scl_i),
                .scl_o(scl_o),
                .scl_oen(scl_oen),
                .sda_i(sda_i),
                .sda_o(sda_o),
                .sda_oen(sda_oen)
            );
        end
    endgenerate

endmodule

// Shipped interface: the contract's ports, probes left unconnected.
module i2c_master_byte_ctrl (
    input wire clk,
    input wire rst,
    input wire nReset,
    input wire ena,
    input wire [15:0] clk_cnt,
    input wire start,
    input wire stop,
    input wire read,
    input wire write,
    input wire ack_in,
    input wire [7:0] din,
    output wire cmd_ack,
    output wire ack_out,
    output wire [7:0] dout,
    output wire i2c_busy,
    output wire i2c_al,
    input wire scl_i,
    output wire scl_o,
    output wire scl_oen,
    input wire sda_i,
    output wire sda_o,
    output wire sda_oen
);
    i2c_master_byte_ctrl__probed u_probed (
        .clk(clk),
        .rst(rst),
        .nReset(nReset),
        .ena(ena),
        .clk_cnt(clk_cnt),
        .start(start),
        .stop(stop),
        .read(read),
        .write(write),
        .ack_in(ack_in),
        .din(din),
        .cmd_ack(cmd_ack),
        .ack_out(ack_out),
        .dout(dout),
        .i2c_busy(i2c_busy),
        .i2c_al(i2c_al),
        .scl_i(scl_i),
        .scl_o(scl_o),
        .scl_oen(scl_oen),
        .sda_i(sda_i),
        .sda_o(sda_o),
        .sda_oen(sda_oen)
    );
endmodule
