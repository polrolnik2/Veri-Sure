import json
from model import *
from collections import Counter
fit = json.load(open('fit.json'))
for run in ['luna12','luna13','luna14']:
    tps, refs = stim(run)
    # actual traces (continuous) on own stimulus
    T = {k: load_trace(f'{run}.{k}')[run] for k in ['r0','final']}
    G = load_trace('golden')[run]
    c = Counter(); cp = Counter(); n=0
    for tp in tps:
        for e in range(len(tps[tp])):
            a, b, g = T['r0'][tp][e], T['final'][tp][e], G[tp][e]
            ref = refs[tp][e]
            if any(v is None for v in a+b+g): continue
            if a == b: continue
            n += 1
            fg = b == g; fr = b == ref; rg = a == g; rr = a == ref
            c[('final=gold' if fg else 'final!gold') + '/' + ('final=ref' if fr else 'final!ref')] += 1
            c['r0:' + ('=gold' if rg else '!gold') + '/' + ('=ref' if rr else '!ref')] += 1
            for k in range(10):
                if a[k] != b[k]: cp[OUTS[k]] += 1
    # per-cell version: cells where r0 and final differ
    cc = Counter()
    for tp in tps:
        for e in range(len(tps[tp])):
            a, b, g = T['r0'][tp][e], T['final'][tp][e], G[tp][e]; ref = refs[tp][e]
            for k in range(10):
                if a[k] is None or b[k] is None or g[k] is None: continue
                if a[k] != b[k]:
                    cc[('G' if b[k]==g[k] else '-') + ('R' if b[k]==ref[k] else '-')] += 1
    print(run, 'edges r0!=final:', n, dict(c)); print('   cells (final vs Golden/Ref):', dict(cc), 'ports', dict(cp))
