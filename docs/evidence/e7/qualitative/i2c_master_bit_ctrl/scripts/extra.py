import sys, json, subprocess, os
Q='/tmp/claude-0/-home-user-Veri-Sure/12bb865e-7a51-5506-b55a-e5ac7cf72a4a/scratchpad/qual/i2c_master_bit_ctrl'
sys.path.insert(0,Q+'/scripts'); os.chdir(Q)
import composite
from habits import habits
from concurrent.futures import ThreadPoolExecutor
EQ='/tmp/claude-0/-home-user-Veri-Sure/12bb865e-7a51-5506-b55a-e5ac7cf72a4a/scratchpad/eq'
RT=json.load(open('reset_tps.json'))
def eqrow(a,b): return all('x' in y or x==y for x,y in zip(a[:8],b[:8]))
def agree(t,G):
    e=et=0
    for sr,tps in RT.items():
        for k in tps:
            g=G[sr][k]; x=t[sr][k]
            for i in range(1,len(g)): e+=eqrow(x[i],g[i]); et+=1
    return e/et
jobs=[(a.split(':')[0], a.split(':')[1].split('+') if ':' in a and a.split(':')[1] else []) for a in sys.argv[1:]]
def run(j):
    d,extra=j
    h=habits(d); f=[x for v in h.values() for x in v]+extra
    name=f"cy_{d}_{'_'.join(extra) or 'all'}"
    open(f'gv/{name}.v','w').write(composite.build(d,f))
    if not os.path.exists(f'work/{name}.json'):
        subprocess.run(['python3','scripts/simvar.py',name,f'gv/{name}.v'],capture_output=True,text=True)
    return j,name
with ThreadPoolExecutor(8) as ex: res=list(ex.map(run,jobs))
out=json.load(open('extra.json')) if os.path.exists('extra.json') else {}
cache={}
for (d,extra),name in res:
    if d not in cache: cache={d:json.load(open(f'{EQ}/out/i2c_master_bit_ctrl/{d}.json'))}
    a=agree(cache[d],json.load(open(f'work/{name}.json')))
    out[f"{d}:{'+'.join(extra)}"]=a
    print(d, extra, round(a,3), flush=True)
json.dump(out,open('extra.json','w'),indent=1)
