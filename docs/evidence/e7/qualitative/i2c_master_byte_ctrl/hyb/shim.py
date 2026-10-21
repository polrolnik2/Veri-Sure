import sys
# write shim module mapping design cmd encoding -> golden encoding
mode=sys.argv[1]  # 'id' | 'swap' (READ=0100,WRITE=1000) | 'bin' (READ=0011, WRITE=0100)
out=sys.argv[2]
if mode=='id': m='cmd'
elif mode=='swap': m='{cmd[2],cmd[3],cmd[1],cmd[0]}'
elif mode=='bin': m="(cmd==4'b0011)?4'b1000:(cmd==4'b0100)?4'b0100:cmd"
open(out,'w').write(f'''`timescale 1ns/1ps
module i2c_master_bit_ctrl(input clk, input rst, input nReset, input ena, input [15:0] clk_cnt, input [3:0] cmd,
  output cmd_ack, output busy, output al, input din, output dout, input scl_i, output scl_o, output scl_oen,
  input sda_i, output sda_o, output sda_oen);
  wire [3:0] gcmd = {m};
  i2c_master_bit_ctrl_golden g(.clk(clk),.rst(rst),.nReset(nReset),.ena(ena),.clk_cnt(clk_cnt),.cmd(gcmd),.cmd_ack(cmd_ack),
    .busy(busy),.al(al),.din(din),.dout(dout),.scl_i(scl_i),.scl_o(scl_o),.scl_oen(scl_oen),.sda_i(sda_i),.sda_o(sda_o),.sda_oen(sda_oen));
endmodule
''')
