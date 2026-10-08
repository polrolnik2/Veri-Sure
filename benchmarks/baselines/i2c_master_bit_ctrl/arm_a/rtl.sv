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

    localparam logic [3:0] CMD_START = 4'b0001;
    localparam logic [3:0] CMD_STOP  = 4'b0010;
    localparam logic [3:0] CMD_WRITE = 4'b0100;
    localparam logic [3:0] CMD_READ  = 4'b1000;

    localparam logic [3:0] ST_IDLE    = 4'd0;
    localparam logic [3:0] ST_START_A = 4'd1;
    localparam logic [3:0] ST_START_B = 4'd2;
    localparam logic [3:0] ST_STOP_A  = 4'd3;
    localparam logic [3:0] ST_STOP_B  = 4'd4;
    localparam logic [3:0] ST_WRITE_A = 4'd5;
    localparam logic [3:0] ST_WRITE_B = 4'd6;
    localparam logic [3:0] ST_WRITE_C = 4'd7;
    localparam logic [3:0] ST_READ_A  = 4'd8;
    localparam logic [3:0] ST_READ_B  = 4'd9;
    localparam logic [3:0] ST_READ_C  = 4'd10;

    logic [3:0] state;
    logic       write_bit;

    logic [15:0] cnt;
    logic [15:0] filter_cnt;

    logic       scl_sync1;
    logic       scl_sync2;
    logic       sda_sync1;
    logic       sda_sync2;

    logic [2:0] scl_hist;
    logic [2:0] sda_hist;
    logic       scl_filt;
    logic       sda_filt;
    logic       scl_filt_d;
    logic       sda_filt_d;

    logic [2:0] scl_hist_next;
    logic [2:0] sda_hist_next;
    logic       scl_value_next;
    logic       sda_value_next;

    logic filter_tick;
    logic scl_rise_event;
    logic scl_fall_event;
    logic sda_fall_event;
    logic sda_rise_event;
    logic start_event;
    logic stop_event;
    logic slave_wait;
    logic clk_en;

    function automatic logic majority3(input logic [2:0] value);
        majority3 = (value[2] & value[1]) |
                    (value[2] & value[0]) |
                    (value[1] & value[0]);
    endfunction

    assign scl_o = 1'b0;
    assign sda_o = 1'b0;

    assign scl_hist_next  = {scl_hist[1:0], scl_sync2};
    assign sda_hist_next  = {sda_hist[1:0], sda_sync2};
    assign scl_value_next = majority3(scl_hist_next);
    assign sda_value_next = majority3(sda_hist_next);

    assign filter_tick = ena && (filter_cnt == 16'd0);

    assign scl_rise_event = filter_tick &&
                            scl_value_next && !scl_filt;
    assign scl_fall_event = filter_tick &&
                            !scl_value_next && scl_filt;
    assign sda_fall_event = filter_tick &&
                            !sda_value_next && sda_filt;
    assign sda_rise_event = filter_tick &&
                            sda_value_next && !sda_filt;

    assign start_event = sda_fall_event && scl_filt;
    assign stop_event  = sda_rise_event && scl_filt;

    assign slave_wait = ena &&
                        (state != ST_IDLE) &&
                        scl_oen &&
                        !scl_filt;

    assign clk_en = ena &&
                    !slave_wait &&
                    !(scl_fall_event && scl_oen) &&
                    (cnt == 16'd0);

always @(posedge clk or negedge nReset or posedge rst) begin
        if (!nReset) begin
            state       = ST_IDLE;
            write_bit   = 1'b0;

            cnt         = 16'd0;
            filter_cnt  = 16'd0;

            scl_sync1   = 1'b1;
            scl_sync2   = 1'b1;
            sda_sync1   = 1'b1;
            sda_sync2   = 1'b1;

            scl_hist    = 3'b111;
            sda_hist    = 3'b111;
            scl_filt    = 1'b1;
            sda_filt    = 1'b1;
            scl_filt_d  = 1'b1;
            sda_filt_d  = 1'b1;

            cmd_ack     = 1'b0;
            busy        = 1'b0;
            al          = 1'b0;
            dout        = 1'b0;

            scl_oen     = 1'b1;
            sda_oen     = 1'b1;
        end
        else if (rst) begin
            state       <= ST_IDLE;
            write_bit   <= 1'b0;
            cnt         <= 16'd0;
            filter_cnt  <= 16'd0;
            scl_sync1   <= 1'b1;
            scl_sync2   <= 1'b1;
            sda_sync1   <= 1'b1;
            sda_sync2   <= 1'b1;
            scl_hist    <= 3'b111;
            sda_hist    <= 3'b111;
            scl_filt    <= 1'b1;
            sda_filt    <= 1'b1;
            scl_filt_d  <= 1'b1;
            sda_filt_d  <= 1'b1;
            cmd_ack     <= 1'b0;
            busy        <= 1'b0;
            al          <= 1'b0;
            dout        <= 1'b0;
            scl_oen     <= 1'b1;
            sda_oen     <= 1'b1;
        end
        else begin
            cmd_ack <= 1'b0;
            scl_sync1 <= scl_i;
            scl_sync2 <= scl_sync1;
            sda_sync1 <= sda_i;
            sda_sync2 <= sda_sync1;
            if (!ena) begin
                filter_cnt <= 16'd0;
            end else if (filter_tick) begin
                filter_cnt <= clk_cnt >> 2;
                scl_hist <= scl_hist_next;
                sda_hist <= sda_hist_next;
                scl_filt_d <= scl_filt;
                sda_filt_d <= sda_filt;
                scl_filt <= scl_value_next;
                sda_filt <= sda_value_next;
            end else begin
                filter_cnt <= filter_cnt - 16'd1;
            end
            if (!ena) cnt <= clk_cnt;
            else if (slave_wait) cnt <= cnt;
            else if (scl_fall_event && scl_oen) cnt <= clk_cnt;
            else if (cnt == 16'd0) cnt <= clk_cnt;
            else cnt <= cnt - 16'd1;
            if (scl_rise_event) dout <= sda_filt;
            if (al) begin
                state <= ST_IDLE;
                scl_oen <= 1'b1;
                sda_oen <= 1'b1;
            end else if (!ena) begin
                if (state == ST_IDLE) begin
                    scl_oen <= 1'b1;
                    sda_oen <= 1'b1;
                end
            end else begin
                if (start_event) busy <= 1'b1;
                if (stop_event) busy <= 1'b0;
                if (stop_event && (state != ST_IDLE) && (state != ST_STOP_A) && (state != ST_STOP_B)) begin
                    state <= ST_IDLE;
                    al <= 1'b1;
                    scl_oen <= 1'b1;
                    sda_oen <= 1'b1;
                end else begin
                    case (state)
                        ST_IDLE: begin
                            if (clk_en) begin
                                case (cmd)
                                    CMD_START: begin state <= ST_START_A; scl_oen <= 1'b1; sda_oen <= 1'b1; end
                                    CMD_STOP: begin state <= ST_STOP_A; scl_oen <= 1'b0; sda_oen <= 1'b0; end
                                    CMD_WRITE: begin state <= ST_WRITE_A; write_bit <= din; scl_oen <= 1'b0; sda_oen <= din; end
                                    CMD_READ: begin state <= ST_READ_A; scl_oen <= 1'b0; sda_oen <= 1'b1; end
                                    default: state <= ST_IDLE;
                                endcase
                            end
                        end
                        ST_START_A: if (clk_en && scl_filt) begin state <= ST_START_B; scl_oen <= 1'b1; sda_oen <= 1'b0; end
                        ST_START_B: if (clk_en) begin state <= ST_IDLE; scl_oen <= 1'b0; sda_oen <= 1'b0; cmd_ack <= 1'b1; end
                        ST_STOP_A: if (clk_en) begin state <= ST_STOP_B; scl_oen <= 1'b1; sda_oen <= 1'b0; end
                        ST_STOP_B: if (clk_en && scl_filt) begin state <= ST_IDLE; scl_oen <= 1'b1; sda_oen <= 1'b1; cmd_ack <= 1'b1; end
                        ST_WRITE_A: if (clk_en && !scl_filt) begin state <= ST_WRITE_B; scl_oen <= 1'b1; end
                        ST_WRITE_B: if (clk_en && (scl_rise_event || scl_filt)) state <= ST_WRITE_C;
                        ST_WRITE_C: if (clk_en) begin
                            if (write_bit && !sda_filt) begin state <= ST_IDLE; al <= 1'b1; scl_oen <= 1'b1; sda_oen <= 1'b1; end
                            else begin state <= ST_IDLE; scl_oen <= 1'b0; sda_oen <= write_bit; cmd_ack <= 1'b1; end
                        end
                        ST_READ_A: if (clk_en && !scl_filt) begin state <= ST_READ_B; scl_oen <= 1'b1; sda_oen <= 1'b1; end
                        ST_READ_B: if (clk_en && (scl_rise_event || scl_filt)) begin state <= ST_READ_C; dout <= sda_filt; end
                        ST_READ_C: if (clk_en) begin state <= ST_IDLE; scl_oen <= 1'b0; sda_oen <= 1'b1; cmd_ack <= 1'b1; end
                        default: begin state <= ST_IDLE; scl_oen <= 1'b1; sda_oen <= 1'b1; end
                    endcase
                end
            end
        end
    end

endmodule