# edge agreement of each design vs gB and vs each golden mutant, reset-first TPs only, edges>=1
import json, sys
EQ='/tmp/claude-0/-home-user-Veri-Sure/12bb865e-7a51-5506-b55a-e5ac7cf72a4a/scratchpad/eq'
Q='/tmp/claude-0/-home-user-Veri-Sure/12bb865e-7a51-5506-b55a-e5ac7cf72a4a/scratchpad/qual/i2c_master_bit_ctrl'
M='i2c_master_bit_ctrl'
RT=json.load(open(f'{Q}/reset_tps.json'))
refs=sys.argv[1].split(',')
designs=[f'{r}.{k}' for r in ['luna12','luna13','luna14','luna15'] for k in ['gen1','gen2','gen3','r0','final']]
R={n:json.load(open(f'{Q}/work/{n}.json')) for n in refs}
def eqrow(a,b): return all('x' in y or x==y for x,y in zip(a[:8],b[:8]))
out={}
hdr='design         '+' '.join(f'{n:>6s}' for n in refs)
print(hdr)
for d in designs:
    t=json.load(open(f'{EQ}/out/{M}/{d}.json'))
    row={}
    for n in refs:
        e=et=tp=0
        for sr,tps in RT.items():
            for k in tps:
                g=R[n][sr][k]; x=t[sr][k]
                ok=[eqrow(x[i],g[i]) for i in range(1,len(g))]
                e+=sum(ok); et+=len(ok); tp+=all(ok)
        row[n]=(e/et, tp/sum(len(v) for v in RT.values()))
    out[d]=row
    print(f'{d:14s} '+' '.join(f'{row[n][0]:6.3f}' for n in refs), flush=True)
json.dump(out,open(f'{Q}/mutcmp_base.json','w'),indent=1)
