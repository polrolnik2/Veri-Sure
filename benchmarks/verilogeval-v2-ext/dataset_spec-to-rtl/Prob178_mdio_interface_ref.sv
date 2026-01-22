module RefModule (
    input  logic        clk,
    input  logic        reset,
    input  logic        start,
    input  logic        op,
    input  logic [4:0]  phy_addr,
    input  logic [4:0]  reg_addr,
    input  logic [15:0] wr_data,
    input  logic        mdio_in,
    output logic        mdc,
    output logic        mdio_out,
    output logic        mdio_oe,
    output logic [15:0] rd_data,
    output logic        busy,
    output logic        done
);
    localparam int TOTAL_BITS = 64;

    logic        lat_op;
    logic [4:0]  lat_phy;
    logic [4:0]  lat_reg;
    logic [15:0] lat_wr;

    logic [15:0] rd_shift;

    logic        phase;      // 0=LOW, 1=HIGH
    logic [6:0]  bit_pos;    // 0..63
    logic        done_pending;

    function automatic logic drive_en_for_bit(input logic op_i, input int unsigned pos);
        if (pos < 46) drive_en_for_bit = 1'b1;                // preamble..regad
        else if (pos < 48) drive_en_for_bit = (op_i == 1'b0); // TA: drive only on WRITE
        else drive_en_for_bit = (op_i == 1'b0);               // data: drive only on WRITE
    endfunction

    function automatic logic bit_value_for_bit(input logic op_i, input int unsigned pos);
        // Only used when drive_en_for_bit()==1
        if (pos < 32) begin
            bit_value_for_bit = 1'b1; // preamble
        end else if (pos < 34) begin
            bit_value_for_bit = (pos == 32) ? 1'b0 : 1'b1; // start "01"
        end else if (pos < 36) begin
            // opcode: WRITE="01", READ="10"
            if (op_i == 1'b0) bit_value_for_bit = (pos == 34) ? 1'b0 : 1'b1;
            else bit_value_for_bit = (pos == 34) ? 1'b1 : 1'b0;
        end else if (pos < 41) begin
            bit_value_for_bit = lat_phy[40 - pos]; // 36..40
        end else if (pos < 46) begin
            bit_value_for_bit = lat_reg[45 - pos]; // 41..45
        end else if (pos < 48) begin
            // TA for WRITE: "10"
            bit_value_for_bit = (pos == 46) ? 1'b1 : 1'b0;
        end else begin
            // WRITE data bits: wr_data[15] first at pos=48
            bit_value_for_bit = lat_wr[63 - pos];
        end
    endfunction

    always_ff @(posedge clk) begin
        if (reset) begin
            lat_op <= 1'b0;
            lat_phy <= 5'd0;
            lat_reg <= 5'd0;
            lat_wr <= 16'd0;
            rd_shift <= 16'd0;
            rd_data <= 16'd0;

            mdc <= 1'b0;
            mdio_out <= 1'b1;
            mdio_oe <= 1'b0;
            busy <= 1'b0;
            done <= 1'b0;

            phase <= 1'b0;
            bit_pos <= 7'd0;
            done_pending <= 1'b0;
        end else begin
            done <= 1'b0;

            if (!busy) begin
                mdc <= 1'b0;
                mdio_oe <= 1'b0;
                mdio_out <= 1'b1;
                done_pending <= 1'b0;

                if (start) begin
                    lat_op <= op;
                    lat_phy <= phy_addr;
                    lat_reg <= reg_addr;
                    lat_wr <= wr_data;
                    rd_shift <= 16'd0;
                    rd_data <= 16'd0;

                    busy <= 1'b1;
                    bit_pos <= 7'd0;

                    // First LOW half-cycle immediately.
                    mdc <= 1'b0;
                    mdio_oe <= drive_en_for_bit(op, 0);
                    mdio_out <= bit_value_for_bit(op, 0);
                    phase <= 1'b1; // next is HIGH
                end
            end else begin
                if (phase == 1'b0) begin
                    // LOW half-cycle: drive bit (or release)
                    mdc <= 1'b0;
                    if (done_pending) begin
                        busy <= 1'b0;
                        done <= 1'b1;
                        mdio_oe <= 1'b0;
                        mdio_out <= 1'b1;
                        rd_data <= (lat_op == 1'b1) ? rd_shift : 16'd0;
                        done_pending <= 1'b0;
                        phase <= 1'b0;
                    end else begin
                        mdio_oe <= drive_en_for_bit(lat_op, bit_pos);
                        mdio_out <= bit_value_for_bit(lat_op, bit_pos);
                        phase <= 1'b1;
                    end
                end else begin
                    // HIGH half-cycle: sample if needed, advance bit
                    mdc <= 1'b1;
                    if ((lat_op == 1'b1) && (bit_pos >= 48) && (bit_pos < 64)) begin
                        rd_shift[63 - bit_pos] <= mdio_in;
                    end

                    phase <= 1'b0;
                    if (bit_pos == (TOTAL_BITS-1)) begin
                        done_pending <= 1'b1;
                    end else begin
                        bit_pos <= bit_pos + 7'd1;
                    end
                end
            end
        end
    end
endmodule

