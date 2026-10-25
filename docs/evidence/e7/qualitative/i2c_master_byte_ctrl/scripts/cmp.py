"""cmp.py REF TRACE... -- per-port edge match, all-port edge match, tp-exact vs REF trace (pooled over stim runs)."""
import json, sys
OUTS=['cmd_ack','ack_out','dout','i2c_busy','i2c_al','scl_o','scl_oen','sda_o','sda_oen']
ref=json.load(open(sys.argv[1]))
for f in sys.argv[2:]:
    X=json.load(open(f)); n=0; e=0; t=0; nt=0; pm=[0]*9; per_run={}
    for r in ref:
        rn=re_=0
        for tp,g in ref[r].items():
            x=X[r][tp]; nt+=1; ok=True
            for a,b in zip(g,x):
                n+=1; rn+=1
                if a==b: e+=1; re_+=1
                else: ok=False
                for i in range(9):
                    if a[i]==b[i]: pm[i]+=1
            t+=ok
        per_run[r]=round(re_/rn,4)
    print(f.split('/')[-1], 'edge=%.4f tp=%.4f'%(e/n,t/nt), per_run, ' '.join('%s=%.3f'%(p,pm[i]/n) for i,p in enumerate(OUTS)))
