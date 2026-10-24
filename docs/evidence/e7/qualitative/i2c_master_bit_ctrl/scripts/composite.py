# build golden(gB)-based composite models carrying a chosen subset of a design's habits
import json, sys, importlib.util
Q='/tmp/claude-0/-home-user-Veri-Sure/12bb865e-7a51-5506-b55a-e5ac7cf72a4a/scratchpad/qual/i2c_master_bit_ctrl'
spec=importlib.util.spec_from_file_location('mut', f'{Q}/scripts/mutants.py')
TABLES=json.load(open(f'{Q}/tables.json'))
base=open(f'{Q}/gv/gB.v').read()
def P1(s): return s.replace('fSCL <= {fSCL[1:0],cSCL[1]};','fSCL <= {fSCL[1:0],cSCL[0]};').replace('fSDA <= {fSDA[1:0],cSDA[1]};','fSDA <= {fSDA[1:0],cSDA[0]};')
def P2(s):
    s=s.replace('    reg sta_condition;\n    reg sto_condition;','    reg sta_r, sto_r;\n    wire sta_condition = ~sSDA & dSDA & sSCL;\n    wire sto_condition = sSDA & ~dSDA & sSCL;')
    return s.replace('sta_condition <=','sta_r <=').replace('sto_condition <=','sto_r <=')
def P3(s):
    s=s.replace('    reg        sSCL, sSDA;','    reg sSCL_r, sSDA_r;\n    wire sSCL = &fSCL[2:1] | &fSCL[1:0] | (fSCL[2] & fSCL[0]);\n    wire sSDA = &fSDA[2:1] | &fSDA[1:0] | (fSDA[2] & fSDA[0]);')
    return s.replace('sSCL <=','sSCL_r <=').replace('sSDA <=','sSDA_r <=')
def AL(s): return s.replace('al <= (sda_chk & ~sSDA & sda_oen)','al <= al | (sda_chk & ~sSDA & sda_oen)')
def ALS(s): # sticky, cleared by a START condition, FSM held idle while al
    import re
    return re.sub(r"al <= \(sda_chk & ~sSDA & sda_oen\) \| (.*?);\n", lambda m: "al <= ~sta_condition & (al | (sda_chk & ~sSDA & sda_oen) | "+m.group(1)+");\n", s, count=1)
def W0(s): return s.replace('(sda_chk & ~sSDA & sda_oen)','(sda_chk & ~sSDA)')

def CE0(s):
    a="""      if (~nReset)
      begin
          cnt    <= 16'h0;
          clk_en <= 1'b1;
      end
      else if (rst || ~|cnt || !ena || scl_sync)"""
    assert a in s
    return s.replace(a, a.replace("clk_en <= 1'b1;","clk_en <= 1'b0;").replace("else if (rst || ~|cnt || !ena || scl_sync)","else if (rst)\n      begin\n          cnt <= clk_cnt;\n          clk_en <= 1'b0;\n      end\n      else if (~|cnt || !ena || scl_sync)"))
def SW(s):
    import re
    return s.replace("          if (clk_en)\n","          if (clk_en & ~slave_wait)\n",1)

CNT_OLD = """      else if (rst || ~|cnt || !ena || scl_sync)
      begin
          cnt    <= clk_cnt;
          clk_en <= 1'b1;
      end
      else if (slave_wait)
      begin
          cnt    <= cnt;
          clk_en <= 1'b0;    
      end
"""
def SWP(s):  # slave_wait has priority over counter expiry (ref-model reading)
    sw = """      else if (slave_wait)
      begin
          cnt    <= cnt;
          clk_en <= 1'b0;    
      end
"""
    assert sw in s and '~|cnt || ' in s
    s = s.replace('~|cnt || ', '', 1)
    return s.replace(sw, sw + """      else if (~|cnt)
      begin
          cnt    <= clk_cnt;
          clk_en <= 1'b1;
      end
""")
def ENA0(s):  # core disabled -> clk_en low
    import re
    m=re.search(r"      else if \(([^\n]*)!ena \|\| ([^\n]*)\)\n", s)
    assert m
    line=m.group(0)
    rep="      else if (!ena)\n      begin\n          cnt <= clk_cnt;\n          clk_en <= 1'b0;\n      end\n"+line.replace('!ena || ','')
    return s.replace(line, rep, 1)

def SWC(s):  # level slave_wait: scl_oen & ~sSCL (no 'just released' edge, no latch)
    a="    reg        slave_wait;      // slave inserts wait states"
    assert a in s
    s=s.replace(a,"    reg        slave_wait_r;\n    wire       slave_wait = scl_oen & ~sSCL;")
    return s.replace("slave_wait <=","slave_wait_r <=")
GT=TABLES['golden']
CODE={'START':1,'STOP':2,'READ':3,'WRITE':4}
CMDV={'START':"`I2C_CMD_START",'STOP':"`I2C_CMD_STOP",'READ':"`I2C_CMD_READ",'WRITE':"`I2C_CMD_WRITE"}
def drive(cmd,lev,first_set):
    C,D=lev[0],lev[1]
    s=f"scl_oen <= 1'b{C}; "
    if cmd=='WRITE':
        s+= "sda_oen <= din; " if first_set else ""
    else: s+=f"sda_oen <= 1'b{D}; "
    return s
