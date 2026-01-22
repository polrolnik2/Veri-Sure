module RefModule (
    input  logic clk,
    input  logic arst,
    output logic srst
);
    logic ff1;
    logic ff2;

    always_ff @(posedge clk or posedge arst) begin
        if (arst) begin
            ff1 <= 1'b1;
            ff2 <= 1'b1;
        end else begin
            ff1 <= 1'b0;
            ff2 <= ff1;
        end
    end

    always_comb begin
        srst = ff2;
    end
endmodule

