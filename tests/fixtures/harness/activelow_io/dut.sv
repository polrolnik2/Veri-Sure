module Dut (
    input      clk,
    input      rst_n,
    input      req_n,     // active low: asserted when 0, idle when 1
    input      bus_i,     // open drain: released is 1
    output reg oen,       // active low output enable: 1 releases, 0 drives low
    output reg seen
);
  always @(posedge clk or negedge rst_n)
    if (!rst_n) begin oen <= 1'b1; seen <= 1'b0; end
    else begin
      oen  <= req_n;            // drive the line low only while req_n is asserted
      seen <= ~req_n & bus_i;   // sampled only when the bus is released high
    end
endmodule
