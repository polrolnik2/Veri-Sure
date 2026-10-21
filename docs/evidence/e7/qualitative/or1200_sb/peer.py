from common import *
buf=['luna12.gen1','luna12.gen2','luna12.gen3','luna12.r0','luna12.final','luna13.final','luna14.gen1']
T={d:trace(d) for d in buf}
print(' '*14+' '.join(f'{d[4:]:>8s}' for d in buf))
for a in buf:
    row=[]
    for b in buf:
        n=ok=0
        for sr in RUNS:
            for tp,ta in T[a][sr].items():
                tb=T[b][sr][tp]
                for x,y in zip(ta,tb):
                    n+=1; ok+= x==y
        row.append(ok/n)
    print(f'{a:14s}'+' '.join(f'{v:8.3f}' for v in row))
# also exact per-tp agreement for final pairs
