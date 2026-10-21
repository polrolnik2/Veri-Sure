import json
from checks import *
fit = json.load(open('fit.json')); fr = json.load(open('fitref.json'))
out = {}
import sys
for run in sys.argv[1:]:
    ref = run_checks(fr[run]['flags'], run)
    artifacts = sorted(k for k, v in ref.items() if v[0] == 'fail')
    print(run, 'ref-model fails (harness artifacts):', artifacts, flush=True)
    out[run] = {'artifacts': artifacts}
    for k in ['gen1','gen2','gen3','r0','final']:
        d = f'{run}.{k}'; F = fit[d]['flags']
        base = run_checks(F, run)
        bf = {u for u, v in base.items() if v[0] == 'fail'} - set(artifacts)
        row = {'fails': sorted(bf), 'visible': {}, 'rewarded': {}}
        for f in F:
            r = run_checks([x for x in F if x != f], run)
            rf = {u for u, v in r.items() if v[0] == 'fail'} - set(artifacts)
            if bf - rf: row['visible'][f] = sorted(bf - rf)
            if rf - bf: row['rewarded'][f] = sorted(rf - bf)
        out[run][d] = row
        print(d, row, flush=True)
json.dump(out, open('vis2_'+'_'.join(sys.argv[1:])+'.json', 'w'), indent=1)
