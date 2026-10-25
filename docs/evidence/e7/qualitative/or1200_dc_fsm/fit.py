import sys, json
from model import *
STIM = {r: stim(r)[0] for r in ['luna12','luna13','luna14']}
def score(flags, tr):
    tot = 0; ports=[0]*10; ne=0
    for r in STIM:
        m = run_model(flags, STIM[r])
        e, nm, p = compare(m, tr[r])
        tot += sum(p); ne+=nm
        ports = [a+b for a,b in zip(ports,p)]
    return tot, ne, ports
designs = [f'{r}.{k}' for r in ['luna12','luna13','luna14'] for k in ['gen1','gen2','gen3','r0','final']]
if len(sys.argv)>1: designs = sys.argv[1:]
res = {}
for d in designs:
    tr = load_trace(d)
    cur = []; best = score(cur, tr)
    base = best
    while True:
        cands = [(score(cur+[f], tr), f) for f in FLAGS if f not in cur]
        sc, f = min(cands, key=lambda x: x[0][0])
        if sc[0] < best[0]:
            cur.append(f); best = sc
        else: break
    # backward pruning
    for f in list(cur):
        t = [x for x in cur if x != f]
        sc = score(t, tr)
        if sc[0] <= best[0]: cur = t; best = sc
    res[d] = dict(flags=cur, base_cells=base[0], base_edges=base[1], resid_cells=best[0], resid_edges=best[1], resid_ports=best[2])
    print(d, 'base', base[:2], 'flags', cur, 'resid', best[0], best[1], best[2], flush=True)
json.dump(res, open('fit.json','w'), indent=1)
