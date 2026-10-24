import json
from model import EQ
def dedup(rows):
    out=[]
    for r in rows:
        if not out or out[-1]!=r: out.append(r)
    return out
G=json.loads((EQ/'cl_out/or1200_dc_fsm/golden.json').read_text())
for d in [f'{r}.{k}' for r in ['luna12','luna13','luna14'] for k in ['gen1','gen2','gen3','r0','final']]:
    D=json.loads((EQ/'cl_out/or1200_dc_fsm'/f'{d}.json').read_text())
    tot=exact=dd=func=0
    for run in G:
        for tp in G[run]:
            a,b=G[run][tp],D[run].get(tp)
            if b is None or isinstance(a,str): continue
            tot+=1
            if a==b: exact+=1
            elif dedup(a)==dedup(b): dd+=1
            else: func+=1
    print(d, 'tps',tot,'exact',exact,'dedup-equal-only',dd,'functional',func, 'timing share of errors %.3f'%(dd/max(1,dd+func)))
