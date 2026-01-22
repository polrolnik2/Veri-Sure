module RefModule (
    input  logic sclk,
    input  logic reset,
    input  logic cs_n,
    input  logic mosi,
    output logic miso,
    output logic miso_oe
);
    logic [7:0] reg0;
    logic [7:0] opcode;
    logic [7:0] rx_shift;
    logic [2:0] rx_bit_count;
    logic [1:0] byte_index;

    logic [2:0] tx_bit_count;

    // Receive path: sample MOSI on rising edge
    always_ff @(posedge sclk or posedge cs_n) begin
        if (cs_n) begin
            rx_shift <= 8'd0;
            rx_bit_count <= 3'd0;
            byte_index <= 2'd0;
            opcode <= 8'd0;
        end else begin
            if (reset) begin
                reg0 <= 8'd0;
                rx_shift <= 8'd0;
                rx_bit_count <= 3'd0;
                byte_index <= 2'd0;
                opcode <= 8'd0;
            end else begin
                rx_shift <= {rx_shift[6:0], mosi};

                if (rx_bit_count == 3'd7) begin
                    logic [7:0] byte_val;
                    byte_val = {rx_shift[6:0], mosi};

                    rx_bit_count <= 3'd0;
                    rx_shift <= 8'd0;

                    if (byte_index == 2'd0) begin
                        opcode <= byte_val;
                        byte_index <= 2'd1;
                    end else if (byte_index == 2'd1) begin
                        if (opcode == 8'h02) begin
                            reg0 <= byte_val;
                        end
                        byte_index <= 2'd2;
                    end else begin
                        byte_index <= byte_index;
                    end
                end else begin
                    rx_bit_count <= rx_bit_count + 3'd1;
                end
            end
        end
    end

    // Transmit path: drive MISO on falling edge
    always_ff @(negedge sclk or posedge cs_n) begin
        if (cs_n) begin
            miso <= 1'b0;
            miso_oe <= 1'b0;
            tx_bit_count <= 3'd0;
        end else begin
            if (reset) begin
                miso <= 1'b0;
                miso_oe <= 1'b0;
                tx_bit_count <= 3'd0;
            end else begin
                if ((opcode == 8'h03) && (byte_index == 2'd1)) begin
                    miso_oe <= 1'b1;
                    miso <= reg0[7 - tx_bit_count];
                    tx_bit_count <= tx_bit_count + 3'd1;
                end else begin
                    miso <= 1'b0;
                    miso_oe <= 1'b0;
                    tx_bit_count <= 3'd0;
                end
            end
        end
    end
endmodule

