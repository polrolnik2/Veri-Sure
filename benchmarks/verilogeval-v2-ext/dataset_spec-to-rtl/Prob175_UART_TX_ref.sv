module RefModule (
    input        clk,
    input        rstn,
    input        rx,
    output reg [7:0] rx_data,
    output reg       done
);

    localparam integer CLKS_PER_BIT = 100_000_000 / 9600; // 10416 cycles @100MHz

    localparam [2:0] S_IDLE  = 3'd0,
                     S_START = 3'd1,
                     S_DATA  = 3'd2,
                     S_STOP  = 3'd3;

    reg [2:0] state;
    reg [13:0] clk_count;
    reg [2:0] bit_idx;

    always @(posedge clk or negedge rstn) begin
        if (!rstn) begin
            state     <= S_IDLE;
            clk_count <= 14'd0;
            bit_idx   <= 3'd0;
            rx_data   <= 8'd0;
            done      <= 1'b0;
        end else begin
            done <= 1'b0;
            case (state)
                S_IDLE: begin
                    clk_count <= 14'd0;
                    bit_idx   <= 3'd0;
                    if (!rx) begin
                        state <= S_START;
                    end
                end

                S_START: begin
                    if (clk_count == (CLKS_PER_BIT/2 - 1)) begin
                        if (!rx) begin
                            clk_count <= 14'd0; // align to bit boundary
                            state     <= S_DATA;
                        end else begin
                            state <= S_IDLE;
                        end
                    end else begin
                        clk_count <= clk_count + 1'b1;
                    end
                end

                S_DATA: begin
                    if (clk_count == CLKS_PER_BIT - 1) begin
                        clk_count            <= 14'd0;
                        rx_data[bit_idx]     <= rx; // sample at middle of each bit
                        if (bit_idx == 3'd7) begin
                            bit_idx <= 3'd0;
                            state   <= S_STOP;
                        end else begin
                            bit_idx <= bit_idx + 1'b1;
                        end
                    end else begin
                        clk_count <= clk_count + 1'b1;
                    end
                end

                S_STOP: begin
                    if (clk_count == CLKS_PER_BIT - 1) begin
                        done      <= 1'b1;
                        state     <= S_IDLE;
                        clk_count <= 14'd0;
                    end else begin
                        clk_count <= clk_count + 1'b1;
                    end
                end

                default: state <= S_IDLE;
            endcase
        end
    end

endmodule