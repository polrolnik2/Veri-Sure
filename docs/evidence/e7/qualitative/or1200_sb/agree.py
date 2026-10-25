from common import *
import sys
res={}
print('design        | g_edge(own,all) | ref_edge own | ref_edge all-stims-avg | per-port mismatch vs golden (all stims, %)')
for d in DESIGNS:
    t=trace(d); own=d.split('.')[0]
    tot=0; gok=0; rok_own=0; n_own=0; gok_own=0; rok_all=0
    port_g=[0]*10; port_r=[0]*10; xcnt=0
    for sr in RUNS:
        s=stim(sr)
        for tp,tt in s['tps'].items():
            for e,(row,ref,o) in enumerate(zip(tt['rows'],tt['ref'],t[sr][tp])):
                pt=passthru(s['inputs'],row); v=[toint(x) for x in o]
                if None in v: xcnt+=1
                tot+=1
                ge = v==pt; re_= v==ref
                gok+=ge; rok_all+=re_
                for k in range(10):
                    if v[k]!=pt[k]: port_g[k]+=1
                    if v[k]!=ref[k]: port_r[k]+=1
                if sr==own:
                    n_own+=1; gok_own+=ge; rok_own+=re_
    print(f'{d:14s}| {gok_own/n_own:.3f},{gok/tot:.3f} | {rok_own/n_own:.3f} | {rok_all/tot:.3f} | '+' '.join(f'{p[:-2]}={100*c/tot:.1f}' for p,c in zip(OUTS,port_g)), 'x-edges',xcnt)
    print(f'{"":14s}  vs-ref per port: '+' '.join(f'{p[:-2]}={100*c/tot:.1f}' for p,c in zip(OUTS,port_r)))
