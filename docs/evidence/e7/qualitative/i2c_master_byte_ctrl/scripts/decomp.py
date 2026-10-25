import json, sys
EQ='/tmp/claude-0/-home-user-Veri-Sure/12bb865e-7a51-5506-b55a-e5ac7cf72a4a/scratchpad/eq'
Q='/tmp/claude-0/-home-user-Veri-Sure/12bb865e-7a51-5506-b55a-e5ac7cf72a4a/scratchpad/qual/i2c_master_byte_ctrl'
OUTS=['cmd_ack','ack_out','dout','i2c_busy','i2c_al','scl_o','scl_oen','sda_o','sda_oen']
G=json.load(open(f'{EQ}/out/i2c_master_byte_ctrl/golden.json'))
fix={'luna14.r0':'bin','luna14.final':'bin','luna13.gen1':'tx','luna13.gen2':'tx','luna13.final':'tx'}
D=['luna12.gen1','luna12.gen2','luna12.gen3','luna12.r0','luna12.final','luna13.gen1','luna13.gen2','luna13.gen3','luna13.final','luna14.gen1','luna14.gen2','luna14.gen3','luna14.r0','luna14.final']
def mm(X):
    c=[0]*9; n=0
    for r in G:
        for tp,g in G[r].items():
            for a,b in zip(g,X[r][tp]):
                n+=1
                for i in range(9):
                    if a[i]!=b[i]: c[i]+=1
    return c,n
out={}
for d in D:
    o,n=mm(json.load(open(f'{EQ}/out/i2c_master_byte_ctrl/{d}.json')))
    m=fix.get(d,'swap')
    f,_=mm(json.load(open(f'{Q}/hyb/traces/{d}.{m}.json')))
    try: i,_=mm(json.load(open(f'{Q}/hyb/traces/{d}.id.json')))
    except FileNotFoundError: i=None
    out[d]={'n':n,'orig':o,'fix':f,'id':i}
    so,sf=sum(o),sum(f)
    print('%-13s cellmm orig=%.3f fix=%.3f id=%s  removed by golden child+enc=%.0f%%  ' % (d, so/9/n, sf/9/n, ('%.3f'%(sum(i)/9/n)) if i else '  -  ', 100*(so-sf)/so),
          ' '.join('%s:%.2f>%.2f'%(p[:6],o[k]/n,f[k]/n) for k,p in enumerate(OUTS) if p not in('scl_o','sda_o','i2c_al')))
json.dump(out,open(f'{Q}/decomp.json','w'))
# pooled by port share of original disagreement
tot=[sum(out[d]['orig'][k] for d in D) for k in range(9)]
print('share of orig cell disagreement by port:', {p:round(tot[k]/sum(tot),3) for k,p in enumerate(OUTS)})
totf=[sum(out[d]['fix'][k] for d in D) for k in range(9)]
print('share of residual (fix) disagreement by port:', {p:round(totf[k]/sum(totf),3) for k,p in enumerate(OUTS)})
print('pooled residual/orig:', sum(totf)/sum(tot))
