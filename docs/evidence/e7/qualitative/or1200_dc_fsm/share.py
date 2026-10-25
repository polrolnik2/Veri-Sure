import json
from model import *
STIM = {r: stim(r)[0] for r in ['luna12','luna13','luna14']}
G = {r: run_model_fresh([], STIM[r]) for r in STIM}
def mism(flags):
    E=set(); P=[0]*10
    for r in STIM:
        m = run_model_fresh(flags, STIM[r])
        for tp in m:
            for e,(a,b) in enumerate(zip(m[tp], G[r][tp])):
                d=[k for k in range(10) if a[k]!=b[k]]
                if d: E.add((r,tp,e)); 
                for k in d: P[k]+=1
    return E,P
for f in ['CI_LIVE_WE','CI_CYC_GATE','CI_HIT_R']:
    E,P=mism([f]); print('single',f,len(E),{OUTS[k]:P[k] for k in range(10) if P[k]})
fit=json.load(open('fit.json'))
groups={'SR':['SR'],'CI':['CI_COMB','CI_REFILL'],'ADDR':['NO_ADDR_UP'],'BRLOAD':['BR_LOAD'],'HITEVAL':['EXIT_EVAL','LATE_REFILL','LATE_IDLE','ACK_EVAL'],
        'ACKQ':['ACK_CYC','ACK_ABORT'],'ERR':['ERR_REFILL'],'DWE':['DWE_BR'],'BRCI':['BR_CI'],'CI_LIVE_WE':['CI_LIVE_WE']}
out={}
for d,v in fit.items():
    F=v['flags']; E,_=mism(F); row={'total':len(E)}
    for g,fl in groups.items():
        if any(x in F for x in fl):
            E2,_=mism([x for x in F if x not in fl]); row[g]=len(E)-len(E2)
    # CI split: replace CI_COMB by its subparts and drop one at a time
    if 'CI_COMB' in F:
        base=[x for x in F if x!='CI_COMB']+['CI_LIVE_WE','CI_CYC_GATE','CI_HIT_R']
        for sub in ['CI_LIVE_WE','CI_CYC_GATE','CI_HIT_R']:
            E2,_=mism([x for x in base if x!=sub]); row['ci:'+sub]=len(E)-len(E2)
    out[d]=row; print(d,row,flush=True)
json.dump(out,open('share_fresh.json','w'),indent=1)
