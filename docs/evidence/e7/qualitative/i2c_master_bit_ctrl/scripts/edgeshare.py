# for each design vs a reference trace set: share of edges mismatching, and per-port mismatch rate (edge-level), excluding edge 0
import json, sys, collections
EQ='/tmp/claude-0/-home-user-Veri-Sure/12bb865e-7a51-5506-b55a-e5ac7cf72a4a/scratchpad/eq'
Q='/tmp/claude-0/-home-user-Veri-Sure/12bb865e-7a51-5506-b55a-e5ac7cf72a4a/scratchpad/qual/i2c_master_bit_ctrl'
M='i2c_master_bit_ctrl'
ports=['cmd_ack','busy','al','dout','scl_o','scl_oen','sda_o','sda_oen']
refn=sys.argv[1]
G=json.load(open(f'{Q}/work/{refn}.json')) if refn!='golden' else json.load(open(f'{EQ}/out/{M}/golden.json'))
designs=sys.argv[2].split(',') if len(sys.argv)>2 else [f'{r}.{k}' for r in ['luna12','luna13','luna14','luna15'] for k in ['gen1','gen2','gen3','r0','final']]
out={}
for d in designs:
    t=json.load(open(f'{EQ}/out/{M}/{d}.json')) if '.' in d else json.load(open(f'{Q}/work/{d}.json'))
    n=bad=0; pm=collections.Counter()
    for sr in G:
        for tp,gt in G[sr].items():
            for a,b in zip(gt[1:],t[sr][tp][1:]):
                n+=1
                w=[p for p,x,y in zip(ports,a,b) if 'x' not in x and x!=y]
                if w: bad+=1
                for p in w: pm[p]+=1
    out[d]={'edge_agree':1-bad/n, **{p:pm[p]/n for p in ['cmd_ack','busy','al','dout','scl_oen','sda_oen']}}
    print(f"{d:14s} agree={1-bad/n:.3f} " + ' '.join(f"{p}={pm[p]/n:.3f}" for p in ['cmd_ack','busy','al','dout','scl_oen','sda_oen']), flush=True)
json.dump(out,open(f'{Q}/edgeshare_{refn}.json','w'),indent=1)
