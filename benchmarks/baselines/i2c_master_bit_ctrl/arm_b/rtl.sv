module i2c_master_bit_ctrl (
    input  logic        clk,
    input  logic        rst,
    input  logic        nReset,
    input  logic        ena,
    input  logic [15:0] clk_cnt,
    input  logic [3:0]  cmd,
    output logic        cmd_ack,
    output logic        busy,
    output logic        al,
    input  logic        din,
    output logic        dout,
    input  logic        scl_i,
    output logic        scl_o,
    output logic        scl_oen,
    input  logic        sda_i,
    output logic        sda_o,
    output logic        sda_oen
);

    localparam logic [3:0] CMD_NOP   = 4'b0000;
    localparam logic [3:0] CMD_START = 4'b0001;
    localparam logic [3:0] CMD_STOP  = 4'b0010;
    localparam logic [3:0] CMD_READ  = 4'b0100;
    localparam logic [3:0] CMD_WRITE = 4'b1000;

    localparam logic [3:0] ST_IDLE   = 4'd0;
    localparam logic [3:0] ST_STA_A  = 4'd1;
    localparam logic [3:0] ST_STA_B  = 4'd2;
    localparam logic [3:0] ST_STA_C  = 4'd3;
    localparam logic [3:0] ST_STO_A  = 4'd4;
    localparam logic [3:0] ST_STO_B  = 4'd5;
    localparam logic [3:0] ST_STO_C  = 4'd6;
    localparam logic [3:0] ST_RD_A   = 4'd7;
    localparam logic [3:0] ST_RD_B   = 4'd8;
    localparam logic [3:0] ST_RD_C   = 4'd9;
    localparam logic [3:0] ST_WR_A   = 4'd10;
    localparam logic [3:0] ST_WR_B   = 4'd11;
    localparam logic [3:0] ST_WR_C   = 4'd12;

    logic [3:0] state;
    logic [3:0] cmd_latched;
    logic       din_latched;

    logic       scl_sync1;
    logic       scl_sync2;
    logic       sda_sync1;
    logic       sda_sync2;
    logic [2:0] scl_hist;
    logic [2:0] sda_hist;
    logic [15:0] filter_count;
    logic       filt_scl_d;
    logic       filt_sda_d;

    logic [15:0] count;
    logic        clk_en;
    logic        slave_wait;
    logic        scl_sync;
    logic        scl_rise;
    logic        sta_condition;
    logic        sto_condition;
    logic        unexpected_stop;
    logic        arbitration_loss;

    logic filt_scl;
    logic filt_sda;

    assign scl_o = 1'b0;
    assign sda_o = 1'b0;

    assign filt_scl = (scl_hist[2] & scl_hist[1]) |
                      (scl_hist[2] & scl_hist[0]) |
                      (scl_hist[1] & scl_hist[0]);

    assign filt_sda = (sda_hist[2] & sda_hist[1]) |
                      (sda_hist[2] & sda_hist[0]) |
                      (sda_hist[1] & sda_hist[0]);

    assign sta_condition = ~filt_sda & filt_sda_d & filt_scl;
    assign sto_condition = filt_sda & ~filt_sda_d & filt_scl;
    assign scl_rise = filt_scl & ~filt_scl_d;

    assign slave_wait = scl_oen & ~filt_scl;
    assign scl_sync = scl_oen & filt_scl_d & ~filt_scl;

    assign unexpected_stop = sto_condition &&
                             (state != ST_IDLE) &&
                             (state != ST_STO_A) &&
                             (state != ST_STO_B) &&
                             (state != ST_STO_C);

    assign arbitration_loss = unexpected_stop ||
                              ((state == ST_WR_B) &&
                               din_latched &&
                               filt_scl &&
                               ~filt_sda);

    assign clk_en = ena && !slave_wait && !scl_sync &&
                    (count == 16'd0);

    always @(*) begin
        scl_oen = 1'b1;
        sda_oen = 1'b1;

        case (state)
            ST_STA_B: begin
                scl_oen = 1'b1;
                sda_oen = 1'b0;
            end

            ST_STA_C: begin
                scl_oen = 1'b0;
                sda_oen = 1'b0;
            end

            ST_STO_A: begin
                scl_oen = 1'b0;
                sda_oen = 1'b0;
            end

            ST_STO_B: begin
                scl_oen = 1'b1;
                sda_oen = 1'b0;
            end

            ST_STO_C: begin
                scl_oen = 1'b1;
                sda_oen = 1'b1;
            end

            ST_RD_A: begin
                scl_oen = 1'b0;
                sda_oen = 1'b1;
            end

            ST_RD_B: begin
                scl_oen = 1'b1;
                sda_oen = 1'b1;
            end

            ST_RD_C: begin
                scl_oen = 1'b0;
                sda_oen = 1'b1;
            end

            ST_WR_A: begin
                scl_oen = 1'b0;
                sda_oen = ~din_latched;
            end

            ST_WR_B: begin
                scl_oen = 1'b1;
                sda_oen = ~din_latched;
            end

            ST_WR_C: begin
                scl_oen = 1'b0;
                sda_oen = ~din_latched;
            end

            default: begin
                scl_oen = 1'b1;
                sda_oen = 1'b1;
            end
        endcase
    end

    always @(posedge clk or negedge nReset) begin
        if (!nReset) begin
            scl_sync1   <= 1'b1;
            scl_sync2   <= 1'b1;
            sda_sync1   <= 1'b1;
            sda_sync2   <= 1'b1;
            scl_hist    <= 3'b111;
            sda_hist    <= 3'b111;
            filter_count <= 16'd0;
            filt_scl_d  <= 1'b1;
            filt_sda_d  <= 1'b1;
        end else if (rst) begin
            scl_sync1   <= 1'b1;
            scl_sync2   <= 1'b1;
            sda_sync1   <= 1'b1;
            sda_sync2   <= 1'b1;
            scl_hist    <= 3'b111;
            sda_hist    <= 3'b111;
            filter_count <= 16'd0;
            filt_scl_d  <= 1'b1;
            filt_sda_d  <= 1'b1;
        end else begin
            scl_sync1 <= scl_i;
            scl_sync2 <= scl_sync1;
            sda_sync1 <= sda_i;
            sda_sync2 <= sda_sync1;

            if (!ena) begin
                filter_count <= 16'd0;
            end else begin
                if (filter_count == 16'd0) begin
                    scl_hist     <= {scl_hist[1:0], scl_sync2};
                    sda_hist     <= {sda_hist[1:0], sda_sync2};
                    filter_count <= clk_cnt >> 2;
                end else begin
                    filter_count <= filter_count - 16'd1;
                end

                filt_scl_d <= filt_scl;
                filt_sda_d <= filt_sda;
            end
        end
    end

    always @(posedge clk or negedge nReset) begin
        if (!nReset) begin
            count <= 16'd0;
        end else if (rst) begin
            count <= 16'd0;
        end else if (!ena) begin
            count <= clk_cnt;
        end else if (scl_sync) begin
            count <= clk_cnt;
        end else if (slave_wait) begin
            count <= count;
        end else if (count == 16'd0) begin
            count <= clk_cnt;
        end else begin
            count <= count - 16'd1;
        end
    end

    always @(posedge clk or negedge nReset) begin
        if (!nReset) begin
            busy <= 1'b0;
        end else if (rst) begin
            busy <= 1'b0;
        end else if (sta_condition) begin
            busy <= 1'b1;
        end else if (sto_condition) begin
            busy <= 1'b0;
        end
    end

    always @(posedge clk or negedge nReset) begin
        if (!nReset) begin
            dout <= 1'b0;
        end else if (rst) begin
            dout <= 1'b0;
        end else if (ena && scl_rise) begin
            dout <= filt_sda;
        end
    end

    always @(posedge clk or negedge nReset) begin
        if (!nReset) begin
            state       <= ST_IDLE;
            cmd_latched <= CMD_NOP;
            din_latched <= 1'b0;
            cmd_ack     <= 1'b0;
            al          <= 1'b0;
        end else if (rst) begin
            state       <= ST_IDLE;
            cmd_latched <= CMD_NOP;
            din_latched <= 1'b0;
            cmd_ack     <= 1'b0;
            al          <= 1'b0;
        end else begin
            cmd_ack <= 1'b0;

            if (ena && arbitration_loss) begin
                state <= ST_IDLE;
                al    <= 1'b1;
            end else if (ena && clk_en && !al) begin
                case (state)
                    ST_IDLE: begin
                        case (cmd)
                            CMD_START: begin
                                cmd_latched <= CMD_START;
                                din_latched <= din;
                                state       <= ST_STA_A;
                            end

                            CMD_STOP: begin
                                cmd_latched <= CMD_STOP;
                                din_latched <= din;
                                state       <= ST_STO_A;
                            end

                            CMD_READ: begin
                                cmd_latched <= CMD_READ;
                                din_latched <= din;
                                state       <= ST_RD_A;
                            end

                            CMD_WRITE: begin
                                cmd_latched <= CMD_WRITE;
                                din_latched <= din;
                                state       <= ST_WR_A;
                            end

                            default: begin
                                state <= ST_IDLE;
                            end
                        endcase
                    end

                    ST_STA_A: state <= ST_STA_B;

                    ST_STA_B: state <= ST_STA_C;

                    ST_STA_C: begin
                        state   <= ST_IDLE;
                        cmd_ack <= 1'b1;
                    end

                    ST_STO_A: state <= ST_STO_B;

                    ST_STO_B: begin
                        if (filt_scl) begin
                            state <= ST_STO_C;
                        end
                    end

                    ST_STO_C: begin
                        state   <= ST_IDLE;
                        cmd_ack <= 1'b1;
                    end

                    ST_RD_A: state <= ST_RD_B;

                    ST_RD_B: begin
                        if (filt_scl) begin
                            state <= ST_RD_C;
                        end
                    end

                    ST_RD_C: begin
                        state   <= ST_IDLE;
                        cmd_ack <= 1'b1;
                    end

                    ST_WR_A: state <= ST_WR_B;

                    ST_WR_B: begin
                        if (filt_scl) begin
                            state <= ST_WR_C;
                        end
                    end

                    ST_WR_C: begin
                        state   <= ST_IDLE;
                        cmd_ack <= 1'b1;
                    end

                    default: state <= ST_IDLE;
                endcase
            end
        end
    end

endmodule