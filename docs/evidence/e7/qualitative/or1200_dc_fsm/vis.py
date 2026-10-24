import json, sys
from checks import *
from model import FLAGS
runs = ['luna12','luna13','luna14']
fit = json.load(open('fit.json'))
out = {}
for run in runs:
    base = run_checks([], run)
    out[run] = {'golden': {k: v[0] for k, v in base.items()}}
    for f in FLAGS:
        r = run_checks([f], run)
        out[run]['+'+f] = {k: v[0] for k, v in r.items()}
        nf = [k for k in r if r[k][0]=='fail' and base[k][0]!='fail']
        fx = [k for k in r if base[k][0]=='fail' and r[k][0]!='fail']
        print(run, f, 'newfail', nf, 'fixed', fx, flush=True)
    for d, v in fit.items():
        r = run_checks(v['flags'], run)
        out[run][d] = {k: x[0] for k, x in r.items()}
        print(run, d, 'fails', [k for k in r if r[k][0]=='fail'], flush=True)
json.dump(out, open('vis.json','w'), indent=0)
