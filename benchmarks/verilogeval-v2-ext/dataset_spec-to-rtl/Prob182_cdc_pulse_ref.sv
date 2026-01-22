module RefModule (
    input  logic clk_fast,
    input  logic reset_fast,
    input  logic clk_slow,
    input  logic reset_slow,
    input  logic pulse_in,
    output logic ready,
    output logic pulse_out
);
    // Toggle-based request/ack handshake.
    logic req_tog;
    logic ack_tog;

    // Synchronizers.
    logic ack_sync1, ack_sync2;
    logic req_sync1, req_sync2;
    logic req_seen;

    assign ready = (req_tog == ack_sync2);

    // Fast domain: generate request toggle when accepting a pulse.
    always_ff @(posedge clk_fast) begin
        if (reset_fast) begin
            req_tog <= 1'b0;
            ack_sync1 <= 1'b0;
            ack_sync2 <= 1'b0;
        end else begin
            ack_sync1 <= ack_tog;
            ack_sync2 <= ack_sync1;
            if (pulse_in && ready) begin
                req_tog <= ~req_tog;
            end
        end
    end

    // Slow domain: detect request toggle edge and generate a 1-cycle pulse.
    always_ff @(posedge clk_slow) begin
        if (reset_slow) begin
            req_sync1 <= 1'b0;
            req_sync2 <= 1'b0;
            req_seen <= 1'b0;
            ack_tog <= 1'b0;
            pulse_out <= 1'b0;
        end else begin
            req_sync1 <= req_tog;
            req_sync2 <= req_sync1;

            pulse_out <= (req_sync2 ^ req_seen);
            if (req_sync2 ^ req_seen) begin
                req_seen <= req_sync2;
                ack_tog <= req_sync2;
            end
        end
    end
endmodule