def fsm(tabs, keep=False):
    # tabs: {'START':[...], 'WRITE':..., 'READ':..., 'STOP':...}; element 0 = decode tick
    dec=[]; items=[]
    for cmd,key in [('START','START'),('WRITE','WRITE1'),('READ','READ1'),('STOP','STOP')]:
        t=tabs[cmd]; g=GT[key]
        # decode-tick drive only if it differs from golden's decode level
        setd = False
        d0=''
        if t[0][:2]!=g[0][:2]:
            if cmd=='WRITE': d0="sda_oen <= din; "; setd=True
            else: d0=drive(cmd,t[0],True)
        if cmd=='START' and t[0][:2]==g[0][:2] and len(t)>1 and t[1][:2]=='10': d0="scl_oen <= 1'b1; sda_oen <= 1'b1; "  # release both at decode
        dec.append(f"                    {CMDV[cmd]}: begin typ <= 3'd{CODE[cmd]}; ph <= 4'd1; {d0}end\n")
        # sda_chk on last SCL-high tick of WRITE
        highs=[i for i,l in enumerate(t) if l[0]=='1' and i>0]
        chk = highs[-1] if (cmd=='WRITE' and highs) else -1
        start_two = (cmd=='START' and sum(1 for l in t[1:] if l[:2]=='11')>=2)
        for i in range(1,len(t)):
            lev=t[i]; last=lev.endswith('A')
            if cmd=='WRITE':
                if lev[1]=='1' or (lev[:2]=='01'): setd=True
                if lev[:2]=='00' and not setd: dr=f"scl_oen <= 1'b0; "
                else: dr=f"scl_oen <= 1'b{lev[0]}; sda_oen <= din; "; setd=True
            elif cmd=='START' and start_two and i==1 and lev[:2]=='11':
                dr="sda_oen <= 1'b1; "   # golden order: SDA first, keep SCL
            else: dr=drive(cmd,lev,True)
            if keep and cmd in ('WRITE','READ') and all(l[0]=='0' for l in t[1:i+1]):
                dr = dr.replace("scl_oen <= 1'b0; ","")
            ck = "sda_chk <= 1'b1; " if i==chk else "sda_chk <= 1'b0; "
            nx = "typ <= 3'd0; ph <= 4'd0; cmd_ack <= 1'b1; " if last else f"ph <= 4'd{i+1}; "
            items.append(f"                {{3'd{CODE[cmd]},4'd{i}}}: begin {dr}{ck}{nx}end\n")
    return f"""    always @(posedge clk or negedge nReset)
      if (!nReset)
      begin
          typ <= 3'd0; ph <= 4'd0; c_state <= idle;
          cmd_ack <= 1'b0; scl_oen <= 1'b1; sda_oen <= 1'b1; sda_chk <= 1'b0;
      end
      else if (rst | al)
      begin
          typ <= 3'd0; ph <= 4'd0; c_state <= idle;
          cmd_ack <= 1'b0; scl_oen <= 1'b1; sda_oen <= 1'b1; sda_chk <= 1'b0;
      end
      else
      begin
          cmd_ack <= 1'b0;
          c_state <= (typ != 3'd0) ? 18'd1 : 18'd0;
          if (clk_en)
          begin
            if (typ == 3'd0)
            begin
                sda_chk <= 1'b0;
                case (cmd)
{''.join(dec)}                    default: ;
                endcase
            end
            else
              case ({{typ,ph}})
{''.join(items)}                default: begin typ <= 3'd0; ph <= 4'd0; end
              endcase
          end
      end
"""
def build(design, factors):
    s=base
    if 'FSM' in factors or any(f.startswith('FSM_') for f in factors):
        T=TABLES[design]; tabs={}
        for cmd,key in [('START','START'),('WRITE','WRITE1'),('READ','READ1'),('STOP','STOP')]:
            use = ('FSM' in factors and f'-{cmd}' not in factors) or (f'FSM_{cmd}' in factors)
            tabs[cmd] = T[key] if (use and T[key]) else GT[key]
        i=s.index('    always @(posedge clk or negedge nReset)\n      if (!nReset)\n      begin\n          c_state <= idle;')
        j=s.index('    assign scl_o')
        s=s[:i]+fsm(tabs, keep=('KEEP' in factors))+s[j:]
        s=s.replace('    reg [17:0] c_state;','    reg [17:0] c_state; reg [2:0] typ; reg [3:0] ph;',1).replace('(|c_state & sto_condition','((typ!=3\'d0) & sto_condition')
        # keep c_state for |c_state usage
        s=s.replace("c_state <= (typ != 3'd0) ? 18'd1 : 18'd0;","c_state <= 18'd0;") if False else s
    if 'P1' in factors: s=P1(s)
    if 'P2' in factors: s=P2(s)
    if 'P3' in factors: s=P3(s)
    if 'AL' in factors: s=AL(s)
    if 'ALS' in factors: s=ALS(s)
    if 'W0' in factors: s=W0(s)
    if 'SWC' in factors: s=SWC(s)
    if 'CE0' in factors: s=CE0(s)
    if 'SWP' in factors: s=SWP(s)
    if 'ENA0' in factors: s=ENA0(s)
    if 'SW' in factors: s=SW(s)
    return s
if __name__=='__main__':
    d=sys.argv[1]; fac=sys.argv[2].split(',') if sys.argv[2] else []; out=sys.argv[3]
    open(out,'w').write(build(d,fac))
