import re, sys
Q='/tmp/claude-0/-home-user-Veri-Sure/12bb865e-7a51-5506-b55a-e5ac7cf72a4a/scratchpad/qual/i2c_master_bit_ctrl'
base=open(f'{Q}/gv/gB.v').read()
def rep(s,a,b,cnt=1):
    assert s.count(a)>=1, a
    return s.replace(a,b) if cnt is None else s.replace(a,b,cnt)
def branch(s,name):
    # return (start,end) of the 'name:' case branch begin..end
    i=s.index(f'                    {name}:\n'); j=s.index('                    end\n',i)+len('                    end\n'); return i,j
M={}
def P1(s): return rep(rep(s,'fSCL <= {fSCL[1:0],cSCL[1]};','fSCL <= {fSCL[1:0],cSCL[0]};'),'fSDA <= {fSDA[1:0],cSDA[1]};','fSDA <= {fSDA[1:0],cSDA[0]};')
def P2(s):
    s=rep(s,'    reg sta_condition;\n    reg sto_condition;','    reg sta_r, sto_r;\n    wire sta_condition = ~sSDA & dSDA & sSCL;\n    wire sto_condition = sSDA & ~dSDA & sSCL;')
    return s.replace('sta_condition <=','sta_r <=').replace('sto_condition <=','sto_r <=')
def P3(s):
    s=rep(s,'    reg        sSCL, sSDA;','    reg sSCL_r, sSDA_r;\n    wire sSCL = &fSCL[2:1] | &fSCL[1:0] | (fSCL[2] & fSCL[0]);\n    wire sSDA = &fSDA[2:1] | &fSDA[1:0] | (fSDA[2] & fSDA[0]);')
    return s.replace('sSCL <=','sSCL_r <=').replace('sSDA <=','sSDA_r <=')
def AL(s): return rep(s,'al <= (sda_chk & ~sSDA & sda_oen) | (|c_state & sto_condition & ~cmd_stop);','al <= al | (sda_chk & ~sSDA & sda_oen) | (|c_state & sto_condition & ~cmd_stop);')
def W0(s): return rep(s,'al <= (sda_chk & ~sSDA & sda_oen)','al <= (sda_chk & ~sSDA)')
def WS(s): return rep(s,'c_state <= start_d;','c_state <= start_e;')
def WP(s): return rep(s,'c_state <= stop_c;','c_state <= stop_d;')
def WR(s): return rep(s,'c_state <= rd_c;','c_state <= rd_d;')
def WW(s):
    i,j=branch(s,'wr_b'); b=s[i:j].replace('c_state <= wr_c;','c_state <= wr_d;').replace("sda_chk <= 1'b0;","sda_chk <= 1'b1;")
    return s[:i]+b+s[j:]
def TR(s):
    names={'start_e':0x20001,'stop_d':0x20002,'rd_d':0x20004,'wr_d':0x20008}
    extra=''
    for n,v in names.items():
        i,j=branch(s,n); b=s[i:j]
        b=b.replace('c_state <= idle;',f'c_state <= tr_{n};').replace("cmd_ack <= 1'b1;","")
        s=s[:i]+b+s[j:]
        extra+=f"                    tr_{n}:\n                    begin\n                        c_state <= idle;\n                        cmd_ack <= 1'b1;\n                    end\n"
        s=rep(s,"    parameter [17:0] wr_d    = 18'b1_0000_0000_0000_0000;",f"    parameter [17:0] wr_d    = 18'b1_0000_0000_0000_0000;\n    parameter [17:0] tr_{n} = 18'h{v:05x};") if False else s
    params=''.join(f"    parameter [17:0] tr_{n} = 18'h{v:05x};\n" for n,v in names.items())
    k=s.index('    parameter [17:0] idle'); s=s[:k]+params+s[k:]
    i,j=branch(s,'wr_d'); s=s[:j]+extra+s[j:]
    return s
def WIN(s): return WW(WR(WP(WS(s))))
def PIPE(s): return P3(P2(P1(s)))
muts={'mP1':[P1],'mP2':[P2],'mP3':[P3],'mAL':[AL],'mW0':[W0],'mWS':[WS],'mWP':[WP],'mWR':[WR],'mWW':[WW],'mTR':[TR],'mWIN':[WIN],'mPIPE':[PIPE]}
for n,fs in muts.items():
    s=base
    for f in fs: s=f(s)
    open(f'{Q}/gv/{n}.v','w').write(s)
print('ok')
