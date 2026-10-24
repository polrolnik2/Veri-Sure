module i2c_master_bit_ctrl__probed (
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
    output            scl_o,
    output reg        scl_oen,
    output            sda_o,
    output reg        sda_oen,
    output            cnt_zero,
    output            cnt_reload,
    output            clk_en,
    output            slave_wait,
    output            scl_sync,
    output            cscl,
    output            csda,
    output            dscl,
    output            sta_condition,
    output            sto_condition,
    output            sda_chk,
    output            fsm_active,
    output            in_start_sequence,
    output            in_stop_sequence,
    output            in_read_sequence,
    output            in_write_sequence
);

    localparam [3:0] ST_IDLE   = 4'd0,
                     ST_START_A = 4'd1,
                     ST_START_B = 4'd2,
                     ST_START_C = 4'd3,
                     ST_START_D = 4'd4,
                     ST_STOP_A  = 4'd5,
                     ST_STOP_B  = 4'd6,
                     ST_STOP_C  = 4'd7,
                     ST_READ_A  = 4'd8,
                     ST_READ_B  = 4'd9,
                     ST_READ_C  = 4'd10,
                     ST_WRITE_A = 4'd11,
                     ST_WRITE_B = 4'd12,
                     ST_WRITE_C = 4'd13;

    reg [3:0] state;
    reg [15:0] cnt;
    reg clk_en_r;
    reg [15:0] filter_cnt;
    reg [2:0] fSCL;
    reg [2:0] fSDA;
    reg cSCL;
    reg cSDA;
    reg dSCL;
    reg dSDA;
    reg sda_chk_r;

    wire sSCL_int;
    wire sSDA_int;
    wire cnt_zero_int;
    wire slave_wait_int;
    wire scl_sync_int;
    wire sta_condition_int;
    wire sto_condition_int;
    wire stop_state_int;
    wire arbitration_lost_int;

    assign sSCL_int = (fSCL[2] & fSCL[1]) |
                      (fSCL[1] & fSCL[0]) |
                      (fSCL[2] & fSCL[0]);
    assign sSDA_int = (fSDA[2] & fSDA[1]) |
                      (fSDA[1] & fSDA[0]) |
                      (fSDA[2] & fSDA[0]);

    assign cnt_zero_int = (cnt == 16'h0000);
    assign slave_wait_int = scl_oen & ~sSCL_int;
    assign scl_sync_int = scl_oen & dSCL & ~sSCL_int;
    assign sta_condition_int = ~sSDA_int & dSDA & sSCL_int;
    assign sto_condition_int = sSDA_int & ~dSDA & sSCL_int;

    assign stop_state_int = (state == ST_STOP_A) |
                            (state == ST_STOP_B) |
                            (state == ST_STOP_C);
    assign arbitration_lost_int =
        (sda_chk_r & sda_oen & ~sSDA_int) |
        ((state != ST_IDLE) & ~stop_state_int & sto_condition_int);

    assign scl_o = 1'b0;
    assign sda_o = 1'b0;

    assign cnt_zero = cnt_zero_int;
    assign cnt_reload = nReset & ~rst &
                        (~ena |
                         (ena & scl_sync_int) |
                         (ena & ~scl_sync_int & ~slave_wait_int & cnt_zero_int));
    assign clk_en = clk_en_r;
    assign slave_wait = slave_wait_int;
    assign scl_sync = scl_sync_int;
    assign cscl = cSCL;
    assign csda = cSDA;
    assign dscl = dSCL;
    assign sta_condition = sta_condition_int;
    assign sto_condition = sto_condition_int;
    assign sda_chk = sda_chk_r;
    assign fsm_active = (state != ST_IDLE);
    assign in_start_sequence = (state == ST_START_A) |
                               (state == ST_START_B) |
                               (state == ST_START_C) |
                               (state == ST_START_D);
    assign in_stop_sequence = stop_state_int;
    assign in_read_sequence = (state == ST_READ_A) |
                              (state == ST_READ_B) |
                              (state == ST_READ_C);
    assign in_write_sequence = (state == ST_WRITE_A) |
                               (state == ST_WRITE_B) |
                               (state == ST_WRITE_C);

    always @(posedge clk or negedge nReset) begin
        if (!nReset) begin
            cnt <= 16'h0000;
            clk_en_r <= 1'b1;
        end else if (rst) begin
            cnt <= 16'h0000;
            clk_en_r <= 1'b1;
        end else if (!ena) begin
            cnt <= clk_cnt;
            clk_en_r <= 1'b0;
        end else if (scl_sync_int) begin
            cnt <= clk_cnt;
            clk_en_r <= 1'b0;
        end else if (slave_wait_int) begin
            cnt <= cnt;
            clk_en_r <= 1'b0;
        end else if (cnt_zero_int) begin
            cnt <= clk_cnt;
            clk_en_r <= 1'b1;
        end else begin
            cnt <= cnt - 16'h0001;
            clk_en_r <= 1'b0;
        end
    end

    always @(posedge clk or negedge nReset) begin
        if (!nReset) begin
            cSCL <= 1'b1;
            cSDA <= 1'b1;
        end else if (rst) begin
            cSCL <= 1'b1;
            cSDA <= 1'b1;
        end else begin
            cSCL <= scl_i;
            cSDA <= sda_i;
        end
    end

    always @(posedge clk or negedge nReset) begin
        if (!nReset) begin
            filter_cnt <= 16'h0000;
            fSCL <= 3'b111;
            fSDA <= 3'b111;
        end else if (rst) begin
            filter_cnt <= 16'h0000;
            fSCL <= 3'b111;
            fSDA <= 3'b111;
        end else if (!ena) begin
            filter_cnt <= 16'h0000;
        end else if (filter_cnt == 16'h0000) begin
            filter_cnt <= clk_cnt >> 2;
            fSCL <= {fSCL[1:0], cSCL};
            fSDA <= {fSDA[1:0], cSDA};
        end else begin
            filter_cnt <= filter_cnt - 16'h0001;
        end
    end

    always @(posedge clk or negedge nReset) begin
        if (!nReset) begin
            dSCL <= 1'b1;
            dSDA <= 1'b1;
        end else if (rst) begin
            dSCL <= 1'b1;
            dSDA <= 1'b1;
        end else begin
            dSCL <= sSCL_int;
            dSDA <= sSDA_int;
        end
    end

    always @(posedge clk or negedge nReset) begin
        if (!nReset) begin
            busy <= 1'b0;
        end else if (rst) begin
            busy <= 1'b0;
        end else if (sta_condition_int) begin
            busy <= 1'b1;
        end else if (sto_condition_int) begin
            busy <= 1'b0;
        end
    end

    always @(posedge clk or negedge nReset) begin
        if (!nReset) begin
            dout <= 1'b0;
        end else if (rst) begin
            dout <= 1'b0;
        end else if (sSCL_int & ~dSCL) begin
            dout <= sSDA_int;
        end
    end

    always @(posedge clk or negedge nReset) begin
        if (!nReset) begin
            state <= ST_IDLE;
            cmd_ack <= 1'b0;
            al <= 1'b0;
            scl_oen <= 1'b1;
            sda_oen <= 1'b1;
            sda_chk_r <= 1'b0;
        end else if (rst) begin
            state <= ST_IDLE;
            cmd_ack <= 1'b0;
            al <= 1'b0;
            scl_oen <= 1'b1;
            sda_oen <= 1'b1;
            sda_chk_r <= 1'b0;
        end else begin
            cmd_ack <= 1'b0;

            if (arbitration_lost_int) begin
                state <= ST_IDLE;
                al <= 1'b1;
                scl_oen <= 1'b1;
                sda_oen <= 1'b1;
                sda_chk_r <= 1'b0;
            end else if (ena && clk_en_r) begin
                case (state)
                    ST_IDLE: begin
                        case (cmd)
                            4'h1: state <= ST_START_A;
                            4'h2: state <= ST_STOP_A;
                            4'h4: state <= ST_WRITE_A;
                            4'h8: state <= ST_READ_A;
                            default: state <= ST_IDLE;
                        endcase
                    end

                    ST_START_A: begin
                        scl_oen <= 1'b1;
                        sda_oen <= 1'b1;
                        sda_chk_r <= 1'b0;
                        state <= ST_START_B;
                    end

                    ST_START_B: begin
                        scl_oen <= 1'b1;
                        sda_oen <= 1'b0;
                        state <= ST_START_C;
                    end

                    ST_START_C: begin
                        scl_oen <= 1'b0;
                        sda_oen <= 1'b0;
                        state <= ST_START_D;
                    end

                    ST_START_D: begin
                        state <= ST_IDLE;
                        cmd_ack <= 1'b1;
                    end

                    ST_STOP_A: begin
                        scl_oen <= 1'b0;
                        sda_oen <= 1'b0;
                        state <= ST_STOP_B;
                    end

                    ST_STOP_B: begin
                        scl_oen <= 1'b1;
                        sda_oen <= 1'b0;
                        state <= ST_STOP_C;
                    end

                    ST_STOP_C: begin
                        scl_oen <= 1'b1;
                        sda_oen <= 1'b1;
                        state <= ST_IDLE;
                        cmd_ack <= 1'b1;
                    end

                    ST_READ_A: begin
                        scl_oen <= 1'b0;
                        sda_oen <= 1'b1;
                        state <= ST_READ_B;
                    end

                    ST_READ_B: begin
                        scl_oen <= 1'b1;
                        sda_oen <= 1'b1;
                        state <= ST_READ_C;
                    end

                    ST_READ_C: begin
                        scl_oen <= 1'b0;
                        state <= ST_IDLE;
                        cmd_ack <= 1'b1;
                    end

                    ST_WRITE_A: begin
                        scl_oen <= 1'b0;
                        sda_oen <= din;
                        state <= ST_WRITE_B;
                    end

                    ST_WRITE_B: begin
                        scl_oen <= 1'b1;
                        sda_chk_r <= 1'b1;
                        state <= ST_WRITE_C;
                    end

                    ST_WRITE_C: begin
                        scl_oen <= 1'b0;
                        sda_chk_r <= 1'b0;
                        state <= ST_IDLE;
                        cmd_ack <= 1'b1;
                    end

                    default: begin
                        state <= ST_IDLE;
                        scl_oen <= 1'b1;
                        sda_oen <= 1'b1;
                        sda_chk_r <= 1'b0;
                    end
                endcase
            end
        end
    end

endmodule

// Shipped interface: the contract's ports, probes left unconnected.
module i2c_master_bit_ctrl (
    input wire clk,
    input wire rst,
    input wire nReset,
    input wire ena,
    input wire [15:0] clk_cnt,
    input wire [3:0] cmd,
    input wire din,
    input wire scl_i,
    input wire sda_i,
    output wire cmd_ack,
    output wire busy,
    output wire al,
    output wire dout,
    output wire scl_o,
    output wire scl_oen,
    output wire sda_o,
    output wire sda_oen
);
    i2c_master_bit_ctrl__probed u_probed (
        .clk(clk),
        .rst(rst),
        .nReset(nReset),
        .ena(ena),
        .clk_cnt(clk_cnt),
        .cmd(cmd),
        .din(din),
        .scl_i(scl_i),
        .sda_i(sda_i),
        .cmd_ack(cmd_ack),
        .busy(busy),
        .al(al),
        .dout(dout),
        .scl_o(scl_o),
        .scl_oen(scl_oen),
        .sda_o(sda_o),
        .sda_oen(sda_oen)
    );
endmodule
