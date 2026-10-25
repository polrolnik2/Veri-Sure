import json, statistics as st
Q='/tmp/claude-0/-home-user-Veri-Sure/12bb865e-7a51-5506-b55a-e5ac7cf72a4a/scratchpad/qual/i2c_master_bit_ctrl'
A=json.load(open(f'{Q}/attrib.json'))
facs=['PIPE','FSM','START','WRITE','READ','STOP','AL','W0']
rows={}
print(f"{'design':13s} {'D0':>5s} {'all':>5s} expl | LOO share of D0: "+' '.join(f'{f:>5s}' for f in facs))
for d,r in sorted(A.items()):
    D0=1-r['gB']; Dall=1-r['all']
    loo={}
    for f in facs:
        k='-'+f
        if k in r: loo[f]=(r['all']-r[k])/D0
    rows[d]=dict(D0=D0,expl=(D0-Dall)/D0,**loo)
    print(f"{d:13s} {D0:5.3f} {r['all']:5.3f} {(D0-Dall)/D0:5.2f} | "+' '.join(f"{loo.get(f,float('nan')):5.2f}" for f in facs))
for arm,ks in [('generated',['gen1','gen2','gen3','r0']),('repaired',['final'])]:
    sel=[v for k,v in rows.items() if k.split('.')[1] in ks]
    print(arm,len(sel),'D0',round(st.mean(x['D0'] for x in sel),3),'explained',round(st.mean(x['expl'] for x in sel),3), ' '.join(f"{f}={st.mean(x.get(f,0) for x in sel):.3f}" for f in facs))
json.dump(rows,open(f'{Q}/attrib_sum.json','w'),indent=1)
