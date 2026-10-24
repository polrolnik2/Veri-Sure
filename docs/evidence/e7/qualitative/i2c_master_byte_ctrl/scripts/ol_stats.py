import json, sys, collections, gc
EQ='/tmp/claude-0/-home-user-Veri-Sure/12bb865e-7a51-5506-b55a-e5ac7cf72a4a/scratchpad/eq'
Q='/tmp/claude-0/-home-user-Veri-Sure/12bb865e-7a51-5506-b55a-e5ac7cf72a4a/scratchpad/qual/i2c_master_byte_ctrl'
M='i2c_master_byte_ctrl'
OUTS=['cmd_ack','ack_out','dout','i2c_busy','i2c_al','scl_o','scl_oen','sda_o','sda_oen']
D=['luna12.gen1','luna12.gen2','luna12.gen3','luna12.r0','luna12.final','luna13.gen1','luna13.gen2','luna13.gen3','luna13.final','luna14.gen1','luna14.gen2','luna14.gen3','luna14.r0','luna14.final']
if len(sys.argv)>1: D=sys.argv[1:]
outdir=sys.argv[0]
G=json.load(open(f'{EQ}/out/{M}/golden.json'))
def dedup(seq):
    o=[]
    for v in seq:
        if not o or o[-1]!=v: o.append(v)
    return o
res={}
# golden stats
gs={}
for r in G:
    c=collections.Counter()
    for tp,rows in G[r].items():
        for row in rows:
            for p,v in zip(OUTS,row): c[(p,v)]+=1
    gs[r]={f'{p}={v}':n for (p,v),n in c.items() if p!='dout'}
res['golden_value_counts']=gs
for d in D:
    X=json.load(open(f'{EQ}/out/{M}/{d}.json'))
    R={}
    for r in G:
        mm=collections.Counter(); n=0; xs=collections.Counter(); vals=collections.Counter()
        tp_ok=collections.Counter(); tp_order=collections.Counter(); tp_final=collections.Counter(); ntp=0
        for tp,grows in G[r].items():
            drows=X[r][tp]; ntp+=1
            assert len(drows)==len(grows)
            for gr,dr in zip(grows,drows):
                n+=1
                for i,p in enumerate(OUTS):
                    if gr[i]!=dr[i]: mm[p]+=1
                    if 'x' in dr[i]: xs[p]+=1
                    if p!='dout': vals[(p,dr[i])]+=1
            for i,p in enumerate(OUTS):
                gseq=[g[i] for g in grows]; dseq=[x[i] for x in drows]
                if gseq==dseq: tp_ok[p]+=1
                if dedup(gseq)==dedup(dseq): tp_order[p]+=1
                if gseq and gseq[-1]==dseq[-1]: tp_final[p]+=1
        R[r]={'n':n,'ntp':ntp,'match':{p:1-mm[p]/n for p in OUTS},'x':dict(xs),
              'tp_exact':{p:tp_ok[p]/ntp for p in OUTS},'tp_order':{p:tp_order[p]/ntp for p in OUTS},'tp_final':{p:tp_final[p]/ntp for p in OUTS},
              'vals':{f'{p}={v}':c for (p,v),c in vals.items()}}
    res[d]=R
    del X; gc.collect()
    print(d, 'done', flush=True)
json.dump(res,open(f'{Q}/ol_stats.json','w'),indent=0)
