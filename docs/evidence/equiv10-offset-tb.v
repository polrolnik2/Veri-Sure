`timescale 1ns/10ps
module tb;
  reg clk=0, rst=0, nReset=0, ena=0, din=0, scl_i=1, sda_i=1;
  reg [15:0] clk_cnt = 16'd3;
  reg [3:0] cmd = 4'd0;
  wire r_cmd_ack,r_busy,r_al,r_dout,r_scl_o,r_scl_oen,r_sda_o,r_sda_oen;
  wire d_cmd_ack,d_busy,d_al,d_dout,d_scl_o,d_scl_oen,d_sda_o,d_sda_oen;
  integer i, fh; integer seed = 32'd12345;
  i2c_master_bit_ctrl      REF (.clk(clk),.rst(rst),.nReset(nReset),.ena(ena),
    .clk_cnt(clk_cnt),.cmd(cmd),.din(din),.scl_i(scl_i),.sda_i(sda_i),
    .cmd_ack(r_cmd_ack),.busy(r_busy),.al(r_al),.dout(r_dout),
    .scl_o(r_scl_o),.scl_oen(r_scl_oen),.sda_o(r_sda_o),.sda_oen(r_sda_oen));
  cand_i2c_master_bit_ctrl DUT (.clk(clk),.rst(rst),.nReset(nReset),.ena(ena),
    .clk_cnt(clk_cnt),.cmd(cmd),.din(din),.scl_i(scl_i),.sda_i(sda_i),
    .cmd_ack(d_cmd_ack),.busy(d_busy),.al(d_al),.dout(d_dout),
    .scl_o(d_scl_o),.scl_oen(d_scl_oen),.sda_o(d_sda_o),.sda_oen(d_sda_oen));
  always #5 clk = ~clk;
  initial begin
    fh = $fopen("trace.txt","w");
    nReset=0; rst=1; ena=0; @(posedge clk); @(posedge clk);
    nReset=1; rst=0; ena=1; @(posedge clk);
    for (i=0; i<4000; i=i+1) begin
      @(posedge clk); #1;
      $fwrite(fh,"%b %b %b %b %b %b\n", r_dout,d_dout, r_scl_oen,d_scl_oen, r_cmd_ack,d_cmd_ack);
      if (i%7==0) cmd = ($random(seed)%5==0) ? 4'd0 : (1 << ($random(seed)&2'd3));
      if (i%3==0) din = $random(seed);
      if (i%2==0) scl_i = ($random(seed)&3)!=0;
      if (i%2==1) sda_i = ($random(seed)&3)!=0;
      if (i%501==500) begin rst=1; @(posedge clk); rst=0; end
    end
    $fclose(fh); $finish;
  end
endmodule
