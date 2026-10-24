"""Run a run's SHIPPED checks over traces produced by the flag model (probes from model state)."""
import sys, json
sys.path.insert(0, '/home/user/Veri-Sure')
from specflow.refmodel.oracles import RequirementOracle, decide, transactional_view, _worst
from model import *
INS = ['rst', 'dc_en', 'dcqmem_cycstb_i', 'dcqmem_ci_i', 'dcqmem_we_i', 'dcqmem_sel_i', 'tagcomp_miss',
       'biudata_valid', 'biudata_error', 'start_addr']
_OR = {}
def oracles(run):
    if run not in _OR:
        s = json.loads((EQ / 'corpora' / run / 'or1200_dc_fsm' / 'shipped.json').read_text())
        _OR[run] = [RequirementOracle(req_uid=o['req_uid'], tp_uids=o['tp_uids'], clause=o['clause'], source=o['source'])
                    for o in s['oracles']]
    return _OR[run]

def traces(flags, tps, fresh=True):
    out = {}
    m = M(flags)
    for tp, rows in tps.items():
        if fresh:
            m = M(flags); m.reset()
        tr = []
        for e, r in enumerate(rows):
            o = m.outputs(r)
            st = m.state
            outs = dict(zip(OUTS, o))
            outs.update(idle=int(st == IDLE), cload=int(st == CLOAD), cstore=int(st == CSTORE),
                        lrefill3=int(st == LR3), srefill4=int(st == SR4), hitmiss_eval=int(m.he),
                        store=int(m.store), load=int(m.load), cache_inhibit=int(m.ci_r),
                        cnt_nonzero=int(m.cnt != 0), first_store_hit_ack=m.last_fsha)
            ins = dict(zip(INS, r)); ins['clk'] = 0
            tr.append({'edge': e, 'index': e, 'held': 1, 'inputs': ins, 'outputs': outs})
            m.advance(r)
        out[tp] = tr
    return out

def run_checks(flags, run, transactional=True, per_tp=False):
    tps, _ = stim(run)
    T = traces(flags, tps)
    res = {}
    for o in oracles(run):
        rs = []
        for tp, tr in T.items():
            rows = transactional_view(tr) if transactional else tr
            r = decide(o, rows)
            rs.append((tp, r))
        w = _worst(o.req_uid, [r for _, r in rs])
        verdict = 'broken' if w.broken else ('fail' if w.ok is False else ('pass' if w.ok else 'abstain'))
        res[o.req_uid] = (verdict, [tp for tp, r in rs if r.ok is False and not r.broken] if per_tp else None, w.detail)
    return res

if __name__ == '__main__':
    run = sys.argv[1]; flags = sys.argv[2].split(',') if len(sys.argv) > 2 and sys.argv[2] else []
    res = run_checks(flags, run, per_tp=True)
    from collections import Counter
    print(Counter(v[0] for v in res.values()))
    for k, v in res.items():
        if v[0] in ('fail', 'broken'):
            print(k, v[0], v[1][:5], v[2][:150])
