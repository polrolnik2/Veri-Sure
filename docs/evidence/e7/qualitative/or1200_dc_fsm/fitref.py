import json
from model import *
res = {}
for run in ['luna12','luna13','luna14']:
    tps, refs = stim(run)
    tr = {tp: [[None if v is None else int(v) for v in row] for row in refs[tp]] for tp in tps}
    def sc(fl):
        m = run_model_fresh(fl, tps); e, nm, p = compare(m, tr); return sum(p), nm, p, e
    cur=[]; best=sc(cur); base=best
    while True:
        c=[(sc(cur+[f]),f) for f in FLAGS if f not in cur]
        s,f=min(c,key=lambda x:x[0][0])
        if s[0]<best[0]: cur.append(f); best=s
        else: break
    for f in list(cur):
        t=[x for x in cur if x!=f]; s=sc(t)
        if s[0]<=best[0]: cur=t; best=s
    print(run,'ref base',base[:2],'of',base[3],'edges; flags',cur,'resid',best[:3])
    res[run]=dict(flags=cur, base=base[:2], resid=best[:3], edges=base[3])
json.dump(res, open('fitref.json','w'), indent=1)
