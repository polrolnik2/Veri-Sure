import json, sys
from model import *
fit = json.load(open('fit.json'))
STN = ['rst','en','cyc','ci','we','sel','miss','val','err','addr']
SN = {0:'IDLE',1:'CLOAD',2:'LREFILL3',3:'CSTORE',4:'SREFILL4'}
def example(design, flag, run, k=1, ctx=3):
    F = fit[design]['flags']; tps,_ = stim(run)
    D = load_trace(design)[run]; G = load_trace('golden')[run]
    Fm = run_model([x for x in F if x != flag], tps)
    # golden state trace
    m = M([]); states = {}
    for tp, rows in tps.items():
        s=[]
        for r in rows:
            m.outputs(r); s.append((SN.get(m.state) if m.known else '?', m.he if m.known else '?', m.ci_r if m.known else '?')); m.advance(r)
        states[tp]=s
    found=0
    for tp in tps:
        for e,(d,g,fm) in enumerate(zip(D[tp],G[tp],Fm[tp])):
            if None in d or None in g or fm is None: continue
            if d!=g and fm==g:
                ports=[OUTS[j] for j in range(10) if d[j]!=g[j]]
                print(f'## {design} {flag} stim={run} {tp} edge {e} ports {ports}')
                for j in range(max(0,e-ctx), e+1):
                    r=tps[tp][j]
                    print('   e%d gold(state,he,ci_r)=%s in:%s | des:%s gold:%s'%(j, states[tp][j], ' '.join(f'{n}={v:x}' if n=='addr' else f'{n}={v}' for n,v in zip(STN,r)),
                        dict((OUTS[q],hex(D[tp][j][q]) if q in (0,9) else D[tp][j][q]) for q in range(10) if D[tp][j][q]!=G[tp][j][q]) ,
                        dict((OUTS[q],hex(G[tp][j][q]) if q in (0,9) else G[tp][j][q]) for q in range(10) if D[tp][j][q]!=G[tp][j][q])))
                found+=1
                if found>=k: return
example(sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4]) if len(sys.argv)>4 else 1)
