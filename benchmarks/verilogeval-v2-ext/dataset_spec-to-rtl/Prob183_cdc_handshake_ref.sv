module RefModule (
    input  logic       src_clk,
    input  logic       src_reset,
    input  logic       src_valid,
    input  logic [7:0] src_data,
    output logic       src_ready,
    input  logic       dst_clk,
    input  logic       dst_reset,
    output logic       dst_valid,
    output logic [7:0] dst_data,
    input  logic       dst_ready
);
    // Toggle handshake.
    logic req_tog;
    logic ack_tog;

    // Data held stable while request is pending.
    logic [7:0] data_hold;

    // Synchronizers.
    logic ack_sync1, ack_sync2;
    logic req_sync1, req_sync2;
    logic req_seen;

    assign src_ready = (req_tog == ack_sync2);

    // Source domain: capture data and toggle request when accepted.
    always_ff @(posedge src_clk) begin
        if (src_reset) begin
            req_tog <= 1'b0;
            data_hold <= 8'd0;
            ack_sync1 <= 1'b0;
            ack_sync2 <= 1'b0;
        end else begin
            ack_sync1 <= ack_tog;
            ack_sync2 <= ack_sync1;
            if (src_valid && src_ready) begin
                data_hold <= src_data;
                req_tog <= ~req_tog;
            end
        end
    end

    // Destination domain: latch data on new request, hold valid until consumed, then ack.
    always_ff @(posedge dst_clk) begin
        if (dst_reset) begin
            req_sync1 <= 1'b0;
            req_sync2 <= 1'b0;
            req_seen <= 1'b0;
            ack_tog <= 1'b0;
            dst_valid <= 1'b0;
            dst_data <= 8'd0;
        end else begin
            req_sync1 <= req_tog;
            req_sync2 <= req_sync1;

            // New transfer arrives.
            if ((req_sync2 ^ req_seen) && !dst_valid) begin
                dst_data <= data_hold;
                dst_valid <= 1'b1;
                req_seen <= req_sync2;
            end

            // Consume at destination and send ack.
            if (dst_valid && dst_ready) begin
                dst_valid <= 1'b0;
                ack_tog <= req_seen;
            end
        end
    end
endmodule

