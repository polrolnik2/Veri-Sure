from common import *
from collections import Counter
for run in RUNS:
    r0=trace(f'{run}.r0'); fi=trace(f'{run}.final'); s=stim(run)
    for sr in [run]:
        C=Counter(); P=Counter(); n=0; r0c=Counter()
        for tp,tt in s['tps'].items():
            for e,(row,ref) in enumerate(zip(tt['rows'],tt['ref'])):
                a=[toint(x) for x in r0[sr][tp][e]]; b=[toint(x) for x in fi[sr][tp][e]]
                n+=1
                if a==b: continue
                g=passthru(s['inputs'],row)
                fg=b==g; fr=b==ref; ag=a==g; ar=a==ref
                C[('final', 'both' if fg and fr else 'golden' if fg else 'ref' if fr else 'neither')]+=1
                r0c[('r0', 'both' if ag and ar else 'golden' if ag else 'ref' if ar else 'neither')]+=1
                for k in range(10):
                    if a[k]!=b[k]:
                        P[(OUTS[k], 'f=ref' if b[k]==ref[k] else 'f!=ref', 'r0=ref' if a[k]==ref[k] else 'r0!=ref', 'f=g' if b[k]==g[k] else 'f!=g')]+=1
        tot=sum(C.values())
        print(f'== {run} own-stim edges {n}; r0!=final at {tot} edges ({100*tot/n:.1f}%)')
        print('   final agrees with:', dict(C)); print('   r0 agrees with:', dict(r0c))
        for k,v in P.most_common(12): print('    ',k,v)
