from common import *
def first_diff(d, sr, want_port=None, need_reset=True, k=2):
    s=stim(sr); I=s['inputs']; ri=I.index('rst'); t=trace(d)[sr]; found=0
    for tp,tt in sorted(s['tps'].items()):
        if need_reset and tt['rows'][0][ri]!=1: continue
        for e,row in enumerate(tt['rows']):
            v=[toint(x) for x in t[tp][e]]; g=passthru(I,row)
            if None in v or row[ri]==1 or (need_reset and e<2): continue
            ps=[OUTS[j] for j in range(10) if v[j]!=g[j]]
            if ps and (want_port is None or want_port in ps):
                i=dict(zip(I,row))
                print(d, sr, tp, 'edge', e, 'inputs: cyc/stb/we', i['dcsb_cyc_i'],i['dcsb_stb_i'],i['dcsb_we_i'], 'adr_i %x'%i['dcsb_adr_i'], 'ack_i',i['sbbiu_ack_i'],'err_i',i['sbbiu_err_i'])
                for p in ps: j=OUTS.index(p); print('    ',p,'design=%x golden=%x ref=%x'%(v[j],g[j],tt['ref'][e][j]))
                found+=1
                break
        if found>=k: return
first_diff('luna13.final','luna13',k=1)
first_diff('luna13.final','luna13','dcsb_err_o',k=1)
first_diff('luna12.final','luna12','dcsb_ack_o',k=1)
first_diff('luna14.gen1','luna14','dcsb_ack_o',need_reset=False,k=1)
first_diff('luna12.final','luna12','sbbiu_we_o',k=1)
