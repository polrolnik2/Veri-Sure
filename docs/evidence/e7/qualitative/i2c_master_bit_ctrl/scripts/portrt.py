# per-port edge mismatch rates vs a reference, reset-first TPs, edges>=1; also TP-level first-divergence port
import json, sys, collections
EQ='/tmp/claude-0/-home-user-Veri-Sure/12bb865e-7a51-5506-b55a-e5ac7cf72a4a/scratchpad/eq'
Q='/tmp/claude-0/-home-user-Veri-Sure/12bb865e-7a51-5506-b55a-e5ac7cf72a4a/scratchpad/qual/i2c_master_bit_ctrl'
M='i2c_master_bit_ctrl'
RT=json.load(open(f'{Q}/reset_tps.json'))
ports=['cmd_ack','busy','al','dout','scl_o','scl_oen','sda_o','sda_oen']
ref=sys.argv[1]
G=json.load(open(f'{Q}/work/{ref}.json'))
designs=sys.argv[2].split(',') if len(sys.argv)>2 else [f'{r}.{k}' for r in ['luna12','luna13','luna14','luna15'] for k in ['gen1','gen2','gen3','r0','final']]
for d in designs:
    t=json.load(open(f'{EQ}/out/{M}/{d}.json')) if '.' in d else json.load(open(f'{Q}/work/{d}.json'))
    n=0; pm=collections.Counter(); bad=0; tpok=0; fd=collections.Counter(); alx=collections.Counter()
    for sr,tps in RT.items():
        for k in tps:
            g=G[sr][k]; x=t[sr][k]; first=None
            for i in range(1,len(g)):
                n+=1
                w=[p for j,p in enumerate(ports) if 'x' not in g[i][j] and g[i][j]!=x[i][j]]
                if w:
                    bad+=1
                    if first is None: first=w
                for p in w: pm[p]+=1
                if 'al' in w: alx['d1g0' if x[i][2]=='1' else 'd0g1']+=1
            tpok+= first is None
            fd['+'.join(first) if first else 'MATCH']+=1
    print(f"{d:13s} agree={1-bad/n:.3f} tp={tpok/sum(len(v) for v in RT.values()):.3f} "+' '.join(f"{p}={pm[p]/n:.3f}" for p in ['cmd_ack','busy','al','dout','scl_oen','sda_oen']), dict(alx), fd.most_common(4), flush=True)
