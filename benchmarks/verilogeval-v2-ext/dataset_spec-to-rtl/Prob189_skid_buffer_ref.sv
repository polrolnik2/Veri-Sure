module RefModule (
    input  logic       clk,
    input  logic       reset,
    input  logic       in_valid,
    input  logic [7:0] in_data,
    output logic       in_ready,
    output logic       out_valid,
    output logic [7:0] out_data,
    input  logic       out_ready
);
    // Implement as a 2-entry FIFO (skid buffer).
    logic [1:0] count; // 0..2
    logic [7:0] d0, d1;

    assign out_valid = (count != 0);
    assign out_data  = d0;

    wire out_fire = out_valid && out_ready;
    assign in_ready = (count != 2) || out_fire;
    wire in_fire = in_valid && in_ready;

    always_ff @(posedge clk) begin
        if (reset) begin
            count <= 2'd0;
            d0 <= 8'd0;
            d1 <= 8'd0;
        end else begin
            unique case ({in_fire, out_fire})
                2'b10: begin // in only
                    if (count == 2'd0) d0 <= in_data;
                    else if (count == 2'd1) d1 <= in_data;
                    count <= count + 2'd1;
                end
                2'b01: begin // out only
                    if (count == 2'd2) begin
                        d0 <= d1;
                    end
                    count <= count - 2'd1;
                end
                2'b11: begin // in and out
                    if (count == 2'd1) begin
                        d0 <= in_data;
                    end else if (count == 2'd2) begin
                        d0 <= d1;
                        d1 <= in_data;
                    end
                    count <= count;
                end
                default: begin
                    count <= count;
                end
            endcase
        end
    end
endmodule

