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
    output wire       scl_o,
    output reg        scl_oen,
    output wire       sda_o,
    output reg        sda_oen,
    output wire       cnt_zero,
    output wire       cnt_reload,
    output wire       clk_en,
    output wire       slave_wait,
    output wire       scl_sync,
    output wire       cscl,
    output wire       csda,
    output wire       dscl,
    output wire       sta_condition,
    output wire       sto_condition,
    output wire       sda_chk,
    output wire       fsm_active,
    output wire       in_start_sequence,
    output wire       in_stop_sequence,
    output wire       in_read_sequence,
    output wire       in_write_sequence
);

    localparam [3:0] ST_IDLE    = 4'h0,
                     ST_START_A = 4'h1,
                     ST_START_B = 4'h2,
                     ST_START_C = 4'h3,
                     ST_START_D = 4'h4,
                     ST_STOP_A  = 4'h5,
                     ST_STOP_B  = 4'h6,
                     ST_STOP_C  = 4'h7,
                     ST_READ_A  = 4'h8,
                     ST_READ_B  = 4'h9,
                     ST_READ_C  = 4'hA,
                     ST_WRITE_A = 4'hB,
                     ST_WRITE_B = 4'hC,
                     ST_WRITE_C = 4'hD;

    reg [3:0] state;
    reg [15:0] cnt;
    reg        clk_en_r;

    reg        cSCL_meta, cSCL;
    reg        cSDA_meta, cSDA;
    reg [2:0]  fSCL, fSDA;
    reg [13:0] filter_cnt;
    reg        dSCL, dSDA;
    reg        din_r;

    wire sSCL = (fSCL[2] & fSCL[1]) |
                (fSCL[2] & fSCL[0]) |
                (fSCL[1] & fSCL[0]);
    wire sSDA = (fSDA[2] & fSDA[1]) |
                (fSDA[2] & fSDA[0]) |
                (fSDA[1] & fSDA[0]);

    wire cnt_zero_w = (cnt == 16'h0000);
    wire slave_wait_w = scl_oen && !sSCL;
    wire scl_sync_w = scl_oen && dSCL && !sSCL;
    wire sta_condition_w = !sSDA && dSDA && sSCL;
    wire sto_condition_w = sSDA && !dSDA && sSCL;
    wire sda_check_w = (state == ST_WRITE_B);
    wire in_stop_w = (state == ST_STOP_A) ||
                     (state == ST_STOP_B) ||
                     (state == ST_STOP_C);
    wire arb_lost_now = (sda_check_w && din_r && !sSDA) ||
                        (sto_condition_w &&
                         (state != ST_IDLE) && !in_stop_w);
    wire cnt_reload_w = !nReset || rst || !ena ||
                        scl_sync_w || (cnt_zero_w && !slave_wait_w);

    assign scl_o = 1'b0;
    assign sda_o = 1'b0;

    assign cnt_zero = cnt_zero_w;
    assign cnt_reload = cnt_reload_w;
    assign clk_en = clk_en_r;
    assign slave_wait = slave_wait_w;
    assign scl_sync = scl_sync_w;
    assign cscl = cSCL;
    assign csda = cSDA;
    assign dscl = dSCL;
    assign sta_condition = sta_condition_w;
    assign sto_condition = sto_condition_w;
    assign sda_chk = sda_check_w;
    assign fsm_active = (state != ST_IDLE);
    assign in_start_sequence = (state == ST_START_A) ||
                               (state == ST_START_B) ||
                               (state == ST_START_C) ||
                               (state == ST_START_D);
    assign in_stop_sequence = in_stop_w;
    assign in_read_sequence = (state == ST_READ_A) ||
                              (state == ST_READ_B) ||
                              (state == ST_READ_C);
    assign in_write_sequence = (state == ST_WRITE_A) ||
                               (state == ST_WRITE_B) ||
                               (state == ST_WRITE_C);

    always @(posedge clk or negedge nReset) begin
        if (!nReset) begin
            cnt      <= 16'h0000;
            clk_en_r <= 1'b1;
        end else if (rst) begin
            cnt      <= 16'h0000;
            clk_en_r <= 1'b1;
        end else if (!ena) begin
            cnt      <= clk_cnt;
            clk_en_r <= 1'b0;
        end else if (scl_sync_w) begin
            cnt      <= clk_cnt;
            clk_en_r <= 1'b1;
        end else if (slave_wait_w) begin
            cnt      <= cnt;
            clk_en_r <= 1'b0;
        end else if (cnt_zero_w) begin
            cnt      <= clk_cnt;
            clk_en_r <= 1'b1;
        end else begin
            cnt      <= cnt - 16'h0001;
            clk_en_r <= 1'b0;
        end
    end

    always @(posedge clk or negedge nReset) begin
        if (!nReset) begin
            cSCL_meta <= 1'b1;
            cSCL      <= 1'b1;
            cSDA_meta <= 1'b1;
            cSDA      <= 1'b1;
            fSCL      <= 3'b111;
            fSDA      <= 3'b111;
            filter_cnt <= 14'h0000;
            dSCL      <= 1'b1;
            dSDA      <= 1'b1;
        end else if (rst) begin
            cSCL_meta <= 1'b1;
            cSCL      <= 1'b1;
            cSDA_meta <= 1'b1;
            cSDA      <= 1'b1;
            fSCL      <= 3'b111;
            fSDA      <= 3'b111;
            filter_cnt <= 14'h0000;
            dSCL      <= 1'b1;
            dSDA      <= 1'b1;
        end else begin
            cSCL_meta <= scl_i;
            cSCL      <= cSCL_meta;
            cSDA_meta <= sda_i;
            cSDA      <= cSDA_meta;
            dSCL      <= sSCL;
            dSDA      <= sSDA;

            if (!ena) begin
                filter_cnt <= 14'h0000;
            end else if (filter_cnt == 14'h0000) begin
                filter_cnt <= clk_cnt[15:2];
                fSCL <= {fSCL[1:0], cSCL};
                fSDA <= {fSDA[1:0], cSDA};
            end else begin
                filter_cnt <= filter_cnt - 14'h0001;
            end
        end
    end

    always @(posedge clk or negedge nReset) begin
        if (!nReset) begin
            state   <= ST_IDLE;
            din_r   <= 1'b0;
            cmd_ack <= 1'b0;
            scl_oen <= 1'b1;
            sda_oen <= 1'b1;
        end else if (rst) begin
            state   <= ST_IDLE;
            din_r   <= 1'b0;
            cmd_ack <= 1'b0;
            scl_oen <= 1'b1;
            sda_oen <= 1'b1;
        end else begin
            cmd_ack <= 1'b0;

            if (al || arb_lost_now) begin
                state   <= ST_IDLE;
                scl_oen <= 1'b1;
                sda_oen <= 1'b1;
            end else if (ena && clk_en_r && !slave_wait_w) begin
                case (state)
                    ST_IDLE: begin
                        case (cmd)
                            4'h1: begin
                                state   <= ST_START_A;
                                scl_oen <= 1'b1;
                                sda_oen <= 1'b1;
                            end
                            4'h2: begin
                                state   <= ST_STOP_A;
                                scl_oen <= 1'b0;
                                sda_oen <= 1'b0;
                            end
                            4'h4: begin
                                state   <= ST_WRITE_A;
                                din_r   <= din;
                                scl_oen <= 1'b0;
                                sda_oen <= din;
                            end
                            4'h8: begin
                                state   <= ST_READ_A;
                                scl_oen <= 1'b0;
                                sda_oen <= 1'b1;
                            end
                            default: begin
                                state <= ST_IDLE;
                            end
                        endcase
                    end

                    ST_START_A: begin
                        state   <= ST_START_B;
                        scl_oen <= 1'b1;
                        sda_oen <= 1'b1;
                    end
                    ST_START_B: begin
                        state   <= ST_START_C;
                        scl_oen <= 1'b1;
                        sda_oen <= 1'b0;
                    end
                    ST_START_C: begin
                        state   <= ST_START_D;
                        scl_oen <= 1'b0;
                        sda_oen <= 1'b0;
                    end
                    ST_START_D: begin
                        state   <= ST_IDLE;
                        cmd_ack <= 1'b1;
                    end

                    ST_STOP_A: begin
                        state   <= ST_STOP_B;
                        scl_oen <= 1'b0;
                        sda_oen <= 1'b0;
                    end
                    ST_STOP_B: begin
                        state   <= ST_STOP_C;
                        scl_oen <= 1'b1;
                        sda_oen <= 1'b0;
                    end
                    ST_STOP_C: begin
                        state   <= ST_IDLE;
                        scl_oen <= 1'b1;
                        sda_oen <= 1'b1;
                        cmd_ack <= 1'b1;
                    end

                    ST_READ_A: begin
                        state   <= ST_READ_B;
                        scl_oen <= 1'b0;
                        sda_oen <= 1'b1;
                    end
                    ST_READ_B: begin
                        state   <= ST_READ_C;
                        scl_oen <= 1'b1;
                        sda_oen <= 1'b1;
                    end
                    ST_READ_C: begin
                        state   <= ST_IDLE;
                        scl_oen <= 1'b0;
                        sda_oen <= 1'b1;
                        cmd_ack <= 1'b1;
                    end

                    ST_WRITE_A: begin
                        state   <= ST_WRITE_B;
                        scl_oen <= 1'b0;
                        sda_oen <= din_r;
                    end
                    ST_WRITE_B: begin
                        state   <= ST_WRITE_C;
                        scl_oen <= 1'b1;
                        sda_oen <= din_r;
                    end
                    ST_WRITE_C: begin
                        state   <= ST_IDLE;
                        scl_oen <= 1'b0;
                        sda_oen <= din_r;
                        cmd_ack <= 1'b1;
                    end

                    default: begin
                        state <= ST_IDLE;
                    end
                endcase
            end
        end
    end

    always @(posedge clk or negedge nReset) begin
        if (!nReset) begin
            busy <= 1'b0;
            al   <= 1'b0;
            dout <= 1'b0;
        end else if (rst) begin
            busy <= 1'b0;
            al   <= 1'b0;
            dout <= 1'b0;
        end else begin
            if (sta_condition_w)
                busy <= 1'b1;
            else if (sto_condition_w)
                busy <= 1'b0;

            if (arb_lost_now)
                al <= 1'b1;

            if (sSCL && !dSCL)
                dout <= sSDA;
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
