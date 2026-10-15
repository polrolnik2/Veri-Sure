/* verilator lint_off DECLFILENAME */
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
    output cmd_ack,
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

    reg [2:0] state_r;
    reg [3:0] core_cmd_r;
    reg [7:0] sr_r;
    reg [2:0] dcnt_r;
    reg ld_r;
    reg shift_r;
    reg cmd_ack_r;
    reg core_txd_r;

    wire core_ack_r;
    wire core_rxd_r;
    wire busy_r;
    wire al_r;
    wire go_r;
    wire cnt_done_r;

    assign go_r = (read | write | stop) & ~cmd_ack_r;
    assign cnt_done_r = (dcnt_r == 3'b000);

    assign cmd_ack = cmd_ack_r;
    assign dout = sr_r;
    assign i2c_busy = busy_r;
    assign i2c_al = al_r;

    assign st_idle  = (state_r == ST_IDLE);
    assign st_start = (state_r == ST_START);
    assign st_read  = (state_r == ST_READ);
    assign st_write = (state_r == ST_WRITE);
    assign st_ack   = (state_r == ST_ACK);
    assign st_stop  = (state_r == ST_STOP);

    assign go = go_r;
    assign ld = ld_r;
    assign shift = shift_r;
    assign dcnt_nonzero = (dcnt_r != 3'b000);
    assign cnt_done = cnt_done_r;

    assign core_ack = core_ack_r;
    assign core_rxd = core_rxd_r;
    assign core_txd = core_txd_r;

    assign core_cmd_start = (core_cmd_r == I2C_CMD_START);
    assign core_cmd_read  = (core_cmd_r == I2C_CMD_READ);
    assign core_cmd_write = (core_cmd_r == I2C_CMD_WRITE);
    assign core_cmd_stop  = (core_cmd_r == I2C_CMD_STOP);
    assign core_cmd_nop   = (core_cmd_r == I2C_CMD_NOP);

    always @(*) begin
        core_txd_r = sr_r[7];
        if (state_r == ST_ACK)
            core_txd_r = ack_in;
    end

    i2c_master_bit_ctrl bit_controller (
        .clk     (clk),
        .rst     (rst),
        .nReset  (nReset),
        .ena     (ena),
        .clk_cnt (clk_cnt),
        .cmd     (core_cmd_r),
        .cmd_ack (core_ack_r),
        .busy    (busy_r),
        .al      (al_r),
        .din     (core_txd_r),
        .dout    (core_rxd_r),
        .scl_i   (scl_i),
        .scl_o   (scl_o),
        .scl_oen (scl_oen),
        .sda_i   (sda_i),
        .sda_o   (sda_o),
        .sda_oen (sda_oen)
    );

    always @(posedge clk or negedge nReset) begin
        if (!nReset) begin
            state_r    <= ST_IDLE;
            core_cmd_r <= I2C_CMD_NOP;
            ld_r       <= 1'b0;
            shift_r    <= 1'b0;
            cmd_ack_r  <= 1'b0;
            ack_out    <= 1'b0;
        end else if (rst || al_r) begin
            state_r    <= ST_IDLE;
            core_cmd_r <= I2C_CMD_NOP;
            ld_r       <= 1'b0;
            shift_r    <= 1'b0;
            cmd_ack_r  <= 1'b0;
            ack_out    <= 1'b0;
        end else begin
            ld_r      <= 1'b0;
            shift_r   <= 1'b0;
            cmd_ack_r <= 1'b0;

            case (state_r)
                ST_IDLE: begin
                    if (go_r) begin
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
                    if (core_ack_r) begin
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
                    if (core_ack_r) begin
                        shift_r <= 1'b1;
                        if (cnt_done_r) begin
                            state_r    <= ST_ACK;
                            core_cmd_r <= I2C_CMD_WRITE;
                        end else begin
                            state_r    <= ST_READ;
                            core_cmd_r <= I2C_CMD_READ;
                        end
                    end
                end

                ST_WRITE: begin
                    if (core_ack_r) begin
                        if (cnt_done_r) begin
                            state_r    <= ST_ACK;
                            core_cmd_r <= I2C_CMD_READ;
                        end else begin
                            state_r    <= ST_WRITE;
                            core_cmd_r <= I2C_CMD_WRITE;
                            shift_r    <= 1'b1;
                        end
                    end
                end

                ST_ACK: begin
                    if (core_ack_r) begin
                        ack_out <= core_rxd_r;
                        if (stop) begin
                            state_r    <= ST_STOP;
                            core_cmd_r <= I2C_CMD_STOP;
                        end else begin
                            state_r    <= ST_IDLE;
                            core_cmd_r <= I2C_CMD_NOP;
                            cmd_ack_r  <= 1'b1;
                        end
                    end
                end

                ST_STOP: begin
                    if (core_ack_r) begin
                        state_r    <= ST_IDLE;
                        core_cmd_r <= I2C_CMD_NOP;
                        cmd_ack_r  <= 1'b1;
                    end
                end

                default: begin
                    state_r    <= ST_IDLE;
                    core_cmd_r <= I2C_CMD_NOP;
                end
            endcase
        end
    end

    always @(posedge clk or negedge nReset) begin
        if (!nReset) begin
            sr_r   <= 8'h00;
            dcnt_r <= 3'd0;
        end else if (rst || al_r) begin
            sr_r   <= 8'h00;
            dcnt_r <= 3'd0;
        end else if (ld_r) begin
            sr_r   <= din;
            dcnt_r <= 3'd7;
        end else if (shift_r) begin
            sr_r   <= {sr_r[6:0], core_rxd_r};
            dcnt_r <= dcnt_r - 3'd1;
        end
    end

endmodule

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
    output reg dout,
    input scl_i,
    output scl_o,
    output reg scl_oen,
    input sda_i,
    output sda_o,
    output reg sda_oen
);
    localparam [3:0] I2C_CMD_NOP   = 4'b0000;
    localparam [3:0] I2C_CMD_START = 4'b0001;
    localparam [3:0] I2C_CMD_STOP  = 4'b0010;
    localparam [3:0] I2C_CMD_READ  = 4'b0100;
    localparam [3:0] I2C_CMD_WRITE = 4'b1000;

    reg waiting;
    reg [3:0] active_cmd;

    assign scl_o = 1'b0;
    assign sda_o = 1'b0;

    always @(posedge clk or negedge nReset) begin
        if (!nReset) begin
            cmd_ack    <= 1'b0;
            busy       <= 1'b0;
            al         <= 1'b0;
            dout       <= 1'b1;
            scl_oen    <= 1'b1;
            sda_oen    <= 1'b1;
            waiting    <= 1'b0;
            active_cmd <= I2C_CMD_NOP;
        end else if (rst) begin
            cmd_ack    <= 1'b0;
            busy       <= 1'b0;
            al         <= 1'b0;
            dout       <= 1'b1;
            scl_oen    <= 1'b1;
            sda_oen    <= 1'b1;
            waiting    <= 1'b0;
            active_cmd <= I2C_CMD_NOP;
        end else begin
            cmd_ack <= 1'b0;

            if (cmd == I2C_CMD_NOP) begin
                waiting    <= 1'b0;
                active_cmd <= I2C_CMD_NOP;
                scl_oen    <= 1'b1;
                sda_oen    <= 1'b1;
            end else if (!waiting) begin
                waiting    <= 1'b1;
                active_cmd <= cmd;
                cmd_ack    <= 1'b1;
                case (cmd)
                    I2C_CMD_START: begin
                        busy    <= 1'b1;
                        scl_oen <= 1'b1;
                        sda_oen <= 1'b0;
                    end
                    I2C_CMD_STOP: begin
                        busy    <= 1'b0;
                        scl_oen <= 1'b1;
                        sda_oen <= 1'b1;
                    end
                    I2C_CMD_READ: begin
                        dout    <= sda_i;
                        scl_oen <= 1'b0;
                        sda_oen <= 1'b1;
                    end
                    I2C_CMD_WRITE: begin
                        scl_oen <= 1'b0;
                        sda_oen <= din;
                    end
                    default: begin
                        scl_oen <= 1'b1;
                        sda_oen <= 1'b1;
                    end
                endcase
            end else begin
                waiting <= 1'b0;
                scl_oen <= 1'b1;
                if (active_cmd != I2C_CMD_START)
                    sda_oen <= 1'b1;
            end
        end
    end
endmodule
/* verilator lint_on DECLFILENAME */

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
