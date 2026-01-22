module RefModule (
    input  logic       clk,
    input  logic       reset,
    input  logic       in_bit,
    input  logic [7:0] pattern,
    input  logic [3:0] pattern_len,
    output logic       match
);
    logic [7:0] history;

    always_ff @(posedge clk) begin
        if (reset) begin
            history <= 8'd0;
            match <= 1'b0;
        end else begin
            logic [7:0] history_next;
            logic [7:0] mask;

            history_next = {history[6:0], in_bit};

            if ((pattern_len == 4'd0) || (pattern_len > 4'd8)) begin
                mask = 8'd0;
                match <= 1'b0;
            end else begin
                if (pattern_len == 4'd8) begin
                    mask = 8'hFF;
                end else begin
                    mask = (8'h01 << pattern_len) - 8'h01;
                end
                match <= ((history_next & mask) == (pattern & mask));
            end

            history <= history_next;
        end
    end
endmodule

