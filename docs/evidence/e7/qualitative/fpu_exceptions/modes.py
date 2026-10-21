"""Assign every settled (design, segment, port) mismatch vs golden to an error mode; count per design/arm."""
import json, collections, sys
D = json.load(open('settled.json'))
O = D['outputs']
segs = [s for s in D['segs'] if s['sc']['rst'] == 0]
import os
if os.environ.get('RS'):
    from rs import keep
    segs = [s for s in segs if keep(s['run'], s['tp'], s['s'])]
M52 = (1 << 52) - 1
def h(v): return int(v, 16) if all(c in '0123456789abcdefABCDEF' for c in v) else 'X'

def gold_sig(s):
    i = dict(zip(D['inputs'], s['row']))
    a, b, ie = i['opa'], i['opb'], i['in_except']
    def cls(x):
        e = (x >> 52) & 0x7ff; f = x & M52
        return dict(z=(x & ((1 << 63) - 1)) == 0, inf=e == 0x7ff and f == 0,
                    nan=e == 0x7ff and f != 0, snan=e == 0x7ff and f != 0 and not (f >> 51) & 1)
    A, B = cls(a), cls(b)
    op = i['fpu_op']; div = op == 3; mul = op == 2
    inz = (ie & ((1 << 63) - 1)) == 0
    nan_in = A['nan'] or B['nan']; snan_in = A['snan'] or B['snan']
    div_by_inf = div and not A['inf'] and B['inf']
    mul_uf = mul and not A['z'] and not B['z'] and inz
    div_uf = div and not A['z'] and inz
    uf = div_by_inf or mul_uf or div_uf
    mul0inf = mul and ((A['inf'] and B['z']) or (A['z'] and B['inf']))
    addsub_inv = (op == 0 and A['inf'] and B['inf'] and (a >> 63) != (b >> 63)) or \
                 (op == 1 and A['inf'] and B['inf'] and (a >> 63) == (b >> 63))
    inv = snan_in or addsub_inv or mul0inf or (div and A['z'] and B['z']) or (div and A['inf'] and B['inf'])
    return dict(A=A, B=B, op=op, inz=inz, nan_in=nan_in, snan_in=snan_in, div_by_inf=div_by_inf,
                mul_uf=mul_uf, div_uf=div_uf, uf=uf, inv=inv, gen_nan=inv and not snan_in,
                i=i)

def mode(s, g, port, gv, dv):
    sc = s['sc']
    if sc['en'] == 0:
        return 'L0 enable-low freeze (pipeline depth)'
    if dv == 'X':
        return 'X output'
    if port == 'out':
        if g['gen_nan'] and gv != 'X' and ((gv >> 50) & 3) == 1 and ((dv >> 51) & 1) == 1 and ((dv >> 52) & 0x7ff) == 0x7ff:
            return 'M1 invalid-op NaN payload (golden 0x7ff4.., design 0x7ff8..)'
        if g['div_by_inf'] and not g['A']['z'] and not g['inz'] and (gv & ((1 << 63) - 1)) == 0 and dv == s['row'][D['inputs'].index('in_except')]:
            return 'M4 x/inf: out not zeroed when candidate nonzero'
        if g['div_by_inf'] and g['A']['z'] and (gv & ((1 << 63) - 1)) == 0:
            return 'M3 0/inf not underflow'
        return 'out other'
    if port in ('underflow', 'inexact', 'exception', 'ex_enable') and gv == 1 and dv == 0:
        if g['div_by_inf'] and g['A']['z']:
            return 'M3 0/inf not underflow'
        if g['div_by_inf'] and not g['inz'] and not g['nan_in']:
            return 'M4b x/inf underflow missing (candidate nonzero)'
        if g['uf'] and not g['div_by_inf']:
            A, B = g['A'], g['B']
            if g['nan_in']:
                return 'M2c underflow: NaN operand + zero candidate'
            if A['inf'] or B['inf']:
                return 'M2b underflow: inf operand + zero candidate'
            if g['op'] == 3 and B['z']:
                return 'M2a underflow: x/0 + zero candidate'
            return 'M2d underflow other'
        if g['uf'] and g['div_by_inf'] and (g['nan_in'] or g['A']['inf']):
            return 'M2c underflow: NaN operand + zero candidate'
    if port == 'ex_enable' and gv == 1 and dv == 0 and g['nan_in'] and not g['snan_in']:
        return 'M5 ex_enable not set for QNaN input'
    return f'{port} other'

def main():
    cnt = collections.defaultdict(collections.Counter)  # mode -> design -> n
    seg_mode = collections.defaultdict(lambda: collections.defaultdict(set))  # mode -> design -> set(seg idx)
    ex = {}
    portmode = collections.defaultdict(collections.Counter)
    for k, s in enumerate(segs):
        g = gold_sig(s)
        gvals = [h(x) for x in s['g']]
        for d in D['designs']:
            for p, gv, dv in zip(O, gvals, [h(x) for x in s[d]]):
                if gv != dv:
                    m = mode(s, g, p, gv, dv)
                    cnt[m][d] += 1
                    seg_mode[m][d].add(k)
                    portmode[m][p] += 1
                    ex.setdefault(m, (d, s['run'], s['tp'], 'edge', s['e'], p, s['g'][O.index(p)], s[d][O.index(p)]))
    gen = [d for d in D['designs'] if not d.endswith('final')]
    rep = [d for d in D['designs'] if d.endswith('final')]
    n = len(segs)
    print('segments', n)
    for m in sorted(cnt, key=lambda m: -sum(len(v) for v in seg_mode[m].values())):
        sg = [len(seg_mode[m].get(d, ())) for d in gen]
        sr = [len(seg_mode[m].get(d, ())) for d in rep]
        print(f'{m:55s} segs/design gen mean {sum(sg)/len(gen):6.1f} (in {sum(1 for x in sg if x)}/{len(gen)})  rep mean {sum(sr)/len(rep):6.1f} (in {sum(1 for x in sr if x)}/{len(rep)})  ports {dict(portmode[m])}')
        print('      per design:', {d: len(seg_mode[m][d]) for d in D['designs'] if seg_mode[m].get(d)})
        print('      example:', ex[m])
    json.dump({m: {d: sorted(v) for d, v in dd.items()} for m, dd in seg_mode.items()}, open('modes_rs.json' if os.environ.get('RS') else 'modes.json', 'w'))

main()
