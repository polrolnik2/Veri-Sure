# root-cause attribution: first divergence per testpoint vs gB, with golden internal state context
import json, collections, pickle, sys
EQ='/tmp/claude-0/-home-user-Veri-Sure/12bb865e-7a51-5506-b55a-e5ac7cf72a4a/scratchpad/eq'
Q='/tmp/claude-0/-home-user-Veri-Sure/12bb865e-7a51-5506-b55a-e5ac7cf72a4a/scratchpad/qual/i2c_master_bit_ctrl'
M='i2c_master_bit_ctrl'
ports=['cmd_ack','busy','al','dout','scl_o','scl_oen','sda_o','sda_oen']
SN={0:'idle',1:'start_a',2:'start_b',4:'start_c',8:'start_d',0x10:'start_e',0x20:'stop_a',0x40:'stop_b',0x80:'stop_c',0x100:'stop_d',0x200:'rd_a',0x400:'rd_b',0x800:'rd_c',0x1000:'rd_d',0x2000:'wr_a',0x4000:'wr_b',0x8000:'wr_c',0x10000:'wr_d'}
G=json.load(open(f'{Q}/work/gBp.json'))
stims={r:json.load(open(f'{EQ}/stim/{r}/{M}.json')) for r in G}
designs=[f'{r}.{k}' for r in ['luna12','luna13','luna14','luna15'] for k in ['gen1','gen2','gen3','r0','final']]
FD={}
for d in designs:
    t=json.load(open(f'{EQ}/out/{M}/{d}.json'))
    FD[d]={}
    for sr in G:
        ins=stims[sr]['inputs']
        for tp,gt in G[sr].items():
            dt=t[sr][tp]; rows=stims[sr]['tps'][tp]['rows']
            nbad=0; first=None
            for i in range(1,len(gt)):
                w=[p for k,p in enumerate(ports) if gt[i][k]!=dt[i][k] and 'x' not in gt[i][k]]
                if w:
                    nbad+=1
                    if first is None: first=(i,w)
            if first is None: FD[d][(sr,tp)]=None; continue
            i,w=first
            st=SN.get(int(gt[i][8],16),'?')
            prevst=[SN.get(int(gt[j][8],16),'?') for j in range(max(0,i-3),i)]
            info={'edge':i,'ports':w,'gstate':st,'prev':prevst,'nbad':nbad,'n':len(gt)-1,
                  'g':{p:gt[i][k] for k,p in enumerate(ports) if p in w},'d':{p:dt[i][k] for k,p in enumerate(ports) if p in w},
                  'galrecent':any(gt[j][2]=='1' for j in range(max(1,i-40),i+1)),
                  'clk_cnt':rows[i][ins.index('clk_cnt')],'cmd':rows[i][ins.index('cmd')]}
            # offset: smallest k such that design row i's value on first port equals golden at i+k (|k|<=80)
            p=w[0]; k0=ports.index(p); v=dt[i][k0]; off=None
            for kk in range(1,81):
                for s in (kk,-kk):
                    j=i+s
                    if 1<=j<len(gt) and gt[j][k0]==v:
                        off=s; break
                if off is not None: break
            info['off']=off
            FD[d][(sr,tp)]=info
    print(d,'done',flush=True)
pickle.dump(FD,open(f'{Q}/firstdiv.pkl','wb'))
