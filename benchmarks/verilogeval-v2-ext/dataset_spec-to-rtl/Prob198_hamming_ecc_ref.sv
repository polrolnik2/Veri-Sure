module RefModule (
    input  logic [3:0] data_in,
    input  logic [6:0] code_in,
    output logic [6:0] encoded,
    output logic [6:0] corrected,
    output logic [3:0] data_out,
    output logic [2:0] err_pos,
    output logic       error
);
    logic p1;
    logic p2;
    logic p4;

    logic s1;
    logic s2;
    logic s4;

    always_comb begin
        // Encode
        p1 = data_in[0] ^ data_in[1] ^ data_in[3];
        p2 = data_in[0] ^ data_in[2] ^ data_in[3];
        p4 = data_in[1] ^ data_in[2] ^ data_in[3];
        encoded = {data_in[3], data_in[2], data_in[1], p4, data_in[0], p2, p1};

        // Syndrome
        s1 = code_in[0] ^ code_in[2] ^ code_in[4] ^ code_in[6];
        s2 = code_in[1] ^ code_in[2] ^ code_in[5] ^ code_in[6];
        s4 = code_in[3] ^ code_in[4] ^ code_in[5] ^ code_in[6];
        err_pos = {s4, s2, s1};

        error = (err_pos != 3'd0);

        // Correct
        corrected = code_in;
        if (error) begin
            corrected[err_pos - 3'd1] = ~code_in[err_pos - 3'd1];
        end

        // Decode
        data_out = {corrected[6], corrected[5], corrected[4], corrected[2]};
    end
endmodule

