"""Closed loop, reset-started testpoints only: per port, exact / dedup-equal (timing-like) / dedup-unequal (functional)."""
import json, collections, gc
EQ='/tmp/claude-0/-home-user-Veri-Sure/12bb865e-7a51-5506-b55a-e5ac7cf72a4a/scratchpad/eq'
Q='/tmp/claude-0/-home-user-Veri-Sure/12bb865e-7a51-5506-b55a-e5ac7cf72a4a/scratchpad/qual/i2c_master_byte_ctrl'
OUTS=['cmd_ack','ack_out','dout','i2c_busy','i2c_al','scl_o','scl_oen','sda_o','sda_oen']
RT=json.load(open(f'{Q}/reset_tps.json'))
D=['luna12.gen1','luna12.gen2','luna12.gen3','luna12.r0','luna12.final','luna13.gen1','luna13.gen2','luna13.gen3','luna13.final','luna14.gen1','luna14.gen2','luna14.gen3','luna14.r0','luna14.final']
def dd(s):
    o=[]
    for v in s:
        if not o or o[-1]!=v: o.append(v)
    return o
G=json.load(open(f'{EQ}/cl_out/i2c_master_byte_ctrl/golden.json'))
G={r:{tp:G[r][tp] for tp in RT[r] if tp in G[r]} for r in RT}
res={}
for d in D:
    X=json.load(open(f'{EQ}/cl_out/i2c_master_byte_ctrl/{d}.json'))
    c=collections.Counter(); pc=collections.defaultdict(collections.Counter); n=0
    for r in RT:
        for tp,g in G[r].items():
            x=X[r].get(tp)
            if x is None: continue
            n+=1
            if x==g: c['exact']+=1
            elif dd([tuple(v) for v in x])==dd([tuple(v) for v in g]): c['order']+=1
            else: c['func']+=1
            for i,p in enumerate(OUTS):
                gs=[v[i] for v in g]; xs=[v[i] for v in x]
                k='exact' if gs==xs else 'order' if dd(gs)==dd(xs) else 'func'
                pc[p][k]+=1
    res[d]={'n':n,'all':dict(c),'port':{p:dict(v) for p,v in pc.items()}}
    print(d,n,dict(c),' func share per port:',{p[:7]:round(pc[p]['func']/n,2) for p in OUTS if p not in('scl_o','sda_o')},flush=True)
    del X; gc.collect()
json.dump(res,open(f'{Q}/cl_reset.json','w'))
