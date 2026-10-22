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
    output core_cmd_nop
);

    localparam [2:0] ST_IDLE  = 3'b000;
    localparam [2:0] ST_START = 3'b001;
    localparam [2:0] ST_READ  = 3'b010;
    localparam [2:0] ST_WRITE = 3'b011;
    localparam [2:0] ST_ACK   = 3'b100;
    localparam [2:0] ST_STOP  = 3'b101;

    localparam [3:0] I2C_CMD_NOP   = 4'b0000;
    localparam [3:0] I2C_CMD_START = 4'b0001;
    localparam [3:0] I2C_CMD_STOP  = 4'b0010;
    localparam [3:0] I2C_CMD_READ  = 4'b0100;
    localparam [3:0] I2C_CMD_WRITE = 4'b1000;

    reg [2:0] state;
    reg [7:0] sr;
    reg [2:0] dcnt;

    reg [3:0] core_cmd_int;
    reg core_txd_int;
    reg ld_int;
    reg shift_int;

    wire go_int;
    wire cnt_done_int;
    wire core_ack_int;
    wire core_rxd_int;

    assign go_int = (read | write | stop) & ~cmd_ack;
    assign cnt_done_int = (dcnt == 3'b000);

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
    assign dcnt_nonzero = (dcnt != 3'b000);
    assign cnt_done = cnt_done_int;

    assign core_ack = core_ack_int;
    assign core_rxd = core_rxd_int;
    assign core_txd = core_txd_int;

    assign core_cmd_start = (core_cmd_int == I2C_CMD_START);
    assign core_cmd_read  = (core_cmd_int == I2C_CMD_READ);
    assign core_cmd_write = (core_cmd_int == I2C_CMD_WRITE);
    assign core_cmd_stop  = (core_cmd_int == I2C_CMD_STOP);
    assign core_cmd_nop   = (core_cmd_int == I2C_CMD_NOP);

    i2c_master_bit_ctrl bit_controller (
        .clk     (clk),
        .rst     (rst),
        .nReset  (nReset),
        .ena     (ena),
        .clk_cnt (clk_cnt),
        .cmd     (core_cmd_int),
        .cmd_ack (core_ack_int),
        .busy    (i2c_busy),
        .al      (i2c_al),
        .din     (core_txd_int),
        .dout    (core_rxd_int),
        .scl_i   (scl_i),
        .scl_o   (scl_o),
        .scl_oen (scl_oen),
        .sda_i   (sda_i),
        .sda_o   (sda_o),
        .sda_oen (sda_oen)
    );

    always @(*) begin
        core_cmd_int = I2C_CMD_NOP;
        core_txd_int = sr[7];
        ld_int = 1'b0;
        shift_int = 1'b0;

        if (nReset && !rst && !i2c_al) begin
            case (state)
                ST_IDLE: begin
                    if (go_int) begin
                        if (start) begin
                            core_cmd_int = I2C_CMD_START;
                            ld_int = 1'b1;
                        end else if (read) begin
                            core_cmd_int = I2C_CMD_READ;
                            ld_int = 1'b1;
                        end else if (write) begin
                            core_cmd_int = I2C_CMD_WRITE;
                            ld_int = 1'b1;
                        end else begin
                            core_cmd_int = I2C_CMD_STOP;
                        end
                    end
                end

                ST_START: begin
                    core_cmd_int = I2C_CMD_START;
                    if (core_ack_int) begin
                        if (read)
                            core_cmd_int = I2C_CMD_READ;
                        else
                            core_cmd_int = I2C_CMD_WRITE;
                    end
                end

                ST_READ: begin
                    core_cmd_int = I2C_CMD_READ;
                    if (core_ack_int) begin
                        shift_int = 1'b1;
                        if (cnt_done_int)
                            core_cmd_int = I2C_CMD_WRITE;
                    end
                end

                ST_WRITE: begin
                    core_cmd_int = I2C_CMD_WRITE;
                    if (core_ack_int) begin
                        shift_int = 1'b1;
                        if (cnt_done_int)
                            core_cmd_int = I2C_CMD_READ;
                    end
                end

                ST_ACK: begin
                    if (read) begin
                        core_cmd_int = I2C_CMD_WRITE;
                        core_txd_int = ack_in;
                    end else begin
                        core_cmd_int = I2C_CMD_READ;
                    end

                    if (core_ack_int) begin
                        if (stop)
                            core_cmd_int = I2C_CMD_STOP;
                        else
                            core_cmd_int = I2C_CMD_NOP;
                    end
                end

                ST_STOP: begin
                    core_cmd_int = I2C_CMD_STOP;
                    if (core_ack_int)
                        core_cmd_int = I2C_CMD_NOP;
                end

                default: begin
                    core_cmd_int = I2C_CMD_NOP;
                end
            endcase
        end
    end

    always @(posedge clk or negedge nReset) begin
        if (!nReset) begin
            sr <= 8'h00;
            dcnt <= 3'b000;
        end else if (rst) begin
            sr <= 8'h00;
            dcnt <= 3'b000;
        end else begin
            if (ld_int) begin
                sr <= din;
                dcnt <= 3'd7;
            end else if (shift_int) begin
                sr <= {sr[6:0], core_rxd_int};
                dcnt <= dcnt - 3'd1;
            end
        end
    end

    always @(posedge clk or negedge nReset) begin
        if (!nReset) begin
            state <= ST_IDLE;
            cmd_ack <= 1'b0;
            ack_out <= 1'b0;
        end else if (rst || i2c_al) begin
            state <= ST_IDLE;
            cmd_ack <= 1'b0;
            ack_out <= 1'b0;
        end else begin
            cmd_ack <= 1'b0;

            case (state)
                ST_IDLE: begin
                    if (go_int) begin
                        if (start)
                            state <= ST_START;
                        else if (read)
                            state <= ST_READ;
                        else if (write)
                            state <= ST_WRITE;
                        else
                            state <= ST_STOP;
                    end
                end

                ST_START: begin
                    if (core_ack_int) begin
                        if (read)
                            state <= ST_READ;
                        else
                            state <= ST_WRITE;
                    end
                end

                ST_READ: begin
                    if (core_ack_int && cnt_done_int)
                        state <= ST_ACK;
                end

                ST_WRITE: begin
                    if (core_ack_int && cnt_done_int)
                        state <= ST_ACK;
                end

                ST_ACK: begin
                    if (core_ack_int) begin
                        if (!read)
                            ack_out <= core_rxd_int;

                        if (stop) begin
                            state <= ST_STOP;
                        end else begin
                            state <= ST_IDLE;
                            cmd_ack <= 1'b1;
                        end
                    end
                end

                ST_STOP: begin
                    if (core_ack_int) begin
                        state <= ST_IDLE;
                        cmd_ack <= 1'b1;
                    end
                end

                default: begin
                    state <= ST_IDLE;
                end
            endcase
        end
    end

endmodule