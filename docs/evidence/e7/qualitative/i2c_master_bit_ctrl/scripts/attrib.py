import json, sys, subprocess, os
from concurrent.futures import ThreadPoolExecutor
Q='/tmp/claude-0/-home-user-Veri-Sure/12bb865e-7a51-5506-b55a-e5ac7cf72a4a/scratchpad/qual/i2c_master_bit_ctrl'
EQ='/tmp/claude-0/-home-user-Veri-Sure/12bb865e-7a51-5506-b55a-e5ac7cf72a4a/scratchpad/eq'
M='i2c_master_bit_ctrl'
sys.path.insert(0,f'{Q}/scripts')
from habits import habits
import composite
RT=json.load(open(f'{Q}/reset_tps.json'))
designs=[f'{r}.{k}' for r in ['luna12','luna13','luna14','luna15'] for k in ['gen1','gen2','gen3','r0','final']]
if len(sys.argv)>1: designs=sys.argv[1].split(',')
jobs=[]
for d in designs:
    h=habits(d); allf=[f for v in h.values() for f in v]
    var={'all':allf}
    for k,v in h.items():
        var['-'+k]=[f for f in allf if f not in v]
        var['+'+k]=list(v)
    for c in ['START','WRITE','READ','STOP']:
        var['-'+c]=allf+['-'+c]
    for n,f in var.items():
        name=f'cx_{d}_{n}'.replace('+','p').replace('-','m')
        open(f'{Q}/gv/{name}.v','w').write(composite.build(d,f))
        jobs.append((d,n,name))
def sim(j):
    d,n,name=j
    if not os.path.exists(f'{Q}/work/{name}.json'):
        subprocess.run(['python3',f'{Q}/scripts/simvar.py',name,f'{Q}/gv/{name}.v'],capture_output=True,text=True)
    return j
with ThreadPoolExecutor(8) as ex: list(ex.map(sim,jobs))
def eqrow(a,b): return all('x' in y or x==y for x,y in zip(a[:8],b[:8]))
def agree(t,G):
    e=et=0
    for sr,tps in RT.items():
        for k in tps:
            g=G[sr][k]; x=t[sr][k]
            for i in range(1,len(g)):
                e+=eqrow(x[i],g[i]); et+=1
    return e/et
gB=json.load(open(f'{Q}/work/gB.json'))
res=json.load(open(f'{Q}/attrib.json')) if os.path.exists(f'{Q}/attrib.json') else {}
for d in designs:
    t=json.load(open(f'{EQ}/out/{M}/{d}.json'))
    r={'gB':agree(t,gB)}
    for (dd,n,name) in jobs:
        if dd!=d: continue
        r[n]=agree(t,json.load(open(f'{Q}/work/{name}.json')))
    res[d]=r
    print(d, ' '.join(f'{k}={v:.3f}' for k,v in r.items()), flush=True)
    json.dump(res,open(f'{Q}/attrib.json','w'),indent=1)
