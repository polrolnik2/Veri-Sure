import json, collections
EQ='/tmp/claude-0/-home-user-Veri-Sure/12bb865e-7a51-5506-b55a-e5ac7cf72a4a/scratchpad/eq'
Q='/tmp/claude-0/-home-user-Veri-Sure/12bb865e-7a51-5506-b55a-e5ac7cf72a4a/scratchpad/qual/i2c_master_bit_ctrl'
M='i2c_master_bit_ctrl'
RT=json.load(open(f'{Q}/reset_tps.json'))
ports=['cmd_ack','busy','al','dout','scl_o','scl_oen','sda_o','sda_oen']
gB=json.load(open(f'{Q}/work/gB.json'))
def eqg(a,g): return all('x' in y or x==y for x,y in zip(a,g))
def eqr(a,r): return all(x==format(int(y),'x') for x,y in zip(a,r))
out={}
for run in ['luna12','luna13','luna14','luna15']:
    st=json.load(open(f'{EQ}/stim/{run}/{M}.json'))
    r0=json.load(open(f'{EQ}/out/{M}/{run}.r0.json'))[run]
    fi=json.load(open(f'{EQ}/out/{M}/{run}.final.json'))[run]
    c=collections.Counter(); cp=collections.Counter(); agg=collections.Counter()
    for tp in RT[run]:
        g=gB[run][tp]; ref=st['tps'][tp]['ref']; a=r0[tp]; b=fi[tp]
        for i in range(1,min(len(g),len(ref))):
            agg['n']+=1
            agg['r0_ref']+=eqr(a[i],ref[i]); agg['fi_ref']+=eqr(b[i],ref[i])
            agg['r0_g']+=eqg(a[i],g[i]); agg['fi_g']+=eqg(b[i],g[i])
            agg['ref_g']+=eqg([format(int(v),'x') for v in ref[i]],g[i])
            if a[i]==b[i]: continue
            fg=eqg(b[i],g[i]); fr=eqr(b[i],ref[i]); rg=eqg(a[i],g[i]); rr=eqr(a[i],ref[i])
            c[('final:'+('G' if fg else '')+('R' if fr else '') or 'final:-', 'r0:'+(('G' if rg else '')+('R' if rr else '') or '-'))]+=1
            for k,p in enumerate(ports):
                if a[i][k]!=b[i][k]:
                    gv=g[i][k]; rv=format(int(ref[i][k]),'x')
                    cp[(p, 'fin=G' if b[i][k]==gv else ('fin=R' if b[i][k]==rv else 'fin=-'), 'g==ref' if gv==rv else 'g!=ref')]+=1
    n=sum(c.values())
    print(f"== {run}: edges={agg['n']} r0->final differ at {n} edges ({n/agg['n']:.3f}); ref agreement r0={agg['r0_ref']/agg['n']:.3f} final={agg['fi_ref']/agg['n']:.3f}; gB agreement r0={agg['r0_g']/agg['n']:.3f} final={agg['fi_g']/agg['n']:.3f}; ref-vs-gB={agg['ref_g']/agg['n']:.3f}")
    for k,v in c.most_common(): print('   ',k, v, f'{v/n:.3f}')
    for k,v in sorted(cp.items(), key=lambda x:-x[1])[:10]: print('      port',k,v)
    out[run]={'agg':dict(agg),'cls':{str(k):v for k,v in c.items()}}
json.dump(out,open(f'{Q}/h2.json','w'),indent=1)
