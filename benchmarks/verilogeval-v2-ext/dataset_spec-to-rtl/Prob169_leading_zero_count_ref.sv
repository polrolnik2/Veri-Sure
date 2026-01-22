module RefModule (
    input  logic [31:0] x,
    output logic [5:0]  count
);
    integer i;
    logic found_one;

    always_comb begin
        count = 6'd0;
        found_one = 1'b0;

        for (i = 31; i >= 0; i = i - 1) begin
            if (!found_one) begin
                if (x[i] == 1'b0) begin
                    count = count + 6'd1;
                end else begin
                    found_one = 1'b1;
                end
            end
        end
    end
endmodule

