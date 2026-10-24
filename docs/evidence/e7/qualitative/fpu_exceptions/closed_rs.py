"""Closed loop on reset-start testpoints only, dropping the first (reset) row of every trace."""
import json, collections
exec(open('closed.py').read().split('res = {}')[0])
from rs import RESET_START
res = {}
for d in DES:
    tr = json.load(open(f'{EQ}/cl_out/fpu_exceptions/{d}.json'))
    c = collections.Counter()
    for r in RUNS:
        for tp, gt0 in gold[r].items():
            if tp not in RESET_START[r]: continue
            gt = gt0[1:]; dt = tr[r][tp][1:]
            c['n'] += 1
            if gt == dt: c['exact'] += 1
            elif dedup(gt) == dedup(dt): c['timing'] += 1
            elif dedup(m1norm(gt)) == dedup(m1norm(dt)): c['func_M1only'] += 1
            else: c['func'] += 1
            gn, dn = m1norm(gt), m1norm(dt)
            for pi in range(7):
                gp = [x[pi] for x in gt]; dp = [x[pi] for x in dt]
                c['pp_n'] += 1
                if gp == dp: c['pp_exact'] += 1
                elif dedup([(x,) for x in gp]) == dedup([(x,) for x in dp]): c['pp_timing'] += 1
                elif dedup([(x[pi],) for x in gn]) == dedup([(x[pi],) for x in dn]): c['pp_M1'] += 1
                else: c['pp_func'] += 1
    res[d] = dict(c); n = c['n']; pn = c['pp_n']
    print(f"{d:13s} TPs {n}: exact {100*c['exact']/n:5.1f} timing-only {100*c['timing']/n:5.1f} M1-only {100*c['func_M1only']/n:5.1f} functional {100*c['func']/n:5.1f} | per-port exact {100*c['pp_exact']/pn:5.1f} timing {100*c['pp_timing']/pn:5.1f} M1 {100*c['pp_M1']/pn:4.1f} func {100*c['pp_func']/pn:5.1f}")
    del tr
json.dump(res, open('closed_rs.json', 'w'))
