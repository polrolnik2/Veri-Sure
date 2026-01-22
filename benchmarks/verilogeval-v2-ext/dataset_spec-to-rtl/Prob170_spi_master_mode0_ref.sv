module RefModule (
    input  logic       clk,
    input  logic       reset,
    input  logic       start,
    input  logic [7:0] tx_data,
    input  logic       miso,
    output logic       mosi,
    output logic       sclk,
    output logic       cs_n,
    output logic [7:0] rx_data,
    output logic       busy,
    output logic       done
);
    logic       phase;  // 0=low, 1=high
    logic [2:0] bit_idx;
    logic [7:0] tx_shift;
    logic [7:0] rx_shift;
    logic       done_pending;

    always_ff @(posedge clk) begin
        if (reset) begin
            mosi <= 1'b0;
            sclk <= 1'b0;
            cs_n <= 1'b1;
            rx_data <= 8'd0;
            busy <= 1'b0;
            done <= 1'b0;

            phase <= 1'b0;
            bit_idx <= 3'd0;
            tx_shift <= 8'd0;
            rx_shift <= 8'd0;
            done_pending <= 1'b0;
        end else begin
            done <= 1'b0;

            if (!busy) begin
                // Idle defaults
                sclk <= 1'b0;
                cs_n <= 1'b1;
                mosi <= 1'b0;
                done_pending <= 1'b0;

                if (start) begin
                    busy <= 1'b1;
                    cs_n <= 1'b0;
                    sclk <= 1'b0;
                    tx_shift <= tx_data;
                    rx_shift <= 8'd0;
                    bit_idx <= 3'd7;
                    mosi <= tx_data[7];
                    phase <= 1'b1;  // next cycle is HIGH half-cycle (sample)
                end
            end else begin
                if (phase == 1'b0) begin
                    // LOW half-cycle
                    sclk <= 1'b0;
                    if (done_pending) begin
                        busy <= 1'b0;
                        cs_n <= 1'b1;
                        mosi <= 1'b0;
                        done <= 1'b1;
                        rx_data <= rx_shift;
                        done_pending <= 1'b0;
                        phase <= 1'b0;
                    end else begin
                        mosi <= tx_shift[bit_idx];
                        phase <= 1'b1;
                    end
                end else begin
                    // HIGH half-cycle: sample MISO
                    sclk <= 1'b1;
                    rx_shift[bit_idx] <= miso;
                    phase <= 1'b0;
                    if (bit_idx == 3'd0) begin
                        done_pending <= 1'b1;
                    end else begin
                        bit_idx <= bit_idx - 3'd1;
                    end
                end
            end
        end
    end
endmodule

