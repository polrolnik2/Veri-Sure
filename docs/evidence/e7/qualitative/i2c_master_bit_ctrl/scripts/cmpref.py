# compare all designs against a set of reference traces (golden variants); X in ref = don't care
import json, sys, collections
EQ='/tmp/claude-0/-home-user-Veri-Sure/12bb865e-7a51-5506-b55a-e5ac7cf72a4a/scratchpad/eq'
Q='/tmp/claude-0/-home-user-Veri-Sure/12bb865e-7a51-5506-b55a-e5ac7cf72a4a/scratchpad/qual/i2c_master_bit_ctrl'
M='i2c_master_bit_ctrl'
ports=['cmd_ack','busy','al','dout','scl_o','scl_oen','sda_o','sda_oen']
refs={n:json.load(open(f'{Q}/work/{n}.json')) for n in sys.argv[1].split(',')}
skip0 = len(sys.argv)>2 and sys.argv[2]=='skip0'
designs=[f'{r}.{k}' for r in ['luna12','luna13','luna14','luna15'] for k in ['gen1','gen2','gen3','r0','final']]
def eq(a,b): return all('x' in y or x==y for x,y in zip(a,b))
print('design', *[f'{n}:edge/tp/cell[k b a d C D]' for n in refs])
for d in designs:
    t=json.load(open(f'{EQ}/out/{M}/{d}.json'))
    out=[]
    for n,G in refs.items():
        e=et=tp=tt=0; cell=collections.Counter(); ct=0
        for sr in G:
            for k,gt in G[sr].items():
                dt=t[sr][k]
                st=1 if skip0 else 0
                pairs=list(zip(gt[st:],dt[st:]))
                ok=[eq(b,a) for a,b in pairs]
                e+=sum(ok); et+=len(ok); tp+=all(ok); tt+=1; ct+=1
                for pi,p in enumerate(ports):
                    cell[p]+=all('x' in a[pi] or a[pi]==b[pi] for a,b in pairs)
        out.append(f"{e/et:.3f}/{tp/tt:.3f}/" + ' '.join(f"{cell[p]/ct:.2f}" for p in ['cmd_ack','busy','al','dout','scl_oen','sda_oen']))
    print(d, *out, flush=True)
