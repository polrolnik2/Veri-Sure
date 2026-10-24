import json
Q='/tmp/claude-0/-home-user-Veri-Sure/12bb865e-7a51-5506-b55a-e5ac7cf72a4a/scratchpad/qual/i2c_master_byte_ctrl'
OUTS=['cmd_ack','ack_out','dout','i2c_busy','i2c_al','scl_o','scl_oen','sda_o','sda_oen']
G=json.load(open(f'{Q}/hyb/traces_rst/golden.id.json'))
fix={'luna14.r0':'bin','luna14.final':'bin','luna13.gen1':'tx','luna13.gen2':'tx','luna13.final':'tx'}
D=['luna12.gen1','luna12.gen2','luna12.gen3','luna12.r0','luna12.final','luna13.gen1','luna13.gen2','luna13.gen3','luna13.final','luna14.gen1','luna14.gen2','luna14.gen3','luna14.r0','luna14.final']
def st(X):
    c=[0]*9; n=e=0
    for r in G:
        for tp,g in G[r].items():
            for a,b in zip(g,X[r][tp]):
                n+=1; e+= a==b
                for i in range(9): c[i]+= a[i]!=b[i]
    return c,n,e
out={}
for d in D:
    o,n,eo=st(json.load(open(f'{Q}/hyb/traces_rst/{d}.own.json')))
    f,_,ef=st(json.load(open(f'{Q}/hyb/traces_rst/{d}.{fix.get(d,"swap")}.json')))
    out[d]=(o,f,n)
    print('%-13s edge own=%.3f fix=%.3f  cellmm own=%.3f fix=%.3f removed=%.0f%%'%(d,eo/n,ef/n,sum(o)/9/n,sum(f)/9/n,100*(sum(o)-sum(f))/sum(o)))
for grp,ds in [('all',D),('held',[d for d in D if d not in('luna12.r0','luna14.gen1','luna14.r0','luna14.final')]),('pulse',['luna12.r0','luna14.gen1','luna14.r0','luna14.final'])]:
    O=[sum(out[d][0][i] for d in ds) for i in range(9)]; F=[sum(out[d][1][i] for d in ds) for i in range(9)]
    print(grp,'removed %.1f%%'%(100*(sum(O)-sum(F))/sum(O)),'own share by port',{p:round(O[i]/sum(O),3) for i,p in enumerate(OUTS)},'residual share by port',{p:round(F[i]/sum(F),3) for i,p in enumerate(OUTS)})
mut=['ackw','wshift8','nold_start','txd_comb','pulse','comb_ldshift']
for m in mut:
    c,n,e=st(json.load(open(f'{Q}/hyb/traces_rst/mut_{m}.id.json')))
    print('mut %-13s edge=%.3f cellmm=%.4f cells=%d'%(m,e/n,sum(c)/9/n,sum(c)), {p:round(c[i]/n,3) for i,p in enumerate(OUTS) if c[i]})
tot_own=sum(sum(out[d][0]) for d in D); print('total own cells', tot_own, 'n per design', out[D[0]][2])
