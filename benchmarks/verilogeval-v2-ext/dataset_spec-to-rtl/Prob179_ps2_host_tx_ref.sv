module RefModule (
    input  logic       clk,
    input  logic       reset,
    input  logic       start,
    input  logic [7:0] data,
    input  logic       ps2_data_in,
    output logic       ps2_clk_oe,
    output logic       ps2_data_oe,
    output logic       busy,
    output logic       done,
    output logic       ack_error
);
    typedef enum logic [3:0] {
        ST_IDLE,
        ST_INHIBIT,
        ST_BIT_LOW,
        ST_BIT_HIGH,
        ST_ACK_LOW,
        ST_ACK_HIGH,
        ST_DONE
    } state_t;

    state_t state;

    logic [7:0] latched;
    logic [3:0] inhibit_cnt;
    logic [3:0] frame_idx; // 0..10
    logic       parity_bit;

    function automatic logic frame_bit(input logic [7:0] d, input logic parity, input int unsigned idx);
        if (idx == 0) frame_bit = 1'b0;               // start
        else if (idx >= 1 && idx <= 8) frame_bit = d[idx-1]; // data[0]..data[7]
        else if (idx == 9) frame_bit = parity;        // parity
        else frame_bit = 1'b1;                        // stop
    endfunction

    always_ff @(posedge clk) begin
        if (reset) begin
            state <= ST_IDLE;
            latched <= 8'd0;
            inhibit_cnt <= 4'd0;
            frame_idx <= 4'd0;
            parity_bit <= 1'b0;
            done <= 1'b0;
            ack_error <= 1'b0;
        end else begin
            done <= 1'b0;

            case (state)
                ST_IDLE: begin
                    if (start) begin
                        latched <= data;
                        parity_bit <= ~(^data); // odd parity
                        inhibit_cnt <= 4'd0;
                        frame_idx <= 4'd0;
                        ack_error <= 1'b0;
                        state <= ST_INHIBIT;
                    end
                end
                ST_INHIBIT: begin
                    if (inhibit_cnt == 4'd3) begin
                        inhibit_cnt <= 4'd0;
                        state <= ST_BIT_LOW;
                    end else begin
                        inhibit_cnt <= inhibit_cnt + 4'd1;
                    end
                end
                ST_BIT_LOW: begin
                    state <= ST_BIT_HIGH;
                end
                ST_BIT_HIGH: begin
                    if (frame_idx == 4'd10) begin
                        state <= ST_ACK_LOW;
                    end else begin
                        frame_idx <= frame_idx + 4'd1;
                        state <= ST_BIT_LOW;
                    end
                end
                ST_ACK_LOW: state <= ST_ACK_HIGH;
                ST_ACK_HIGH: begin
                    if (ps2_data_in) ack_error <= 1'b1;
                    state <= ST_DONE;
                end
                ST_DONE: begin
                    done <= 1'b1;
                    state <= ST_IDLE;
                end
                default: state <= ST_IDLE;
            endcase
        end
    end

    always_comb begin
        ps2_clk_oe = 1'b0;
        ps2_data_oe = 1'b0;

        case (state)
            ST_IDLE: begin
                ps2_clk_oe = 1'b0;
                ps2_data_oe = 1'b0;
            end
            ST_INHIBIT: begin
                ps2_clk_oe = 1'b1;
                ps2_data_oe = 1'b0;
            end
            ST_BIT_LOW: begin
                ps2_clk_oe = 1'b1;
                ps2_data_oe = (frame_bit(latched, parity_bit, frame_idx) == 1'b0);
            end
            ST_BIT_HIGH: begin
                ps2_clk_oe = 1'b0;
                ps2_data_oe = (frame_bit(latched, parity_bit, frame_idx) == 1'b0);
            end
            ST_ACK_LOW: begin
                ps2_clk_oe = 1'b1;
                ps2_data_oe = 1'b0;
            end
            ST_ACK_HIGH: begin
                ps2_clk_oe = 1'b0;
                ps2_data_oe = 1'b0;
            end
            ST_DONE: begin
                ps2_clk_oe = 1'b0;
                ps2_data_oe = 1'b0;
            end
            default: begin
                ps2_clk_oe = 1'b0;
                ps2_data_oe = 1'b0;
            end
        endcase
    end

    assign busy = (state != ST_IDLE) && (state != ST_DONE);
endmodule

