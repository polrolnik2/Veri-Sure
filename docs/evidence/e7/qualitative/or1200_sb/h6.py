from common import *
g=trace('golden',cl=True)
def dedup(t):
    out=[]
    for r in t:
        if not out or out[-1]!=r: out.append(r)
    return out
print('design        exact  dedup-eq-only(timing)  functional  (fraction of TPs, all stims)')
for d in DESIGNS:
    t=trace(d,cl=True); n=ex=tm=fn=0
    for sr in RUNS:
        for tp,gt in g[sr].items():
            dt=t[sr].get(tp)
            if not isinstance(dt,list) or not isinstance(gt,list): continue
            n+=1
            if dt==gt: ex+=1
            elif dedup(dt)==dedup(gt): tm+=1
            else: fn+=1
    print(f'{d:14s} {ex/n:.3f}  {tm/n:.3f}  {fn/n:.3f}  (n={n})')
