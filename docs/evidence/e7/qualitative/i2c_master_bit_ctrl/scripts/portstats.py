import json, sys, collections
EQ='/tmp/claude-0/-home-user-Veri-Sure/12bb865e-7a51-5506-b55a-e5ac7cf72a4a/scratchpad/eq'
M='i2c_master_bit_ctrl'
OUT='/tmp/claude-0/-home-user-Veri-Sure/12bb865e-7a51-5506-b55a-e5ac7cf72a4a/scratchpad/qual/i2c_master_bit_ctrl'
ports=['cmd_ack','busy','al','dout','scl_o','scl_oen','sda_o','sda_oen']
g=json.load(open(f'{EQ}/out/{M}/golden.json'))
designs=[f'{r}.{k}' for r in ['luna12','luna13','luna14','luna15'] for k in ['gen1','gen2','gen3','r0','final']]
res={}
def dd(seq):
    o=[]
    for v in seq:
        if not o or o[-1]!=v: o.append(v)
    return o
for d in designs:
    t=json.load(open(f'{EQ}/out/{M}/{d}.json'))
    mis=collections.Counter(); tot=collections.Counter(); cell=collections.Counter(); ctot=collections.Counter(); order=collections.Counter()
    first=collections.Counter()
    xs=collections.Counter()
    for sr in g:
        for tp,gt in g[sr].items():
            dt=t[sr][tp]
            fd=None
            for k,p in enumerate(ports):
                ce=True
                gs=[]; ds=[]
                for i,(gr,dr) in enumerate(zip(gt,dt)):
                    gv=gr[k]; dv=dr[k]
                    if 'x' in dv and 'x' not in gv: xs[p]+=1
                    if 'x' in gv: continue
                    tot[p]+=1
                    if gv!=dv:
                        mis[p]+=1; ce=False
                        if fd is None or i<fd[0]: fd=(i,[p])
                        elif i==fd[0]: fd[1].append(p)
                    gs.append(gv); ds.append(dv)
                cell[p]+=ce; ctot[p]+=1
                order[p]+= dd(gs)==dd(ds)
            if fd: first['+'.join(fd[1])]+=1
            else: first['NONE']+=1
    res[d]={'mis':{p:mis[p]/tot[p] for p in ports},'cell':{p:cell[p]/ctot[p] for p in ports},'order':{p:order[p]/ctot[p] for p in ports},'first':dict(first),'xs':dict(xs)}
    print(d, ' '.join(f"{p}:{res[d]['mis'][p]:.3f}/{res[d]['cell'][p]:.2f}/{res[d]['order'][p]:.2f}" for p in ports), flush=True)
    print('   first-div:', first.most_common(6), 'x:',dict(xs), flush=True)
json.dump(res,open(f'{OUT}/portstats.json','w'),indent=1)
