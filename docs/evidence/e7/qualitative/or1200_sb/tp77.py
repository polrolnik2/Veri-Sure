from common import *
s=stim('luna12'); I=s['inputs']
r0=trace('luna12.r0')['luna12']; fi=trace('luna12.final')['luna12']
for tp in ['TP-0077']:
    tt=s['tps'][tp]
    print(tp, 'notes', tt['notes'][:2])
    for e,row in enumerate(tt['rows'][:12]):
        i=dict(zip(I,row))
        f=lambda v: ' '.join(v[1:3]+v[4:6]+v[7:8])
        print(e, f"rst={i['rst']} cyc={i['dcsb_cyc_i']} we={i['dcsb_we_i']} adr={i['dcsb_adr_i']:x} ack_i={i['sbbiu_ack_i']}", '| r0', f(r0[tp][e]), '| final', f(fi[tp][e]), '| ref', ' '.join(format(x,'x') for x in [tt['ref'][e][1],tt['ref'][e][2],tt['ref'][e][4],tt['ref'][e][5],tt['ref'][e][7]]))
