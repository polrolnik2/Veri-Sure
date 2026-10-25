from common import *
g=trace('golden')
for sr in RUNS:
    s=stim(sr); n=0; bad=0; refbad=0; refx=0
    for tp,t in s['tps'].items():
        gt=g[sr][tp]
        assert len(gt)==len(t['rows']), (sr,tp,len(gt),len(t['rows']))
        for e,(row,ref,go) in enumerate(zip(t['rows'],t['ref'],gt)):
            pt=passthru(s['inputs'],row); gv=[toint(x) for x in go]
            n+=1
            if pt!=gv: bad+=1
            if any(r is None for r in ref): refx+=1
            if ref!=gv: refbad+=1
    print(sr,'edges',n,'golden!=passthru',bad,'ref!=golden',refbad,'ref has None',refx)
