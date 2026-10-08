module Dut (
    input        clk,
    input        rst_n,
    input        ena,
    input  [3:0] prescale,
    input        go,
    output reg   busy,
    output reg   done
);
  reg [3:0] cnt;
  reg       clk_en;
  reg [2:0] state;

  always @(posedge clk or negedge rst_n)
    if (!rst_n)            begin cnt <= 4'd0; clk_en <= 1'b1; end
    else if (cnt == 4'd0 || !ena) begin cnt <= prescale; clk_en <= 1'b1; end
    else                   begin cnt <= cnt - 4'd1; clk_en <= 1'b0; end

  always @(posedge clk or negedge rst_n)
    if (!rst_n) begin state <= 3'd0; busy <= 1'b0; done <= 1'b0; end
    else begin
      done <= 1'b0;                     // one-cycle pulse, cleared every edge
      if (clk_en && ena)
        case (state)
          3'd0: if (go) begin state <= 3'd1; busy <= 1'b1; end
          3'd1:         begin state <= 3'd2; end          // hold: no output change
          3'd2:         begin state <= 3'd3; end          // hold: no output change
          3'd3:         begin state <= 3'd4; end
          3'd4:         begin state <= 3'd0; busy <= 1'b0; done <= 1'b1; end
          default:      begin state <= 3'd0; end
        endcase
    end
endmodule
