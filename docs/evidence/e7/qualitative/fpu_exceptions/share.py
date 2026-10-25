"""Share of open-loop port-edge disagreement with golden per category (mode / timing / unsettled / reset rows),
per design and pooled by arm."""
import json, collections
exec(open('modes.py').read().split('def main')[0])
EQ = '/tmp/claude-0/-home-user-Veri-Sure/12bb865e-7a51-5506-b55a-e5ac7cf72a4a/scratchpad/eq'
RUNS = ['luna12', 'luna13', 'luna14', 'luna15']
stims = {r: json.load(open(f'{EQ}/stim/{r}/fpu_exceptions.json')) for r in RUNS}
gold = json.load(open(f'{EQ}/out/fpu_exceptions/golden.json'))
segmap = {(s['run'], s['tp'], s['e']): s for s in D['segs']}
gsig = {}
lab = {}
for r in RUNS:
    for tp, v in stims[r]['tps'].items():
        rows = v['rows']; s = 0; L = [None] * len(rows)
        for k in range(1, len(rows) + 1):
            if k == len(rows) or rows[k] != rows[s]:
                for j in range(s, k):
                    L[j] = (k - 1) if k - s >= 12 else None
                s = k
        lab[(r, tp)] = L
import os
RSF = bool(os.environ.get('RS'))
from rs import keep
tot = {}
for d in D['designs']:
    tr = json.load(open(f'{EQ}/out/fpu_exceptions/{d}.json'))
    c = collections.Counter()
    for r in RUNS:
        for tp, gt in gold[r].items():
            dt = tr[r][tp]; rows = stims[r]['tps'][tp]['rows']; L = lab[(r, tp)]
            for e in range(len(gt)):
                if RSF and not keep(r, tp, e):
                    continue
                for pi, p in enumerate(O):
                    c['_pe'] += 1
                    if gt[e][pi] == dt[e][pi]:
                        continue
                    if rows[e][1] == 1:
                        k = 'reset row'
                    elif L[e] is None:
                        k = 'unsettled (short segment)'
                    else:
                        s = segmap[(r, tp, L[e])]
                        gv, dv = h(s['g'][pi]), h(s[d][pi])
                        if gv == dv:
                            k = 'timing (settled equal)'
                        else:
                            key = (r, tp, L[e])
                            if key not in gsig: gsig[key] = gold_sig(s)
                            k = mode(s, gsig[key], p, gv, dv)
                    c[k] += 1
    tot[d] = c
    del tr
json.dump({d: dict(c) for d, c in tot.items()}, open('share_rs.json' if RSF else 'share.json', 'w'))
cats = sorted({k for c in tot.values() for k in c if k != '_pe'}, key=lambda k: -sum(c[k] for c in tot.values()))
for arm, ds in [('generated', [d for d in tot if not d.endswith('final')]), ('repaired', [d for d in tot if d.endswith('final')])]:
    allmm = sum(sum(v for k, v in tot[d].items() if k != '_pe') for d in ds)
    pe = sum(tot[d]['_pe'] for d in ds)
    print(f'== {arm}: {len(ds)} designs, port-edge mismatch {100*allmm/pe:.2f}% of port-edges')
    for k in cats:
        n = sum(tot[d][k] for d in ds)
        if n: print(f'   {k:58s} {100*n/allmm:5.1f}% of disagreement')
print()
for d in tot:
    allmm = sum(v for k, v in tot[d].items() if k != '_pe')
    print(d, {k.split(' ')[0]: round(100 * tot[d][k] / allmm, 1) for k in cats if tot[d][k]})
