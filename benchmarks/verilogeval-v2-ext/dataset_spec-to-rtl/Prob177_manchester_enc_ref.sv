module RefModule (
    input  logic       clk,
    input  logic       reset,
    input  logic       start,
    input  logic [7:0] data,
    output logic       man_out,
    output logic       out_valid,
    output logic       busy,
    output logic       done
);
    typedef enum logic [1:0] { ST_IDLE, ST_RUN, ST_DONE } state_t;
    state_t state;

    logic [7:0] latched;
    logic [2:0] bit_idx;
    logic       half; // 0=first half, 1=second half

    function automatic logic man_level(input logic bitval, input logic halfsel);
        // bit=0 -> 1 then 0; bit=1 -> 0 then 1
        if (!halfsel) man_level = ~bitval;
        else man_level = bitval;
    endfunction

    always_ff @(posedge clk) begin
        if (reset) begin
            state <= ST_IDLE;
            latched <= 8'd0;
            bit_idx <= 3'd0;
            half <= 1'b0;
            man_out <= 1'b1;
            out_valid <= 1'b0;
            busy <= 1'b0;
            done <= 1'b0;
        end else begin
            done <= 1'b0;

            case (state)
                ST_IDLE: begin
                    man_out <= 1'b1;
                    out_valid <= 1'b0;
                    busy <= 1'b0;
                    if (start) begin
                        latched <= data;
                        bit_idx <= 3'd7;
                        half <= 1'b0;
                        man_out <= man_level(data[7], 1'b0);
                        out_valid <= 1'b1;
                        busy <= 1'b1;
                        state <= ST_RUN;
                    end
                end
                ST_RUN: begin
                    out_valid <= 1'b1;
                    busy <= 1'b1;
                    man_out <= man_level(latched[bit_idx], half);

                    if (half == 1'b0) begin
                        half <= 1'b1;
                    end else begin
                        half <= 1'b0;
                        if (bit_idx == 3'd0) begin
                            out_valid <= 1'b0;
                            busy <= 1'b0;
                            man_out <= 1'b1;
                            state <= ST_DONE;
                        end else begin
                            bit_idx <= bit_idx - 3'd1;
                        end
                    end
                end
                ST_DONE: begin
                    done <= 1'b1;
                    man_out <= 1'b1;
                    out_valid <= 1'b0;
                    busy <= 1'b0;
                    state <= ST_IDLE;
                end
                default: state <= ST_IDLE;
            endcase
        end
    end
endmodule

