module RefModule (
    input  logic       clk,
    input  logic       reset,
    input  logic       start,
    input  logic [6:0] addr,
    input  logic [7:0] data,
    input  logic       sda_in,
    output logic       scl_oe,
    output logic       sda_oe,
    output logic       busy,
    output logic       done,
    output logic       ack_error
);
    typedef enum logic [3:0] {
        ST_IDLE,
        ST_START0,
        ST_START1,
        ST_BIT_LOW,
        ST_BIT_HIGH,
        ST_ACK_LOW,
        ST_ACK_HIGH,
        ST_STOP0,
        ST_STOP1,
        ST_STOP2,
        ST_DONE
    } state_t;

    state_t state;

    logic [7:0] addr_byte;
    logic [7:0] data_byte;
    logic       byte_sel;   // 0=addr_byte, 1=data_byte
    logic [2:0] bit_idx;

    function automatic logic get_cur_bit();
        if (byte_sel == 1'b0) begin
            get_cur_bit = addr_byte[bit_idx];
        end else begin
            get_cur_bit = data_byte[bit_idx];
        end
    endfunction

    always_ff @(posedge clk) begin
        if (reset) begin
            state <= ST_IDLE;
            addr_byte <= 8'd0;
            data_byte <= 8'd0;
            byte_sel <= 1'b0;
            bit_idx <= 3'd0;
            ack_error <= 1'b0;
            done <= 1'b0;
        end else begin
            done <= 1'b0;

            case (state)
                ST_IDLE: begin
                    if (start) begin
                        addr_byte <= {addr, 1'b0}; // write
                        data_byte <= data;
                        byte_sel <= 1'b0;
                        bit_idx <= 3'd7;
                        ack_error <= 1'b0;
                        state <= ST_START0;
                    end
                end
                ST_START0: state <= ST_START1;
                ST_START1: state <= ST_BIT_LOW;
                ST_BIT_LOW: state <= ST_BIT_HIGH;
                ST_BIT_HIGH: begin
                    if (bit_idx == 3'd0) begin
                        state <= ST_ACK_LOW;
                    end else begin
                        bit_idx <= bit_idx - 3'd1;
                        state <= ST_BIT_LOW;
                    end
                end
                ST_ACK_LOW: state <= ST_ACK_HIGH;
                ST_ACK_HIGH: begin
                    if (sda_in) begin
                        ack_error <= 1'b1;
                    end
                    if (byte_sel == 1'b0) begin
                        byte_sel <= 1'b1;
                        bit_idx <= 3'd7;
                        state <= ST_BIT_LOW;
                    end else begin
                        state <= ST_STOP0;
                    end
                end
                ST_STOP0: state <= ST_STOP1;
                ST_STOP1: state <= ST_STOP2;
                ST_STOP2: state <= ST_DONE;
                ST_DONE: begin
                    done <= 1'b1;
                    state <= ST_IDLE;
                end
                default: state <= ST_IDLE;
            endcase
        end
    end

    always_comb begin
        // Defaults: release lines
        scl_oe = 1'b0;
        sda_oe = 1'b0;

        case (state)
            ST_IDLE: begin
                scl_oe = 1'b0;
                sda_oe = 1'b0;
            end
            ST_START0: begin
                scl_oe = 1'b0;
                sda_oe = 1'b1;
            end
            ST_START1: begin
                scl_oe = 1'b1;
                sda_oe = 1'b1;
            end
            ST_BIT_LOW: begin
                scl_oe = 1'b1;
                sda_oe = (get_cur_bit() == 1'b0);
            end
            ST_BIT_HIGH: begin
                scl_oe = 1'b0;
                sda_oe = (get_cur_bit() == 1'b0);
            end
            ST_ACK_LOW: begin
                scl_oe = 1'b1;
                sda_oe = 1'b0;
            end
            ST_ACK_HIGH: begin
                scl_oe = 1'b0;
                sda_oe = 1'b0;
            end
            ST_STOP0: begin
                scl_oe = 1'b1;
                sda_oe = 1'b1;
            end
            ST_STOP1: begin
                scl_oe = 1'b0;
                sda_oe = 1'b1;
            end
            ST_STOP2: begin
                scl_oe = 1'b0;
                sda_oe = 1'b0;
            end
            ST_DONE: begin
                scl_oe = 1'b0;
                sda_oe = 1'b0;
            end
            default: begin
                scl_oe = 1'b0;
                sda_oe = 1'b0;
            end
        endcase
    end

    assign busy = (state != ST_IDLE) && (state != ST_DONE);
endmodule

