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
    reg [3:0] core_cmd;
    reg [7:0] sr;
    reg [2:0] dcnt;

    reg core_ack_r;
    reg core_rxd_r;
    reg busy_r;

    wire go_int;
    wire ld_int;
    wire shift_int;
    wire cnt_done_int;
    wire core_txd_int;

    assign go_int = (read | write | stop) & ~cmd_ack;
    assign cnt_done_int = (dcnt == 3'b000);
    assign ld_int = ld_reg;

reg ld_reg;
reg shift_reg;
reg transfer_read;
    assign shift_int = shift_reg;
    assign core_txd_int = (state == ST_ACK && transfer_read) ? ack_in : sr[7];

    assign dout = sr;
    assign i2c_busy = busy_r;
    assign i2c_al = 1'b0;

    // The lower-level bit controller is not included in this source. These
    // outputs represent an idle, released open-drain pad interface.
    assign scl_o = 1'b0;
    assign scl_oen = 1'b1;
    assign sda_o = 1'b0;
    assign sda_oen = 1'b1;

    assign go = go_int;
    assign ld = ld_int;
    assign shift = shift_int;
    assign dcnt_nonzero = |dcnt;
    assign cnt_done = cnt_done_int;
    assign core_ack = core_ack_r;
    assign core_rxd = core_rxd_r;
    assign core_txd = core_txd_int;

    assign st_idle = (state == ST_IDLE);
    assign st_start = (state == ST_START);
    assign st_read = (state == ST_READ);
    assign st_write = (state == ST_WRITE);
    assign st_ack = (state == ST_ACK);
    assign st_stop = (state == ST_STOP);

    assign core_cmd_start = (core_cmd == I2C_CMD_START);
    assign core_cmd_read = (core_cmd == I2C_CMD_READ);
    assign core_cmd_write = (core_cmd == I2C_CMD_WRITE);
    assign core_cmd_stop = (core_cmd == I2C_CMD_STOP);
    assign core_cmd_nop = (core_cmd == I2C_CMD_NOP);

    // Minimal local command responder in place of the unavailable bit controller.
    always @(posedge clk or negedge nReset) begin
        if (!nReset) begin
            core_ack_r <= 1'b0;
            core_rxd_r <= 1'b0;
            busy_r <= 1'b0;
        end else if (rst) begin
            core_ack_r <= 1'b0;
            core_rxd_r <= 1'b0;
            busy_r <= 1'b0;
        end else begin
            core_ack_r <= 1'b0;
            // Complete each held command once, then wait for the byte FSM to
            // consume the acknowledgement and launch its next command.
            if (ena && (core_cmd != I2C_CMD_NOP) && !core_ack_r) begin
                core_ack_r <= 1'b1;
                case (core_cmd)
                    I2C_CMD_START: busy_r <= 1'b1;
                    I2C_CMD_STOP:  busy_r <= 1'b0;
                    I2C_CMD_READ:  core_rxd_r <= sda_i;
                    default:       busy_r <= busy_r;
                endcase
            end
        end
    end

    always @(posedge clk or negedge nReset) begin
        if (!nReset) begin
            state <= ST_IDLE;
            core_cmd <= I2C_CMD_NOP;
            cmd_ack <= 1'b0;
            ack_out <= 1'b0;
            sr <= 8'h00;
            dcnt <= 3'b000;
            ld_reg <= 1'b0;
            shift_reg <= 1'b0;
            transfer_read <= 1'b0;
        end else if (rst || i2c_al) begin
            state <= ST_IDLE;
            core_cmd <= I2C_CMD_NOP;
            cmd_ack <= 1'b0;
            ack_out <= 1'b0;
            sr <= 8'h00;
            dcnt <= 3'b000;
            ld_reg <= 1'b0;
            shift_reg <= 1'b0;
            transfer_read <= 1'b0;
        end else begin
            // The datapath consumes the registered controls from the prior
            // cycle; the FSM schedules controls for the next cycle.
            ld_reg <= 1'b0;
            shift_reg <= 1'b0;
            cmd_ack <= 1'b0;

            if (ld_reg) begin
                sr <= din;
                dcnt <= 3'd7;
            end else if (shift_reg) begin
                sr <= {sr[6:0], core_rxd_r};
                dcnt <= dcnt - 3'd1;
            end

            case (state)
                ST_IDLE: begin
                    if (go_int) begin
                        if (start) begin
                            state <= ST_START;
                            core_cmd <= I2C_CMD_START;
                            ld_reg <= 1'b1;
                        end else if (read) begin
                            state <= ST_READ;
                            core_cmd <= I2C_CMD_READ;
                            ld_reg <= 1'b1;
                            transfer_read <= 1'b1;
                        end else if (write) begin
                            state <= ST_WRITE;
                            core_cmd <= I2C_CMD_WRITE;
                            ld_reg <= 1'b1;
                            transfer_read <= 1'b0;
                        end else begin
                            state <= ST_STOP;
                            core_cmd <= I2C_CMD_STOP;
                            transfer_read <= 1'b0;
                        end
                    end
                end

                ST_START: begin
                    if (core_ack_r) begin
                        if (read) begin
                            state <= ST_READ;
                            core_cmd <= I2C_CMD_READ;
                            transfer_read <= 1'b1;
                        end else begin
                            state <= ST_WRITE;
                            core_cmd <= I2C_CMD_WRITE;
                            transfer_read <= 1'b0;
                        end
                    end
                end

                ST_READ: begin
                    if (core_ack_r) begin
                        shift_reg <= 1'b1;
                        if (cnt_done_int) begin
                            state <= ST_ACK;
                            core_cmd <= I2C_CMD_WRITE;
                        end else begin
                            core_cmd <= I2C_CMD_READ;
                        end
                    end
                end

                ST_WRITE: begin
                    if (core_ack_r) begin
                        if (cnt_done_int) begin
                            state <= ST_ACK;
                            core_cmd <= I2C_CMD_READ;
                        end else begin
                            core_cmd <= I2C_CMD_WRITE;
                            shift_reg <= 1'b1;
                        end
                    end
                end

                ST_ACK: begin
                    if (core_ack_r) begin
                        ack_out <= core_rxd_r;
                        if (stop) begin
                            state <= ST_STOP;
                            core_cmd <= I2C_CMD_STOP;
                        end else begin
                            state <= ST_IDLE;
                            core_cmd <= I2C_CMD_NOP;
                            cmd_ack <= 1'b1;
                        end
                    end
                end

                ST_STOP: begin
                    if (core_ack_r) begin
                        state <= ST_IDLE;
                        core_cmd <= I2C_CMD_NOP;
                        cmd_ack <= 1'b1;
                    end
                end

                default: begin
                    state <= ST_IDLE;
                    core_cmd <= I2C_CMD_NOP;
                end
            endcase
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
