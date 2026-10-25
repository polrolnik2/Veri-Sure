// A register the design does NOT reset -- the shape of golden i2c's `dout`,
// written by `always @(posedge clk) if (sSCL & ~dSCL) dout <= sSDA;` with no
// reset path at all.
//
// It exists to pin TESTPOINT INDEPENDENCE. cocotb runs every test module in one
// simulator process by default and the DUT is elaborated once, so `latched`
// keeps whatever the previous testpoint left in it -- and `Env.reset()` cannot
// clear it, because there is nothing to drive. On the golden i2c core that
// single effect made 60 of 168 testpoints fail for a CORRECT design, and it
// made the verdicts depend on test ORDER.
module Dut (input clk, input rst_n, input load, input d, output reg q, output reg latched);
  always @(posedge clk or negedge rst_n)
    if (!rst_n) q <= 1'b0;
    else        q <= d;

  // No reset. Deliberately.
  always @(posedge clk)
    if (load) latched <= d;
endmodule
