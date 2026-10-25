import json
from model import *
from collections import Counter
fit = json.load(open('fit.json'))
for run in ['luna12','luna13','luna14']:
    tps, refs = stim(run)
    rf = set(json.load(open(f'resetfirst_{run}.json')))
    for mode in ['fresh-model', 'traces-resetfirst']:
        if mode == 'fresh-model':
            R0 = run_model_fresh(fit[f'{run}.r0']['flags'], tps); FI = run_model_fresh(fit[f'{run}.final']['flags'], tps); G = run_model_fresh([], tps); keep = set(tps)
        else:
            R0 = load_trace(f'{run}.r0')[run]; FI = load_trace(f'{run}.final')[run]; G = load_trace('golden')[run]; keep = rf
        c = Counter(); n = 0; refag = Counter(); gag = Counter(); tot = 0
        for tp in tps:
            if tp not in keep: continue
            for e in range(len(tps[tp])):
                a, b, g = R0[tp][e], FI[tp][e], G[tp][e]; ref = [int(v) for v in refs[tp][e]]
                if a is None or b is None or g is None or None in a + b + g: continue
                tot += 1
                refag['r0'] += a == ref; refag['final'] += b == ref; gag['r0'] += a == g; gag['final'] += b == g
                if a == b: continue
                n += 1
                c[('G' if b == g else '-') + ('R' if b == ref else '-') + '|r0:' + ('G' if a == g else '-') + ('R' if a == ref else '-')] += 1
        fG = sum(v for k, v in c.items() if k[0] == 'G'); fR = sum(v for k, v in c.items() if k[1] == 'R')
        rG = sum(v for k, v in c.items() if k[5] == 'G'); rR = sum(v for k, v in c.items() if k[6] == 'R')
        print(f'{run} {mode}: edges {tot}; golden agree r0 {gag["r0"]/tot:.3f} final {gag["final"]/tot:.3f}; ref agree r0 {refag["r0"]/tot:.3f} final {refag["final"]/tot:.3f}')
        print(f'   r0!=final edges {n}: final=G {fG}, final=R {fR}; r0=G {rG}, r0=R {rR}; detail {dict(c)}')
