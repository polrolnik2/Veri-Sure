// A request/acknowledge FSM whose acknowledge is COMBINATIONAL: `ack` is high
// while BUSY and `done_i` is presented, on the same edge that leaves BUSY. The
// shape of or1200_dc_fsm's first_miss_ack, and the case a post-edge recording
// can never show -- after the edge the state is IDLE and `ack` is low.
// `in_busy` and `done_count` are the contract's probes, exposed as ports the
// way generated RTL exposes them.
module Dut (input clk, input rst_n, input go, input done_i,
            output busy, output ack, output reg [1:0] count,
            output in_busy, output [1:0] done_count);
  reg state;
  assign busy = state;
  assign in_busy = state;
  assign done_count = count;
  assign ack = state & done_i;
  always @(posedge clk or negedge rst_n)
    if (!rst_n) begin
      state <= 1'b0;
      count <= 2'd0;
    end else if (!state) begin
      if (go) state <= 1'b1;
    end else if (done_i) begin
      state <= 1'b0;
      count <= count + 2'd1;
    end
endmodule
