from common import *
from collections import Counter
tot_mis=Counter()
for d in DESIGNS:
    t=trace(d); C=Counter(); n=0; mis=0
    for sr in RUNS:
        s=stim(sr); I=s['inputs']
        prev_ack=0
        for tp,tt in s['tps'].items():
            prev_ack=None
            for e,row in enumerate(tt['rows']):
                i=dict(zip(I,row)); v=[toint(x) for x in t[sr][tp][e]]; o=dict(zip(OUTS,v)); g=passthru(I,row)
                n+=1
                if v!=g:
                    mis+=1
                    if o['dcsb_ack_o']==1 and i['sbbiu_ack_i']==0: C['ack_early']+=1
                    if o['dcsb_ack_o']==0 and i['sbbiu_ack_i']==1: C['ack_supp']+=1
                    if o['dcsb_err_o']==0 and i['sbbiu_err_i']==1: C['err_mask']+=1
                    if v[3:]!=g[3:]: C['biu_req']+=1
                    if i['dcsb_cyc_i']==1 and i['dcsb_we_i']==0 and o['sbbiu_we_o']==1: C['read_stalled_as_write']+=1
                    if i['dcsb_cyc_i']==0 and o['sbbiu_cyc_o']==1: C['spurious_cyc']+=1
                    if prev_ack is not None and o['dcsb_ack_o']==prev_ack and o['dcsb_ack_o']!=i['sbbiu_ack_i'] and v[3:]==g[3:]: C['ack_delayed_1']+=1
                    if None in v: C['x']+=1
                prev_ack=i['sbbiu_ack_i']
    tot_mis[d]=mis
    print(f'{d:14s} mismatch {mis/n:.3f} | '+' '.join(f'{k}={v/n:.3f}' for k,v in sorted(C.items())))
print('total mismatched edges', sum(tot_mis.values()), {k:v for k,v in tot_mis.items() if v})
