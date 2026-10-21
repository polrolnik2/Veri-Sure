"""At edges where r0 and final differ (own run's stimulus, reset-prefixed traces), does final agree with golden, ref, both, neither?"""
import json, collections
EQ='/tmp/claude-0/-home-user-Veri-Sure/12bb865e-7a51-5506-b55a-e5ac7cf72a4a/scratchpad/eq'
Q='/tmp/claude-0/-home-user-Veri-Sure/12bb865e-7a51-5506-b55a-e5ac7cf72a4a/scratchpad/qual/i2c_master_byte_ctrl'
OUTS=['cmd_ack','ack_out','dout','i2c_busy','i2c_al','scl_o','scl_oen','sda_o','sda_oen']
def val(s):
    try: return int(s,16)
    except ValueError: return s
res={}
for run in ['luna12','luna14']:
    S=json.load(open(f'{EQ}/stim/{run}/i2c_master_byte_ctrl.json'))
    G=json.load(open(f'{Q}/hyb/traces_rst/golden.id.json'))[run]
    R0=json.load(open(f'{Q}/hyb/traces_rst/{run}.r0.own.json'))[run]
    F=json.load(open(f'{Q}/hyb/traces_rst/{run}.final.own.json'))[run]
    c=collections.defaultdict(collections.Counter); refagree=collections.defaultdict(lambda:[0,0,0])
    for tp in G:
        ref=S['tps'][tp]['ref']
        for e,(g,a,b) in enumerate(zip(G[tp],R0[tp],F[tp])):
            rf=ref[e] if e<len(ref) else None
            for i,p in enumerate(OUTS):
                gv,av,bv=val(g[i]),val(a[i]),val(b[i]); rv=rf[i] if rf is not None else None
                if rv is not None:
                    refagree[p][0]+=1; refagree[p][1]+= (av==rv); refagree[p][2]+=(bv==rv)
                if av==bv: continue
                fg=bv==gv; fr=bv==rv; rg=av==gv; rr=av==rv
                c[p]['final:'+('both' if fg and fr else 'golden' if fg else 'ref' if fr else 'neither')]+=1
                c[p]['r0:'+('both' if rg and rr else 'golden' if rg else 'ref' if rr else 'neither')]+=1
                c[p]['n']+=1
    print('=====',run)
    for p in OUTS:
        if c[p]['n']: print(' %-8s n=%6d '%(p,c[p]['n']), {k:v for k,v in sorted(c[p].items()) if k!='n'})
    print(' ref agreement r0 -> final per port:', {p:'%.3f->%.3f'%(v[1]/v[0],v[2]/v[0]) for p,v in refagree.items()})
    tot=collections.Counter()
    for p in OUTS:
        for k,v in c[p].items(): tot[k]+=v
    print(' TOTAL', dict(tot))
