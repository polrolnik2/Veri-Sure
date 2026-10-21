"""Per-port settle latency after an input change (segment start), per design vs golden.
Latency = first edge offset k from segment start after which the port stays at its settled value.
Only segments with enable=1, len>=12, and previous row enable=1 & rst=0 & output actually changes in golden or design."""
import json, collections
EQ = '/tmp/claude-0/-home-user-Veri-Sure/12bb865e-7a51-5506-b55a-e5ac7cf72a4a/scratchpad/eq'
RUNS = ['luna12', 'luna13', 'luna14', 'luna15']
DES = ['golden'] + [f'{r}.{k}' for r in RUNS for k in ['gen1', 'gen2', 'gen3', 'r0', 'final'] if not (r == 'luna14' and k == 'r0')]
stims = {r: json.load(open(f'{EQ}/stim/{r}/fpu_exceptions.json')) for r in RUNS}
O = stims['luna12']['outputs']
segs = []
for r in RUNS:
    for tp, v in stims[r]['tps'].items():
        rows = v['rows']; s = 0
        for k in range(1, len(rows) + 1):
            if k == len(rows) or rows[k] != rows[s]:
                if k - s >= 12 and s > 0 and rows[s][2] == 1 and rows[s][1] == 0 and rows[s - 1][2] == 1 and rows[s - 1][1] == 0:
                    segs.append((r, tp, s, k - 1))
                s = k
res = {}
glitch = collections.Counter()
for d in DES:
    tr = json.load(open(f'{EQ}/out/fpu_exceptions/{d}.json'))
    lat = {p: collections.Counter() for p in O}
    for (r, tp, s, e) in segs:
        t = tr[r][tp]
        for pi, p in enumerate(O):
            fin = t[e][pi]
            if t[s - 1][pi] == fin:
                # check for a transient glitch: value differs mid-segment but returns
                if any(t[k][pi] != fin for k in range(s, e)):
                    lat[p]['glitch'] += 1
                continue
            k = e
            while k > s and t[k - 1][pi] == fin:
                k -= 1
            # count distinct intermediate values between s-1 and k (multi-step settle)
            inter = len(set(t[j][pi] for j in range(s, k)) - {t[s - 1][pi]})
            lat[p][k - s] += 1
            if inter:
                lat[p]['multistep'] += 1
    res[d] = {p: dict(lat[p]) for p in O}
    del tr
json.dump(res, open('latency.json', 'w'))
for d in DES:
    row = []
    for p in O:
        c = {k: v for k, v in res[d][p].items() if isinstance(k, int)}
        tot = sum(c.values())
        top = sorted(c.items(), key=lambda kv: -kv[1])[:3]
        row.append(f"{p}:" + ','.join(f'{k}x{v}' for k, v in top) + (f" ms{res[d][p].get('multistep',0)} gl{res[d][p].get('glitch',0)}"))
    print(d, ' | '.join(row))
