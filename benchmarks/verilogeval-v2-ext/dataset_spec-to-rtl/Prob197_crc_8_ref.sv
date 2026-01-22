module RefModule (
    input  logic [7:0] crc_in,
    input  logic [7:0] data,
    output logic [7:0] crc_out
);
    integer i;
    logic [7:0] crc;
    logic mix;

    always_comb begin
        crc = crc_in;
        for (i = 7; i >= 0; i = i - 1) begin
            mix = data[i] ^ crc[7];
            crc = {crc[6:0], 1'b0};
            if (mix) crc = crc ^ 8'h07;
        end
        crc_out = crc;
    end
endmodule

