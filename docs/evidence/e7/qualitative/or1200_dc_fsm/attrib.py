import json
from model import *
from collections import defaultdict
STIM = {r: stim(r)[0] for r in ['luna12','luna13','luna14']}
G = {r: run_model([], STIM[r]) for r in STIM}
def mism(flags):
    tot=0; ports=[0]*10; ne=0; edges=set()
    for r in STIM:
        m = run_model(flags, STIM[r])
        for tp in m:
            for e,(a,b) in enumerate(zip(m[tp], G[r][tp])):
                if a is None or b is None: continue
                ne+=1
                d=[k for k in range(10) if a[k]!=b[k]]
                if d:
                    edges.add((r,tp,e))
                    for k in d: ports[k]+=1
    return edges, ports, ne
fit = json.load(open('fit.json'))
single = {}
for f in FLAGS:
    e,p,ne = mism([f])
    single[f]=dict(edges=len(e), ports=dict(zip(OUTS,p)))
    print('single', f, len(e), 'of', ne, {OUTS[k]:p[k] for k in range(10) if p[k]})
loo = {}
for d,v in fit.items():
    F=v['flags']; E,P,ne = mism(F)
    row={'total':len(E)}
    for f in F:
        E2,_,_ = mism([x for x in F if x!=f])
        row[f]=len(E)-len(E2)
    # exclusive attribution: edges that disappear when f alone is added to golden? use 'only-f' edges
    loo[d]=row
    print(d, row)
json.dump(dict(single=single, loo=loo), open('attrib.json','w'), indent=1)
