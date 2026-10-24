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
    output dcnt_nonzero,
    output cnt_done,
    output core_ack,
    output core_rxd,
    output core_txd,
    output core_cmd_start,
    output core_cmd_read,
    output core_cmd_write,
    output core_cmd_stop,
    output core_cmd_nop
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
    reg [2:0] state_next;
    reg [3:0] core_cmd_r;
    reg [3:0] core_cmd_next;
    reg [7:0] sr;
    reg [2:0] dcnt;
    reg core_txd_r;
    reg core_txd_next;

    reg ld_i;
    reg shift_i;
    reg cmd_ack_next;
    reg ack_out_next;

    wire core_ack_i;
    wire core_rxd_i;
    wire cnt_done_i;
    wire go_i;

    assign go_i = (read | write | stop) & ~cmd_ack;
    assign cnt_done_i = (dcnt == 3'b000);

    assign dout = sr;

    assign st_idle  = (state == ST_IDLE);
    assign st_start = (state == ST_START);
    assign st_read  = (state == ST_READ);
    assign st_write = (state == ST_WRITE);
    assign st_ack   = (state == ST_ACK);
    assign st_stop  = (state == ST_STOP);

    assign go = go_i;
    assign ld = ld_i;
    assign shift = shift_i;
    assign dcnt_nonzero = (dcnt != 3'b000);
    assign cnt_done = cnt_done_i;

    assign core_ack = core_ack_i;
    assign core_rxd = core_rxd_i;
    assign core_txd = core_txd_r;

    assign core_cmd_start = (core_cmd_r == I2C_CMD_START);
    assign core_cmd_read  = (core_cmd_r == I2C_CMD_READ);
    assign core_cmd_write = (core_cmd_r == I2C_CMD_WRITE);
    assign core_cmd_stop  = (core_cmd_r == I2C_CMD_STOP);
    assign core_cmd_nop   = (core_cmd_r == I2C_CMD_NOP);

    i2c_master_bit_ctrl bit_controller (
        .clk     (clk),
        .rst     (rst),
        .nReset  (nReset),
        .ena     (ena),
        .clk_cnt (clk_cnt),
        .cmd     (core_cmd_r),
        .cmd_ack (core_ack_i),
        .busy    (i2c_busy),
        .al      (i2c_al),
        .din     (core_txd_r),
        .dout    (core_rxd_i),
        .scl_i   (scl_i),
        .scl_o   (scl_o),
        .scl_oen (scl_oen),
        .sda_i   (sda_i),
        .sda_o   (sda_o),
        .sda_oen (sda_oen)
    );

    always @(*) begin
        state_next    = state;
        core_cmd_next = I2C_CMD_NOP;
        core_txd_next = sr[7];
        ld_i          = 1'b0;
        shift_i       = 1'b0;
        cmd_ack_next  = 1'b0;
        ack_out_next  = ack_out;

        case (state)
            ST_IDLE: begin
                if (go_i) begin
                    ld_i = 1'b1;
                    if (start) begin
                        state_next    = ST_START;
                        core_cmd_next = I2C_CMD_START;
                    end else if (read) begin
                        state_next    = ST_READ;
                        core_cmd_next = I2C_CMD_READ;
                    end else if (write) begin
                        state_next    = ST_WRITE;
                        core_cmd_next = I2C_CMD_WRITE;
                    end else begin
                        state_next    = ST_STOP;
                        core_cmd_next = I2C_CMD_STOP;
                    end
                end
            end

            ST_START: begin
                if (core_ack_i) begin
                    if (read) begin
                        state_next    = ST_READ;
                        core_cmd_next = I2C_CMD_READ;
                    end else begin
                        state_next    = ST_WRITE;
                        core_cmd_next = I2C_CMD_WRITE;
                    end
                end else begin
                    core_cmd_next = I2C_CMD_START;
                end
            end

            ST_READ: begin
                if (core_ack_i) begin
                    shift_i = 1'b1;
                    if (cnt_done_i) begin
                        state_next    = ST_ACK;
                        core_cmd_next = I2C_CMD_WRITE;
                    end else begin
                        state_next    = ST_READ;
                        core_cmd_next = I2C_CMD_READ;
                    end
                end else begin
                    core_cmd_next = I2C_CMD_READ;
                end
            end

            ST_WRITE: begin
                if (core_ack_i) begin
                    shift_i = 1'b1;
                    if (cnt_done_i) begin
                        state_next    = ST_ACK;
                        core_cmd_next = I2C_CMD_READ;
                    end else begin
                        state_next    = ST_WRITE;
                        core_cmd_next = I2C_CMD_WRITE;
                    end
                end else begin
                    core_cmd_next = I2C_CMD_WRITE;
                end
            end

            ST_ACK: begin
                core_txd_next = ack_in;
                if (core_ack_i) begin
                    if (core_cmd_r == I2C_CMD_READ)
                        ack_out_next = core_rxd_i;

                    if (stop) begin
                        state_next    = ST_STOP;
                        core_cmd_next = I2C_CMD_STOP;
                    end else begin
                        state_next    = ST_IDLE;
                        core_cmd_next = I2C_CMD_NOP;
                        cmd_ack_next  = 1'b1;
                    end
                end else begin
                    core_cmd_next = core_cmd_r;
                end
            end

            ST_STOP: begin
                if (core_ack_i) begin
                    state_next    = ST_IDLE;
                    core_cmd_next = I2C_CMD_NOP;
                    cmd_ack_next  = 1'b1;
                end else begin
                    core_cmd_next = I2C_CMD_STOP;
                end
            end

            default: begin
                state_next    = ST_IDLE;
                core_cmd_next = I2C_CMD_NOP;
            end
        endcase
    end

    always @(posedge clk or negedge nReset) begin
        if (!nReset) begin
            state      <= ST_IDLE;
            core_cmd_r <= I2C_CMD_NOP;
            core_txd_r <= 1'b0;
            sr         <= 8'b0;
            dcnt       <= 3'b0;
            cmd_ack    <= 1'b0;
            ack_out    <= 1'b0;
        end else if (rst || i2c_al) begin
            state      <= ST_IDLE;
            core_cmd_r <= I2C_CMD_NOP;
            core_txd_r <= 1'b0;
            sr         <= 8'b0;
            dcnt       <= 3'b0;
            cmd_ack    <= 1'b0;
            ack_out    <= 1'b0;
        end else begin
            state      <= state_next;
            core_cmd_r <= core_cmd_next;
            core_txd_r <= core_txd_next;
            cmd_ack    <= cmd_ack_next;
            ack_out    <= ack_out_next;

            if (ld_i)
                sr <= din;
            else if (shift_i)
                sr <= {sr[6:0], core_rxd_i};

            if (ld_i)
                dcnt <= 3'd7;
            else if (shift_i)
                dcnt <= dcnt - 3'd1;
        end
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
