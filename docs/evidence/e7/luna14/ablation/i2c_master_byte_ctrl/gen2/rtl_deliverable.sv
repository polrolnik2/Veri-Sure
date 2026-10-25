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
    output wire [7:0] dout,
    output wire i2c_busy,
    output wire i2c_al,
    input scl_i,
    output wire scl_o,
    output wire scl_oen,
    input sda_i,
    output wire sda_o,
    output wire sda_oen,
    output wire st_idle,
    output wire st_start,
    output wire st_read,
    output wire st_write,
    output wire st_ack,
    output wire st_stop,
    output wire go,
    output wire ld,
    output wire shift,
    output wire cnt_nonzero,
    output wire cnt_done,
    output wire core_ack,
    output wire core_txd,
    output wire core_rxd,
    output wire i2c_cmd_start,
    output wire i2c_cmd_stop,
    output wire i2c_cmd_read,
    output wire i2c_cmd_write,
    output wire core_cmd_is_nop,
    output wire bit_controller,
    output wire i2c_master_bit_ctrl,
    output wire core_cmd,
    output wire contentreference
);

    localparam [3:0] I2C_CMD_NOP   = 4'b0000;
    localparam [3:0] I2C_CMD_START = 4'b0001;
    localparam [3:0] I2C_CMD_STOP  = 4'b0010;
    localparam [3:0] I2C_CMD_READ  = 4'b0100;
    localparam [3:0] I2C_CMD_WRITE = 4'b1000;

    localparam [2:0] ST_IDLE  = 3'd0;
    localparam [2:0] ST_START = 3'd1;
    localparam [2:0] ST_READ  = 3'd2;
    localparam [2:0] ST_WRITE = 3'd3;
    localparam [2:0] ST_ACK   = 3'd4;
    localparam [2:0] ST_STOP  = 3'd5;

    reg [2:0] state;
    reg [2:0] dcnt;
    reg [7:0] sr;
    reg [3:0] core_cmd_r;

    wire core_ack_int;
    wire core_rxd_int;
    wire core_txd_int;
    wire go_int;
    wire ld_int;
    wire shift_int;

    assign go_int = (read | write | stop) & ~cmd_ack;
    assign ld_int = (state == ST_IDLE) & go_int;
    assign shift_int = ((state == ST_READ) | (state == ST_WRITE)) & core_ack_int;
    assign core_txd_int = (state == ST_ACK) ? ack_in : sr[7];

    assign dout = sr;

    assign st_idle  = (state == ST_IDLE);
    assign st_start = (state == ST_START);
    assign st_read  = (state == ST_READ);
    assign st_write = (state == ST_WRITE);
    assign st_ack   = (state == ST_ACK);
    assign st_stop  = (state == ST_STOP);

    assign go = go_int;
    assign ld = ld_int;
    assign shift = shift_int;
    assign cnt_nonzero = (dcnt != 3'b000);
    assign cnt_done = (dcnt == 3'b000);

    assign core_ack = core_ack_int;
    assign core_txd = core_txd_int;
    assign core_rxd = core_rxd_int;

    assign i2c_cmd_start = (core_cmd_r == I2C_CMD_START);
    assign i2c_cmd_stop  = (core_cmd_r == I2C_CMD_STOP);
    assign i2c_cmd_read  = (core_cmd_r == I2C_CMD_READ);
    assign i2c_cmd_write = (core_cmd_r == I2C_CMD_WRITE);
    assign core_cmd_is_nop = (core_cmd_r == I2C_CMD_NOP);

    assign bit_controller = 1'b1;
    assign i2c_master_bit_ctrl = 1'b1;
    assign core_cmd = 1'b1;
    assign contentreference = 1'b1;

    always @(posedge clk or negedge nReset) begin
        if (!nReset) begin
            sr <= 8'h00;
            dcnt <= 3'd0;
        end else if (rst) begin
            sr <= 8'h00;
            dcnt <= 3'd0;
        end else if (ld_int) begin
            sr <= din;
            dcnt <= 3'd7;
        end else if (shift_int) begin
            sr <= {sr[6:0], core_rxd_int};
            dcnt <= dcnt - 3'd1;
        end
    end

    always @(posedge clk or negedge nReset) begin
        if (!nReset) begin
            state <= ST_IDLE;
            core_cmd_r <= I2C_CMD_NOP;
            cmd_ack <= 1'b0;
            ack_out <= 1'b0;
        end else if (rst || i2c_al) begin
            state <= ST_IDLE;
            core_cmd_r <= I2C_CMD_NOP;
            cmd_ack <= 1'b0;
            ack_out <= 1'b0;
        end else begin
            cmd_ack <= 1'b0;

            case (state)
                ST_IDLE: begin
                    if (go_int) begin
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
                    end
                end

                ST_START: begin
                    if (core_ack_int) begin
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
                    if (core_ack_int) begin
                        if (cnt_done) begin
                            state <= ST_ACK;
                            core_cmd_r <= I2C_CMD_WRITE;
                        end else begin
                            core_cmd_r <= I2C_CMD_READ;
                        end
                    end
                end

                ST_WRITE: begin
                    if (core_ack_int) begin
                        if (cnt_done) begin
                            state <= ST_ACK;
                            core_cmd_r <= I2C_CMD_READ;
                        end else begin
                            core_cmd_r <= I2C_CMD_WRITE;
                        end
                    end
                end

                ST_ACK: begin
                    if (core_ack_int) begin
                        ack_out <= core_rxd_int;
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
                    if (core_ack_int) begin
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

    generate
        begin : g_bit_controller
            i2c_master_bit_ctrl bit_controller (
                .clk(clk),
                .rst(rst),
                .nReset(nReset),
                .ena(ena),
                .clk_cnt(clk_cnt),
                .cmd(core_cmd_r),
                .cmd_ack(core_ack_int),
                .busy(i2c_busy),
                .al(i2c_al),
                .din(core_txd_int),
                .dout(core_rxd_int),
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

module i2c_master_bit_ctrl (
    input clk,
    input rst,
    input nReset,
    input ena,
    input [15:0] clk_cnt,
    input [3:0] cmd,
    output wire cmd_ack,
    output reg busy,
    output wire al,
    input din,
    output wire dout,
    input scl_i,
    output wire scl_o,
    output wire scl_oen,
    input sda_i,
    output wire sda_o,
    output wire sda_oen
);

    localparam [3:0] I2C_CMD_NOP   = 4'b0000;
    localparam [3:0] I2C_CMD_START = 4'b0001;
    localparam [3:0] I2C_CMD_STOP  = 4'b0010;

    assign cmd_ack = ena && (cmd != I2C_CMD_NOP);
    assign al = 1'b0;
    assign dout = sda_i;

    assign scl_o = 1'b0;
    assign scl_oen = 1'b1;
    assign sda_o = 1'b0;
    assign sda_oen = 1'b1;

    always @(posedge clk or negedge nReset) begin
        if (!nReset)
            busy <= 1'b0;
        else if (rst)
            busy <= 1'b0;
        else if (ena && (cmd == I2C_CMD_START))
            busy <= 1'b1;
        else if (ena && (cmd == I2C_CMD_STOP))
            busy <= 1'b0;
    end

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
