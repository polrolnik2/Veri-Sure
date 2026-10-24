"""Per design (reset-prefixed traces): edge agreement, tp-exact, cell mismatch per port; and first-divergence port per testpoint."""
import json, sys, collections
Q='/tmp/claude-0/-home-user-Veri-Sure/12bb865e-7a51-5506-b55a-e5ac7cf72a4a/scratchpad/qual/i2c_master_byte_ctrl'
OUTS=['cmd_ack','ack_out','dout','i2c_busy','i2c_al','scl_o','scl_oen','sda_o','sda_oen']
G=json.load(open(f'{Q}/hyb/traces_rst/golden.id.json'))
res={}
for f in sys.argv[1:]:
    X=json.load(open(f'{Q}/hyb/traces_rst/{f}.json'))
    n=e=0; t=nt=0; mm=[0]*9; fd=collections.Counter(); ex={}
    for r in G:
        for tp,g in G[r].items():
            x=X[r][tp]; nt+=1; first=None
            for k,(a,b) in enumerate(zip(g,x)):
                n+=1
                if a==b: e+=1
                elif first is None:
                    first=k; ps=tuple(p for i,p in enumerate(OUTS) if a[i]!=b[i])
                    fd[ps]+=1
                    ex.setdefault(ps,(r,tp,k,{p:(a[i],b[i]) for i,p in enumerate(OUTS) if a[i]!=b[i]}))
                for i in range(9): mm[i]+= a[i]!=b[i]
            t+= first is None
    res[f]={'n':n,'edge':e/n,'tp':t/nt,'mm':mm,'fd':{'|'.join(k):v for k,v in fd.items()}}
    print('%-22s edge=%.3f tp=%.3f cellmm=%.3f'%(f,e/n,t/nt,sum(mm)/9/n), ' '.join('%s=%.2f'%(p[:7],mm[i]/n) for i,p in enumerate(OUTS) if p not in('scl_o','sda_o')))
    print('    first-divergence:', [(k,v,ex[k]) for k,v in fd.most_common(3)])
json.dump(res,open(f'{Q}/firstdiv_{sys.argv[1].split(".")[-1]}.json','w'))
