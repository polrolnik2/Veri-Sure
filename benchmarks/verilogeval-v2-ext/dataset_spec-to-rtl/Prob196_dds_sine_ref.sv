module RefModule (
    input  logic        clk,
    input  logic        reset,
    input  logic [15:0] phase_inc,
    output logic signed [11:0] sine_out
);
    logic [15:0] phase;

    function automatic logic signed [11:0] qsin(input logic [4:0] idx);
        case (idx)
            5'd0:  qsin = 12'sd0;
            5'd1:  qsin = 12'sd201;
            5'd2:  qsin = 12'sd399;
            5'd3:  qsin = 12'sd594;
            5'd4:  qsin = 12'sd783;
            5'd5:  qsin = 12'sd965;
            5'd6:  qsin = 12'sd1137;
            5'd7:  qsin = 12'sd1299;
            5'd8:  qsin = 12'sd1447;
            5'd9:  qsin = 12'sd1582;
            5'd10: qsin = 12'sd1702;
            5'd11: qsin = 12'sd1805;
            5'd12: qsin = 12'sd1891;
            5'd13: qsin = 12'sd1959;
            5'd14: qsin = 12'sd2008;
            5'd15: qsin = 12'sd2037;
            5'd16: qsin = 12'sd2047;
            default: qsin = 12'sd0;
        endcase
    endfunction

    function automatic logic signed [11:0] sine_from_addr(input logic [5:0] addr);
        logic [1:0] quadrant;
        logic [3:0] offset;
        logic [4:0] qidx;
        logic signed [11:0] mag;
        begin
            quadrant = addr[5:4];
            offset = addr[3:0];
            qidx = (quadrant[0]) ? (5'd16 - {1'b0, offset}) : {1'b0, offset};
            mag = qsin(qidx);
            sine_from_addr = quadrant[1] ? -mag : mag;
        end
    endfunction

    always_ff @(posedge clk) begin
        if (reset) begin
            phase <= 16'd0;
            sine_out <= 12'sd0;
        end else begin
            logic [15:0] phase_next;
            phase_next = phase + phase_inc;
            phase <= phase_next;
            sine_out <= sine_from_addr(phase_next[15:10]);
        end
    end
endmodule

