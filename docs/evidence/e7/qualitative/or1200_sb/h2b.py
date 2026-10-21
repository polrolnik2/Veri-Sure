from common import *
from collections import Counter
for run in ['luna12','luna13']:
    s=stim(run); ri=s['inputs'].index('rst')
    r0=trace(f'{run}.r0')[run]; fi=trace(f'{run}.final')[run]
    C=Counter(); R=Counter(); n=0
    for tp,tt in s['tps'].items():
        fr=next((i for i,r in enumerate(tt['rows']) if r[ri]==1),None)
        if fr is None: continue
        for e,(row,ref) in enumerate(zip(tt['rows'],tt['ref'])):
            if e<=fr: continue
            a=[toint(x) for x in r0[tp][e]]; b=[toint(x) for x in fi[tp][e]]; g=passthru(s['inputs'],row)
            n+=1
            if a==b: continue
            C['both' if b==g and b==ref else 'golden' if b==g else 'ref' if b==ref else 'neither']+=1
            R['both' if a==g and a==ref else 'golden' if a==g else 'ref' if a==ref else 'neither']+=1
    print(run,'post-reset edges',n,'differ',sum(C.values()),'final agrees:',dict(C),' r0 agrees:',dict(R))
