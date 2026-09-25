module Dut (input clk, input rst_n, input [7:0] d, output [7:0] q);
  reg [7:0] s1, s2, s3;
  always @(posedge clk or negedge rst_n)
    if (!rst_n) begin s1 <= 8'd0; s2 <= 8'd0; s3 <= 8'd0; end
    else        begin s1 <= d + 8'd1; s2 <= s1; s3 <= s2; end
  assign q = s3;
endmodule
