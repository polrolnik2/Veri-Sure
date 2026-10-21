"""Closed loop: per design, testpoints exact / dedup-equal-only (timing) / functional (dedup differs).
For functional TPs, check whether dedup equality is restored by (a) ignoring the 7ff4-vs-7ff8 payload (M1),
(b) additionally dropping leading reset-row carry-over (first distinct row)."""
import json, collections, sys
EQ = '/tmp/claude-0/-home-user-Veri-Sure/12bb865e-7a51-5506-b55a-e5ac7cf72a4a/scratchpad/eq'
RUNS = ['luna12', 'luna13', 'luna14', 'luna15']
DES = [f'{r}.{k}' for r in RUNS for k in ['gen1', 'gen2', 'gen3', 'r0', 'final'] if not (r == 'luna14' and k == 'r0')]
gold = json.load(open(f'{EQ}/cl_out/fpu_exceptions/golden.json'))

def dedup(t):
    o = []
    for r in t:
        r = tuple(r)
        if not o or o[-1] != r:
            o.append(r)
    return o

def m1norm(t):
    # map golden-style generated NaN 7ff4/fff4 payload to the 7ff8 form so M1 is ignored
    out = []
    for r in t:
        v = r[0]
        try:
            x = int(v, 16)
            if ((x >> 52) & 0x7ff) == 0x7ff and ((x >> 50) & 3) == 1:
                x = (x & ~(3 << 50)) | (2 << 50)
                v = '%016x' % x
        except ValueError:
            pass
        out.append((v,) + tuple(r[1:]))
    return out

res = {}
for d in DES:
    tr = json.load(open(f'{EQ}/cl_out/fpu_exceptions/{d}.json'))
    c = collections.Counter()
    for r in RUNS:
        for tp, gt in gold[r].items():
            dt = tr[r][tp]
            c['n'] += 1
            if gt == dt:
                c['exact'] += 1; continue
            gd, dd = dedup(gt), dedup(dt)
            if gd == dd:
                c['timing'] += 1; continue
            c['func'] += 1
            gd1, dd1 = dedup(m1norm(gt)), dedup(m1norm(dt))
            if gd1 == dd1:
                c['func_M1only'] += 1; continue
            if gd1[1:] == dd1 or gd1 == dd1[1:] or gd1[1:] == dd1[1:]:
                c['func_M1+leadrow'] += 1
            pass
        for r in RUNS:
            for tp, gt in gold[r].items():
                dt = tr[r][tp]
                gn, dn = m1norm(gt), m1norm(dt)
                for pi in range(7):
                    gp = [x[pi] for x in gt]; dp = [x[pi] for x in dt]
                    c['pp_n'] += 1
                    if gp == dp: c['pp_exact'] += 1
                    elif dedup([(x,) for x in gp]) == dedup([(x,) for x in dp]): c['pp_timing'] += 1
                    elif dedup([(x[pi],) for x in gn]) == dedup([(x[pi],) for x in dn]): c['pp_func_M1'] += 1
                    else: c['pp_func'] += 1; c['pp_func_'+str(pi)] += 1
    res[d] = dict(c)
    n = c['n']
    print(f"{d:13s} exact {100*c['exact']/n:5.1f}  timing-only {100*c['timing']/n:5.1f}  functional {100*c['func']/n:5.1f}  "
          f"(of which M1-only {100*c['func_M1only']/n:5.1f}, M1+leading-row {100*c['func_M1+leadrow']/n:5.1f})")
    pn=c['pp_n']; print('      per-port: exact %.1f timing %.1f func(M1 only) %.1f func(other) %.1f  other-func by port %s' % (100*c['pp_exact']/pn,100*c['pp_timing']/pn,100*c['pp_func_M1']/pn,100*c['pp_func']/pn, [c['pp_func_'+str(i)] for i in range(7)]))
    del tr
json.dump(res, open('closed.json', 'w'))
