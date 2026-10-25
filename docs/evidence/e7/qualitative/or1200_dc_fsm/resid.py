import sys, json
from model import *
d = sys.argv[1]; flags = sys.argv[2].split(',') if sys.argv[2] else []
tr = load_trace(d); n=0
for r in ['luna12','luna13','luna14']:
    tps,_ = stim(r)
    m = run_model(flags, tps); g = run_model([], tps)
    for tp in tps:
        for e,(a,b) in enumerate(zip(m[tp], tr[r][tp])):
            if a is None or b is None: continue
            diff = [OUTS[k] for k in range(10) if b[k] is not None and a[k]!=b[k]]
            if diff:
                n+=1
                if n<=int(sys.argv[3] if len(sys.argv)>3 else 6):
                    lo=max(0,e-4)
                    print('==',r,tp,'edge',e,diff)
                    for j in range(lo,e+1):
                        print('  ',j,'in',tps[tp][j][:9],hex(tps[tp][j][9]),'model',m[tp][j][:9],'des',tr[r][tp][j][:9],'gold',g[tp][j][:9])
print('total',n)
