"""Write single-deviation mutants of the golden byte controller (each = one design habit)."""
from pathlib import Path
Q=Path('/tmp/claude-0/-home-user-Veri-Sure/12bb865e-7a51-5506-b55a-e5ac7cf72a4a/scratchpad/qual/i2c_master_byte_ctrl')
g=(Q/'src/golden_byte.v').read_text()
def rep(t,a,b,n=1):
    assert t.count(a)>=1,(a,t.count(a)); return t.replace(a,b) if n==0 else t.replace(a,b,n)
M={}
# 1 ack_out captured only after a write transfer (ACK phase issued READ)
M['ackw']=rep(g,"ack_out <= #1 core_rxd;","if (core_cmd == `I2C_CMD_READ) ack_out <= #1 core_rxd;")
# 2 ST_WRITE shifts on the last bit too (8 shifts)
M['wshift8']=rep(g,"""	                  c_state  <= #1 ST_ACK;
	                  core_cmd <= #1 `I2C_CMD_READ;
	              end""","""	                  c_state  <= #1 ST_ACK;
	                  core_cmd <= #1 `I2C_CMD_READ;
	                  shift    <= #1 1'b1;
	              end""")
# 3 no reload (ld) when START completes
s=g.index('ST_START:'); e=g.index('ST_WRITE:',s)
M['nold_start']=g[:s]+g[s:e].replace("ld <= #1 1'b1;","")+g[e:]
# 4 core_txd combinational: sr[7], or ack_in in ST_ACK
t=rep(g,".din     ( core_txd ),",".din     ( core_txd_c ),")
t=rep(t,"assign dout = sr;","assign dout = sr;\n\twire core_txd_c = (c_state == ST_ACK) ? ack_in : sr[7];")
M['txd_comb']=t
# 5 command is a one-cycle pulse: core_cmd defaults to NOP every cycle
M['pulse']=rep(g,"""	      core_txd <= #1 sr[7];
	      shift    <= #1 1'b0;""","""	      core_txd <= #1 sr[7];
	      core_cmd <= #1 `I2C_CMD_NOP;
	      shift    <= #1 1'b0;""")
# 6 ld/shift combinational (sr updates at the same edge the FSM sees core_ack / leaves idle)
t=g.replace("else if (ld)","else if (ld_c)").replace("else if (shift)","else if (shift_c)")
t=rep(t,"assign dout = sr;","""assign dout = sr;
	wire ld_c = ~(rst|i2c_al) & (((c_state == ST_IDLE) & go) | ((c_state == ST_START) & core_ack));
	wire shift_c = ~(rst|i2c_al) & core_ack & ((c_state == ST_READ) | ((c_state == ST_WRITE) & ~cnt_done));""")
M['comb_ldshift']=t
for k,v in M.items(): (Q/'mut'/f'g_{k}.v').write_text(v)
print(list(M))
