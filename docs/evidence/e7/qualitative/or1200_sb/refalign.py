from common import *
for run in RUNS:
    s=stim(run); ri=s['inputs'].index('rst')
    tps=s['tps']; first_rst=sum(1 for t in tps.values() if t['rows'][0][ri]==1)
    anyrst=sum(1 for t in tps.values() if any(r[ri]==1 for r in t['rows']))
    print(run,'tps',len(tps),'start with rst',first_rst,'contain rst',anyrst)
    for d in [f'{run}.r0',f'{run}.final',f'{run}.gen1']:
        t=trace(d)[run]
        n=ok=0; n2=ok2=0; npost=okpost=0
        for tp,tt in tps.items():
            # edges after first reset row
            fr=next((i for i,r in enumerate(tt['rows']) if r[ri]==1),None)
            for e,(row,ref) in enumerate(zip(tt['rows'],tt['ref'])):
                v=[toint(x) for x in t[tp][e]]
                n+=1; ok+= v==ref
                if fr is not None and e>fr: npost+=1; okpost+= v==ref
        print(f'   {d:14s} ref-agree all {ok/n:.3f}   after-first-reset {okpost/max(npost,1):.3f} ({npost} edges)')
