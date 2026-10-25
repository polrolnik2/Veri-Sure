"""Open-loop: decompose port-edge mismatches vs golden into functional (segment settled values differ)
vs timing (settled values equal, edge differs) vs unsettled (segment shorter than 12). Own-stimulus too.
Also: closed-loop testpoint classes: exact / dedup-equal (timing only) / functional."""
import json, collections
EQ = '/tmp/claude-0/-home-user-Veri-Sure/12bb865e-7a51-5506-b55a-e5ac7cf72a4a/scratchpad/eq'
RUNS = ['luna12', 'luna13', 'luna14', 'luna15']
DES = [f'{r}.{k}' for r in RUNS for k in ['gen1', 'gen2', 'gen3', 'r0', 'final'] if not (r == 'luna14' and k == 'r0')]
stims = {r: json.load(open(f'{EQ}/stim/{r}/fpu_exceptions.json')) for r in RUNS}
O = stims['luna12']['outputs']
gold = json.load(open(f'{EQ}/out/fpu_exceptions/golden.json'))
# segment id per edge
segof = {}
for r in RUNS:
    for tp, v in stims[r]['tps'].items():
        rows = v['rows']; s = 0; lab = [None] * len(rows)
        for k in range(1, len(rows) + 1):
            if k == len(rows) or rows[k] != rows[s]:
                for j in range(s, k):
                    lab[j] = (k - 1) if k - s >= 12 else None
                s = k
        segof[(r, tp)] = lab
out = {}
for d in DES:
    tr = json.load(open(f'{EQ}/out/fpu_exceptions/{d}.json'))
    c = collections.Counter(); cp = collections.defaultdict(collections.Counter)
    for r in RUNS:
        for tp, gt in gold[r].items():
            dt = tr[r][tp]; lab = segof[(r, tp)]
            for e in range(len(gt)):
                if 'x' in ''.join(gt[e]):
                    continue
                c['edges'] += 1
                anym = False
                for pi, p in enumerate(O):
                    c['pe'] += 1
                    if gt[e][pi] != dt[e][pi]:
                        anym = True
                        L = lab[e]
                        if L is None:
                            k = 'unsettled'
                        elif gt[L][pi] != dt[L][pi]:
                            k = 'functional'
                        else:
                            k = 'timing'
                        c[k] += 1; cp[p][k] += 1
                if anym:
                    c['edge_mm'] += 1
    out[d] = {'c': dict(c), 'port': {p: dict(v) for p, v in cp.items()}}
    del tr
    pe = c['pe']
    print(f"{d:13s} edge-any-mm {100*c['edge_mm']/c['edges']:5.1f}%  port-edge mm {100*(c['functional']+c['timing']+c['unsettled'])/pe:5.2f}%: "
          f"func {100*c['functional']/pe:5.2f} timing {100*c['timing']/pe:5.2f} unsettled {100*c['unsettled']/pe:5.2f}  | "
          + ' '.join(f"{p}:f{100*cp[p]['functional']/(pe/7):.1f}/t{100*cp[p]['timing']/(pe/7):.1f}" for p in O))
json.dump(out, open('decomp.json', 'w'))
