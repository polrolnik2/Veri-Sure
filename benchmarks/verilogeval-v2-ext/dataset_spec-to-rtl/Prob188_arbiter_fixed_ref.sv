module RefModule (
    input  logic [3:0] req,
    output logic [3:0] grant,
    output logic       grant_valid
);
    always_comb begin
        grant = 4'b0000;
        if (req[0]) grant = 4'b0001;
        else if (req[1]) grant = 4'b0010;
        else if (req[2]) grant = 4'b0100;
        else if (req[3]) grant = 4'b1000;

        grant_valid = |grant;
    end
endmodule

