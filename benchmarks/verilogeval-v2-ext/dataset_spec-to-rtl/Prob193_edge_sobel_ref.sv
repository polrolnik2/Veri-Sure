module RefModule (
    input  logic [7:0] p00,
    input  logic [7:0] p01,
    input  logic [7:0] p02,
    input  logic [7:0] p10,
    input  logic [7:0] p11,
    input  logic [7:0] p12,
    input  logic [7:0] p20,
    input  logic [7:0] p21,
    input  logic [7:0] p22,
    output logic signed [10:0] gx,
    output logic signed [10:0] gy,
    output logic [10:0] mag
);
    function automatic logic [10:0] abs11(input logic signed [10:0] v);
        logic signed [11:0] tmp;
        begin
            tmp = v;
            if (tmp < 0) tmp = -tmp;
            abs11 = tmp[10:0];
        end
    endfunction

    logic signed [11:0] gx_s;
    logic signed [11:0] gy_s;
    logic [10:0] ax;
    logic [10:0] ay;

    always_comb begin
        gx_s =
            $signed({1'b0, p02}) + ($signed({1'b0, p12}) <<< 1) + $signed({1'b0, p22})
            - ($signed({1'b0, p00}) + ($signed({1'b0, p10}) <<< 1) + $signed({1'b0, p20}));
        gy_s =
            $signed({1'b0, p20}) + ($signed({1'b0, p21}) <<< 1) + $signed({1'b0, p22})
            - ($signed({1'b0, p00}) + ($signed({1'b0, p01}) <<< 1) + $signed({1'b0, p02}));

        gx = gx_s[10:0];
        gy = gy_s[10:0];

        ax = abs11(gx);
        ay = abs11(gy);
        mag = ax + ay;
    end
endmodule
