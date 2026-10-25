module i2c_master_bit_ctrl (
    input         clk,
    input         rst,
    input         nReset,
    input         ena,
    input  [15:0] clk_cnt,
    input  [3:0]  cmd,
    input         din,
    input         scl_i,
    input         sda_i,
    output reg    cmd_ack,
    output reg    busy,
    output reg    al,
    output reg    dout,
    output        scl_o,
    output reg    scl_oen,
    output        sda_o,
    output reg    sda_oen,
    output        idle,
    output        fsm_active,
    output        in_start_sequence,
    output        in_stop_sequence,
    output        in_read_sequence,
    output        in_write_sequence,
    output        write_stable_high_phase,
    output        read_sample_window,
    output        cscl,
    output        csda,
    output        filter_cnt_expired,
    output [2:0]  fscl,
    output [2:0]  fsda,
    output        sscl,
    output        ssda,
    output        dscl,
    output        dsda,
    output        sscl_rise,
    output        sta_condition,
    output        sto_condition,
    output        slave_wait,
    output        scl_sync,
    output        cnt_zero,
    output        clk_en,
    output        sda_chk
);

    localparam [3:0] ST_IDLE    = 4'd0,
                     ST_START_A = 4'd1,
                     ST_START_B = 4'd2,
                     ST_START_C = 4'd3,
                     ST_START_D = 4'd4,
                     ST_START_E = 4'd5,
                     ST_STOP_A  = 4'd6,
                     ST_STOP_B  = 4'd7,
                     ST_STOP_C  = 4'd8,
                     ST_READ_A  = 4'd9,
                     ST_READ_B  = 4'd10,
                     ST_READ_C  = 4'd11,
                     ST_WRITE_A = 4'd12,
                     ST_WRITE_B = 4'd13,
                     ST_WRITE_C = 4'd14;

    reg [3:0] state;
    reg [15:0] cnt_r;
    reg        clk_en_r;
    reg [15:0] filter_cnt_r;
    reg [2:0]  fscl_hist, fsda_hist;
    reg        cscl_meta, csda_meta;
    reg        cscl_r, csda_r;
    reg        sscl_r, ssda_r;
    reg        dscl_r, dsda_r;
    reg        sda_chk_r;

    wire sscl_rise_int;
    wire sta_condition_int;
    wire sto_condition_int;
    wire slave_wait_int;
    wire scl_sync_int;
    wire cnt_zero_int;
    wire filter_cnt_expired_int;
    wire active_int;
    wire stop_sequence_int;
    wire arbitration_event_int;

    assign sscl_r = (fscl_hist[2] & fscl_hist[1]) |
                    (fscl_hist[2] & fscl_hist[0]) |
                    (fscl_hist[1] & fscl_hist[0]);
    assign ssda_r = (fsda_hist[2] & fsda_hist[1]) |
                    (fsda_hist[2] & fsda_hist[0]) |
                    (fsda_hist[1] & fsda_hist[0]);

    assign sscl_rise_int = sscl_r & ~dscl_r;
    assign sta_condition_int = ~ssda_r & dsda_r & sscl_r;
    assign sto_condition_int = ssda_r & ~dsda_r & sscl_r;
    assign slave_wait_int = scl_oen & ~sscl_r;
    assign scl_sync_int = scl_oen & dscl_r & ~sscl_r;
    assign cnt_zero_int = (cnt_r == 16'h0000);
    assign filter_cnt_expired_int = ena & (filter_cnt_r == 16'h0000);
    assign active_int = (state != ST_IDLE);
    assign stop_sequence_int = (state == ST_STOP_A) ||
                               (state == ST_STOP_B) ||
                               (state == ST_STOP_C);
    assign arbitration_event_int = (sda_chk_r & ~ssda_r) |
                                  (sto_condition_int & active_int &
                                   ~stop_sequence_int);

    assign scl_o = 1'b0;
    assign sda_o = 1'b0;

    assign idle = (state == ST_IDLE);
    assign fsm_active = active_int;
    assign in_start_sequence = (state == ST_START_A) ||
                               (state == ST_START_B) ||
                               (state == ST_START_C) ||
                               (state == ST_START_D) ||
                               (state == ST_START_E);
    assign in_stop_sequence = stop_sequence_int;
    assign in_read_sequence = (state == ST_READ_A) ||
                              (state == ST_READ_B) ||
                              (state == ST_READ_C);
    assign in_write_sequence = (state == ST_WRITE_A) ||
                               (state == ST_WRITE_B) ||
                               (state == ST_WRITE_C);
    assign write_stable_high_phase = (state == ST_WRITE_C);
    assign read_sample_window = (state == ST_READ_C);
    assign cscl = cscl_r;
    assign csda = csda_r;
    assign filter_cnt_expired = filter_cnt_expired_int;
    assign fscl = fscl_hist;
    assign fsda = fsda_hist;
    assign sscl = sscl_r;
    assign ssda = ssda_r;
    assign dscl = dscl_r;
    assign dsda = dsda_r;
    assign sscl_rise = sscl_rise_int;
    assign sta_condition = sta_condition_int;
    assign sto_condition = sto_condition_int;
    assign slave_wait = slave_wait_int;
    assign scl_sync = scl_sync_int;
    assign cnt_zero = cnt_zero_int;
    assign clk_en = clk_en_r;
    assign sda_chk = sda_chk_r;

    always @(posedge clk or negedge nReset) begin
        if (!nReset) begin
            cscl_meta <= 1'b1;
            csda_meta <= 1'b1;
            cscl_r <= 1'b1;
            csda_r <= 1'b1;
        end else if (rst) begin
            cscl_meta <= 1'b1;
            csda_meta <= 1'b1;
            cscl_r <= 1'b1;
            csda_r <= 1'b1;
        end else begin
            cscl_meta <= scl_i;
            csda_meta <= sda_i;
            cscl_r <= cscl_meta;
            csda_r <= csda_meta;
        end
    end

    always @(posedge clk or negedge nReset) begin
        if (!nReset) begin
            filter_cnt_r <= 16'h0000;
            fscl_hist <= 3'b111;
            fsda_hist <= 3'b111;
        end else if (rst) begin
            filter_cnt_r <= 16'h0000;
            fscl_hist <= 3'b111;
            fsda_hist <= 3'b111;
        end else if (!ena) begin
            filter_cnt_r <= 16'h0000;
        end else if (filter_cnt_r == 16'h0000) begin
            filter_cnt_r <= clk_cnt >> 2;
            fscl_hist <= {fscl_hist[1:0], cscl_r};
            fsda_hist <= {fsda_hist[1:0], csda_r};
        end else begin
            filter_cnt_r <= filter_cnt_r - 16'h0001;
        end
    end

    always @(posedge clk or negedge nReset) begin
        if (!nReset) begin
            dscl_r <= 1'b1;
            dsda_r <= 1'b1;
        end else if (rst) begin
            dscl_r <= 1'b1;
            dsda_r <= 1'b1;
        end else begin
            dscl_r <= sscl_r;
            dsda_r <= ssda_r;
        end
    end

    always @(posedge clk or negedge nReset) begin
        if (!nReset) begin
            cnt_r <= 16'h0000;
            clk_en_r <= 1'b1;
        end else if (rst) begin
            cnt_r <= clk_cnt;
            clk_en_r <= 1'b1;
        end else if (!ena) begin
            cnt_r <= clk_cnt;
            clk_en_r <= 1'b1;
        end else if (scl_sync_int || cnt_zero_int) begin
            cnt_r <= clk_cnt;
            clk_en_r <= 1'b1;
        end else if (slave_wait_int) begin
            cnt_r <= cnt_r;
            clk_en_r <= 1'b0;
        end else begin
            cnt_r <= cnt_r - 16'h0001;
            clk_en_r <= 1'b0;
        end
    end

    always @(posedge clk or negedge nReset) begin
        if (!nReset) begin
            dout <= 1'b0;
        end else if (rst) begin
            dout <= 1'b0;
        end else if (sscl_rise_int) begin
            dout <= ssda_r;
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
            al <= 1'b0;
        end else if (rst) begin
            al <= 1'b0;
        end else if (arbitration_event_int) begin
            al <= 1'b1;
        end
    end

    initial begin
        state = ST_IDLE;
        cmd_ack = 1'b0;
        scl_oen = 1'b1;
        sda_oen = 1'b1;
        sda_chk_r = 1'b0;
    end

    always @(posedge clk or negedge nReset) begin
        if (!nReset) begin
            state <= ST_IDLE;
            cmd_ack <= 1'b0;
            scl_oen <= 1'b1;
            sda_oen <= 1'b1;
            sda_chk_r <= 1'b0;
        end else if (rst) begin
            state <= ST_IDLE;
            cmd_ack <= 1'b0;
            scl_oen <= 1'b1;
            sda_oen <= 1'b1;
            sda_chk_r <= 1'b0;
        end else begin
            cmd_ack <= 1'b0;
            if (al || (state == ST_WRITE_C && sda_chk_r && !ssda_r) ||
                (sto_condition_int && active_int && !stop_sequence_int)) begin
                state <= ST_IDLE;
                scl_oen <= 1'b1;
                sda_oen <= 1'b1;
                sda_chk_r <= 1'b0;
            end else if (!slave_wait_int) begin
                case (state)
                    ST_IDLE: begin
                        sda_chk_r <= 1'b0;
                        if (ena && clk_en_r) begin
                            case (cmd)
                                4'h1: state <= ST_START_A;
                                4'h2: state <= ST_STOP_A;
                                4'h4: state <= ST_WRITE_A;
                                4'h8: state <= ST_READ_A;
                                default: state <= ST_IDLE;
                            endcase
                        end
                    end
                    ST_START_A: begin
                        if (ena && clk_en_r) begin
                            sda_oen <= 1'b1;
                            state <= ST_START_B;
                        end
                    end
                    ST_START_B: begin
                        if (ena && clk_en_r) begin
                            scl_oen <= 1'b1;
                            state <= ST_START_C;
                        end
                    end
                    ST_START_C: begin
                        if (ena && clk_en_r) begin
                            sda_oen <= 1'b0;
                            state <= ST_START_D;
                        end
                    end
                    ST_START_D: begin
                        if (ena && clk_en_r) begin
                            scl_oen <= 1'b0;
                            state <= ST_START_E;
                        end
                    end
                    ST_START_E: begin
                        if (ena && clk_en_r) begin
                            cmd_ack <= 1'b1;
                            state <= ST_IDLE;
                        end
                    end
                    ST_STOP_A: begin
                        if (ena && clk_en_r) begin
                            sda_oen <= 1'b0;
                            state <= ST_STOP_B;
                        end
                    end
                    ST_STOP_B: begin
                        if (ena && clk_en_r) begin
                            scl_oen <= 1'b1;
                            state <= ST_STOP_C;
                        end
                    end
                    ST_STOP_C: begin
                        if (ena && clk_en_r) begin
                            sda_oen <= 1'b1;
                            cmd_ack <= 1'b1;
                            state <= ST_IDLE;
                        end
                    end
                    ST_READ_A: begin
                        if (ena && clk_en_r) begin
                            sda_oen <= 1'b1;
                            state <= ST_READ_B;
                        end
                    end
                    ST_READ_B: begin
                        if (ena && clk_en_r) begin
                            scl_oen <= 1'b1;
                            state <= ST_READ_C;
                        end
                    end
                    ST_READ_C: begin
                        if (ena && clk_en_r) begin
                            scl_oen <= 1'b0;
                            cmd_ack <= 1'b1;
                            state <= ST_IDLE;
                        end
                    end
                    ST_WRITE_A: begin
                        if (ena && clk_en_r) begin
                            sda_oen <= din;
                            state <= ST_WRITE_B;
                        end
                    end
                    ST_WRITE_B: begin
                        if (ena && clk_en_r) begin
                            scl_oen <= 1'b1;
                            sda_chk_r <= 1'b1;
                            state <= ST_WRITE_C;
                        end
                    end
                    ST_WRITE_C: begin
                        if (ena && clk_en_r) begin
                            scl_oen <= 1'b0;
                            sda_chk_r <= 1'b0;
                            cmd_ack <= 1'b1;
                            state <= ST_IDLE;
                        end
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