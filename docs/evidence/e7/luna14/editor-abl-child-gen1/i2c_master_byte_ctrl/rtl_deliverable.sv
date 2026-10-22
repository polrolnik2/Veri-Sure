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

    localparam [3:0] I2C_CMD_NOP   = 4'b0000,
                     I2C_CMD_START = 4'b0001,
                     I2C_CMD_STOP  = 4'b0010,
                     I2C_CMD_READ  = 4'b0100,
                     I2C_CMD_WRITE = 4'b1000;

    reg [2:0] state;
    reg [7:0] sr;
    reg [2:0] dcnt;
    reg [3:0] core_cmd_r;

    wire core_ack_w;
    wire core_rxd_w;
    wire core_txd_w;
    wire go_w;
    wire ld_w;
    wire shift_w;
    wire cnt_nonzero_w;
    wire cnt_done_w;

    assign go_w = (read | write | stop) & ~cmd_ack;
    assign ld_w = (state == ST_IDLE) & go_w;
    assign cnt_nonzero_w = |dcnt;
    assign cnt_done_w = ~cnt_nonzero_w;
    assign shift_w = ((state == ST_READ) & core_ack_w) |
                     ((state == ST_WRITE) & core_ack_w & ~cnt_done_w);

    assign core_txd_w = (state == ST_ACK) ? ack_in : sr[7];
    assign dout = sr;

    always @(posedge clk or negedge nReset) begin
        if (!nReset) begin
            sr   <= 8'b0;
            dcnt <= 3'b0;
        end else if (rst) begin
            sr   <= 8'b0;
            dcnt <= 3'b0;
        end else begin
            if (ld_w)
                sr <= din;
            else if (shift_w)
                sr <= {sr[6:0], core_rxd_w};

            if (ld_w)
                dcnt <= 3'd7;
            else if (shift_w)
                dcnt <= dcnt - 3'd1;
        end
    end

    always @(posedge clk or negedge nReset) begin
        if (!nReset) begin
            state      <= ST_IDLE;
            cmd_ack    <= 1'b0;
            ack_out    <= 1'b0;
            core_cmd_r <= I2C_CMD_NOP;
        end else if (rst | i2c_al) begin
            state      <= ST_IDLE;
            cmd_ack    <= 1'b0;
            core_cmd_r <= I2C_CMD_NOP;
            if (rst)
                ack_out <= 1'b0;
        end else begin
            cmd_ack    <= 1'b0;
            core_cmd_r <= I2C_CMD_NOP;

            case (state)
                ST_IDLE: begin
                    if (go_w) begin
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
                    if (core_ack_w) begin
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
                    if (core_ack_w) begin
                        if (cnt_done_w) begin
                            state      <= ST_ACK;
                            core_cmd_r <= I2C_CMD_WRITE;
                        end else begin
                            state      <= ST_READ;
                            core_cmd_r <= I2C_CMD_READ;
                        end
                    end
                end

                ST_WRITE: begin
                    if (core_ack_w) begin
                        if (cnt_done_w) begin
                            state      <= ST_ACK;
                            core_cmd_r <= I2C_CMD_READ;
                        end else begin
                            state      <= ST_WRITE;
                            core_cmd_r <= I2C_CMD_WRITE;
                        end
                    end
                end

                ST_ACK: begin
                    if (core_ack_w) begin
                        ack_out <= core_rxd_w;
                        if (stop) begin
                            state      <= ST_STOP;
                            core_cmd_r <= I2C_CMD_STOP;
                        end else begin
                            state   <= ST_IDLE;
                            cmd_ack <= 1'b1;
                        end
                    end
                end

                ST_STOP: begin
                    if (core_ack_w) begin
                        state   <= ST_IDLE;
                        cmd_ack <= 1'b1;
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
        if (1'b1) begin : gen_bit_controller
            i2c_master_bit_ctrl bit_controller (
                .clk     (clk),
                .rst     (rst),
                .nReset  (nReset),
                .ena     (ena),
                .clk_cnt (clk_cnt),
                .cmd     (core_cmd_r),
                .cmd_ack (core_ack_w),
                .busy    (i2c_busy),
                .al      (i2c_al),
                .din     (core_txd_w),
                .dout    (core_rxd_w),
                .scl_i   (scl_i),
                .scl_o   (scl_o),
                .scl_oen (scl_oen),
                .sda_i   (sda_i),
                .sda_o   (sda_o),
                .sda_oen (sda_oen)
            );
        end
    endgenerate

    assign st_idle  = (state == ST_IDLE);
    assign st_start = (state == ST_START);
    assign st_read  = (state == ST_READ);
    assign st_write = (state == ST_WRITE);
    assign st_ack   = (state == ST_ACK);
    assign st_stop  = (state == ST_STOP);

    assign go          = go_w;
    assign ld          = ld_w;
    assign shift       = shift_w;
    assign cnt_nonzero = cnt_nonzero_w;
    assign cnt_done    = cnt_done_w;

    assign core_ack = core_ack_w;
    assign core_rxd = core_rxd_w;
    assign core_txd = core_txd_w;

    assign i2c_cmd_start = (core_cmd_r == I2C_CMD_START);
    assign i2c_cmd_stop  = (core_cmd_r == I2C_CMD_STOP);
    assign i2c_cmd_read  = (core_cmd_r == I2C_CMD_READ);
    assign i2c_cmd_write = (core_cmd_r == I2C_CMD_WRITE);
    assign core_cmd_is_nop = (core_cmd_r == I2C_CMD_NOP);

    assign bit_controller = 1'b1;
    assign i2c_master_bit_ctrl = 1'b1;
    assign core_cmd = 1'b1;
    assign contentreference = 1'b1;

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
