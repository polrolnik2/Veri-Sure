import json, collections, sys
EQ='/tmp/claude-0/-home-user-Veri-Sure/12bb865e-7a51-5506-b55a-e5ac7cf72a4a/scratchpad/eq'
SN={0:'idle',1:'start_a',2:'start_b',4:'start_c',8:'start_d',0x10:'start_e',0x20:'stop_a',0x40:'stop_b',0x80:'stop_c',0x100:'stop_d',0x200:'rd_a',0x400:'rd_b',0x800:'rd_c',0x1000:'rd_d',0x2000:'wr_a',0x4000:'wr_b',0x8000:'wr_c',0x10000:'wr_d'}
RT=json.load(open('reset_tps.json')); G=json.load(open('work/gBp.json'))
ports=['cmd_ack','busy','al','dout','scl_o','scl_oen','sda_o','sda_oen']
d=sys.argv[1]; comp=sys.argv[2]
t=json.load(open(f'{EQ}/out/i2c_master_bit_ctrl/{d}.json')); C=json.load(open(f'work/{comp}.json'))
c=collections.Counter(); ex={}
bad=0
for sr,tps in RT.items():
    for tp in tps:
        x=t[sr][tp]; y=C[sr][tp]; g=G[sr][tp]
        nb=sum(1 for i in range(1,len(g)) if x[i]!=y[i]); bad+=nb
        for i in range(1,len(g)):
            if x[i]!=y[i]:
                w=[p for k,p in enumerate(ports) if x[i][k]!=y[i][k]]
                key=(SN.get(int(g[i][8],16)),'+'.join(w),'d='+''.join(x[i][k] for k,p in enumerate(ports) if p in w),'c='+''.join(y[i][k] for k,p in enumerate(ports) if p in w))
                c[key]+=nb; ex.setdefault(key,(sr,tp,i))
                break
print(d,'vs',comp,'residual edges',bad)
for k,v in c.most_common(10): print('  ',round(v/bad,3),k,ex[k])
