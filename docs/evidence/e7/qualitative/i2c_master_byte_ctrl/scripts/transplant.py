"""Replace the inline bit-level stand-in of luna13.gen1/gen2/final with the golden bit controller (encoding mapped)."""
import re
from pathlib import Path
Q=Path('/tmp/claude-0/-home-user-Veri-Sure/12bb865e-7a51-5506-b55a-e5ac7cf72a4a/scratchpad/qual/i2c_master_byte_ctrl')
def inst(cmd, ack, rxd, busy, txd):
    return f'''
    i2c_master_bit_ctrl_golden bc_g(.clk(clk),.rst(rst),.nReset(nReset),.ena(ena),.clk_cnt(clk_cnt),.cmd({cmd}),
      .cmd_ack({ack}),.busy({busy}),.al(i2c_al),.din({txd}),.dout({rxd}),.scl_i(scl_i),.scl_o(scl_o),.scl_oen(scl_oen),
      .sda_i(sda_i),.sda_o(sda_o),.sda_oen(sda_oen));
'''
def sub(t, pat, rep, flags=0, count=1):
    n=len(re.findall(pat,t,flags))
    assert n>=1, pat
    return re.sub(pat, rep, t, count=0 if count==0 else count, flags=flags)
pads=[r"assign scl_o = 1'b0;", r"assign scl_oen = 1'b1;", r"assign sda_o = 1'b0;", r"assign i2c_al = 1'b0;"]
def strip_pads(t):
    for p in pads: t=sub(t, re.escape(p), '')
    return t
# luna13.gen2
t=(Q/'src/luna13.gen2.sv').read_text()
m=t.index('module i2c_master_byte_ctrl__probed'); e=t.index('endmodule',m)
b=t[m:e]
b=sub(b, re.escape("assign core_ack_int = (core_cmd_int != I2C_CMD_NOP);"), '')
b=sub(b, re.escape("assign core_rxd_int = sda_i;"), '')
b=sub(b, re.escape("assign i2c_busy = busy_int;"), '')
b=sub(b, re.escape("assign sda_oen = 1'b1;"), '')
b=strip_pads(b)
b+=inst('{core_cmd_int[2],core_cmd_int[3],core_cmd_int[1:0]}','core_ack_int','core_rxd_int','i2c_busy','core_txd_int')
(Q/'src/luna13.gen2.tx.sv').write_text(t[:m]+b+t[e:])
# luna13.gen1 (3-bit encoding: START 1, STOP 2, READ 3, WRITE 4)
t=(Q/'src/luna13.gen1.sv').read_text()
m=t.index('module i2c_master_byte_ctrl__probed'); e=t.index('endmodule',m)
b=t[m:e]
b=sub(b, r"output reg i2c_busy", "output i2c_busy")
b=sub(b, re.escape("assign core_ack_i = (core_cmd_i != I2C_CMD_NOP);"), '')
b=sub(b, re.escape("assign core_rxd_i = sda_i;"), '')
b=sub(b, r"assign sda_oen = \(\(core_cmd_i == I2C_CMD_START\).*?;", '', flags=re.S)
b=strip_pads(b)
b=sub(b, r"i2c_busy <=", "busy_unused <=", count=0)
b=b.replace("reg [7:0] sr;", "reg [7:0] sr; reg busy_unused;",1)
cmd="(core_cmd_i==3'd1)?4'b0001:(core_cmd_i==3'd2)?4'b0010:(core_cmd_i==3'd3)?4'b1000:(core_cmd_i==3'd4)?4'b0100:4'b0000"
b+=inst(cmd,'core_ack_i','core_rxd_i','i2c_busy','core_txd_i')
(Q/'src/luna13.gen1.tx.sv').write_text(t[:m]+b+t[e:])
# luna13.final
t=(Q/'src/luna13.final.sv').read_text()
m=t.index('module i2c_master_byte_ctrl__probed'); e=t.index('endmodule',m)
b=t[m:e]
for r_ in ['core_ack_r','core_rxd_r','busy_r']:
    b=sub(b, rf"reg {r_};", f"wire {r_};")
s=b.index('// Minimal local command responder'); a=b.index('always',s)
# end of that always block = start of the next 'always'
nxt=b.index('always @(posedge clk', a+6)
b=b[:s]+b[nxt:]
b=sub(b, re.escape("assign sda_oen = 1'b1;"), '')
b=strip_pads(b)
b+=inst('{core_cmd[2],core_cmd[3],core_cmd[1:0]}','core_ack_r','core_rxd_r','busy_r','core_txd_int')
(Q/'src/luna13.final.tx.sv').write_text(t[:m]+b+t[e:])
print('ok')
