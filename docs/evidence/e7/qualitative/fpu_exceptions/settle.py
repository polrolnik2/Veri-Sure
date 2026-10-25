"""Settled (steady-state) comparison of every design vs golden, per segment of constant inputs.
Writes settled.json: list of records for segments with len>=MINLEN, with per-design final-edge outputs."""
import json, sys, os
EQ = '/tmp/claude-0/-home-user-Veri-Sure/12bb865e-7a51-5506-b55a-e5ac7cf72a4a/scratchpad/eq'
OUT = os.path.dirname(os.path.abspath(__file__))
RUNS = ['luna12', 'luna13', 'luna14', 'luna15']
DESIGNS = []
for r in RUNS:
    for k in ['gen1', 'gen2', 'gen3', 'r0', 'final']:
        if r == 'luna14' and k == 'r0':
            continue
        DESIGNS.append(f'{r}.{k}')
MINLEN = 12

def fclass(x):
    s = x >> 63; e = (x >> 52) & 0x7ff; f = x & ((1 << 52) - 1)
    if e == 0x7ff:
        if f == 0: return '-inf' if s else '+inf'
        return 'qnan' if (f >> 51) & 1 else 'snan'
    if e == 0 and f == 0: return 'zero'
    if e == 0: return 'denorm'
    return 'num'

def scen(row, inputs):
    i = dict(zip(inputs, row))
    op = {0: 'add', 1: 'sub', 2: 'mul', 3: 'div'}.get(i['fpu_op'], 'op%d' % i['fpu_op'])
    return {
        'rst': i['rst'], 'en': i['enable'], 'op': op, 'a': fclass(i['opa']), 'b': fclass(i['opb']),
        'inz': int((i['in_except'] & ((1 << 63) - 1)) == 0), 'ins': i['in_except'] >> 63,
        'ovf': int(i['exponent_in'] > 2046), 'man': i['mantissa_in'], 'rm': i['rmode'],
    }

def main():
    stims = {r: json.load(open(f'{EQ}/stim/{r}/fpu_exceptions.json')) for r in RUNS}
    gold = json.load(open(f'{EQ}/out/fpu_exceptions/golden.json'))
    segs = []  # (run, tp, seg_start, seg_end, scen)
    for r in RUNS:
        st = stims[r]
        for tp, v in st['tps'].items():
            rows = v['rows']; s = 0
            for k in range(1, len(rows) + 1):
                if k == len(rows) or rows[k] != rows[s]:
                    if k - s >= MINLEN:
                        segs.append({'run': r, 'tp': tp, 's': s, 'e': k - 1,
                                     'sc': scen(rows[s], st['inputs']),
                                     'row': rows[s],
                                     'ref': v['ref'][k - 1],
                                     'g': gold[r][tp][k - 1]})
                    s = k
    for d in DESIGNS:
        tr = json.load(open(f'{EQ}/out/fpu_exceptions/{d}.json'))
        for sg in segs:
            sg[d] = tr[sg['run']][sg['tp']][sg['e']]
        del tr
    json.dump({'outputs': stims['luna12']['outputs'], 'inputs': stims['luna12']['inputs'],
               'designs': DESIGNS, 'segs': segs}, open(f'{OUT}/settled.json', 'w'))
    print(len(segs), 'segments')

main()
