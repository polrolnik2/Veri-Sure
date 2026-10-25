# closed-loop (per-TP reset) comparison vs gB: exact / timing-only (dedup-equal) / functional, overall and per port
import json, sys, collections
Q='/tmp/claude-0/-home-user-Veri-Sure/12bb865e-7a51-5506-b55a-e5ac7cf72a4a/scratchpad/qual/i2c_master_bit_ctrl'
M='i2c_master_bit_ctrl'
ports=['cmd_ack','busy','al','dout','scl_o','scl_oen','sda_o','sda_oen']
import os; G=json.load(open(f'{Q}/clwork/cl_out/{M}/'+os.environ.get('CLREF','gB')+'.json'))
def dd(rows):
    o=[]
    for r in rows:
        if not o or o[-1]!=r: o.append(r)
    return o
designs=sys.argv[1].split(',')
res={}
for d in designs:
    try: t=json.load(open(f'{Q}/clwork/cl_out/{M}/{d}.json'))
    except FileNotFoundError: continue
    c=collections.Counter(); pc=collections.Counter(); n=0
    for sr in G:
        for tp,g in G[sr].items():
            x=t[sr][tp]; n+=1
            gs=[tuple(r) for r in g]; xs=[tuple(r) for r in x]
            if gs==xs: c['exact']+=1
            elif dd(gs)==dd(xs): c['timing']+=1
            else: c['func']+=1
            for k,p in enumerate(ports):
                a=[r[k] for r in gs]; b=[r[k] for r in xs]
                if a==b: pc[p+':exact']+=1
                elif dd(a)==dd(b): pc[p+':timing']+=1
                else: pc[p+':func']+=1
    res[d]={'n':n,**{k:v/n for k,v in c.items()},**{k:v/n for k,v in pc.items()}}
    print(f"{d:13s} exact={c['exact']/n:.3f} timing={c['timing']/n:.3f} func={c['func']/n:.3f} | "+' '.join(f"{p}:{pc[p+':exact']/n:.2f}/{pc[p+':timing']/n:.2f}/{pc[p+':func']/n:.2f}" for p in ['cmd_ack','busy','al','dout','scl_oen','sda_oen']), flush=True)
json.dump(res,open(f'{Q}/h6_'+os.environ.get('CLREF','gB')+'.json','w'),indent=1)
