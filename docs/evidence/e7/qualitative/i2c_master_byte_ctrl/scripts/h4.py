"""r0 -> final, reset-prefixed traces, all three stimulus runs: per port, edges fixed (r0 wrong, final right vs golden) and broken."""
import json, sys, collections
Q='/tmp/claude-0/-home-user-Veri-Sure/12bb865e-7a51-5506-b55a-e5ac7cf72a4a/scratchpad/qual/i2c_master_byte_ctrl'
OUTS=['cmd_ack','ack_out','dout','i2c_busy','i2c_al','scl_o','scl_oen','sda_o','sda_oen']
G=json.load(open(f'{Q}/hyb/traces_rst/golden.id.json'))
for run,a,b in [('luna12','own','own'),('luna14','own','own'),('luna12','swap','swap'),('luna14','bin','bin')]:
    A=json.load(open(f'{Q}/hyb/traces_rst/{run}.r0.{a}.json')); B=json.load(open(f'{Q}/hyb/traces_rst/{run}.final.{b}.json'))
    fx=collections.Counter(); br=collections.Counter(); n=0; ex=[]
    for r in G:
        for tp,g in G[r].items():
            for e,(gg,aa,bb) in enumerate(zip(g,A[r][tp],B[r][tp])):
                n+=1
                for i,p in enumerate(OUTS):
                    if aa[i]!=gg[i] and bb[i]==gg[i]: fx[p]+=1
                    elif aa[i]==gg[i] and bb[i]!=gg[i]:
                        br[p]+=1
                        if len(ex)<3 and p in('dout','ack_out') : ex.append((r,tp,e,p,'g',gg[i],'r0',aa[i],'final',bb[i]))
    print(run, a, 'edges',n, 'fixed', {p:round(fx[p]/n,3) for p in OUTS if fx[p]}, 'broken', {p:round(br[p]/n,3) for p in OUTS if br[p]}, 'ex', ex)
