import json, collections, pickle
EQ='/tmp/claude-0/-home-user-Veri-Sure/12bb865e-7a51-5506-b55a-e5ac7cf72a4a/scratchpad/eq'
M='i2c_master_bit_ctrl'
OUT='/tmp/claude-0/-home-user-Veri-Sure/12bb865e-7a51-5506-b55a-e5ac7cf72a4a/scratchpad/qual/i2c_master_bit_ctrl'
ports=['cmd_ack','busy','al','dout','scl_o','scl_oen','sda_o','sda_oen']
g=json.load(open(f'{EQ}/out/{M}/golden.json'))
designs=[f'{r}.{k}' for r in ['luna12','luna13','luna14','luna15'] for k in ['gen1','gen2','gen3','r0','final']]
# per design: per (sr,tp): per port list of mismatching edges (first 1, count), and design values
R={}
for d in designs:
    t=json.load(open(f'{EQ}/out/{M}/{d}.json'))
    R[d]={}
    for sr in g:
        for tp,gt in g[sr].items():
            dt=t[sr][tp]
            m={}
            for k,p in enumerate(ports):
                e=[i for i,(a,b) in enumerate(zip(gt,dt)) if 'x' not in a[k] and a[k]!=b[k]]
                if e: m[p]=(e[0],len(e))
            R[d][(sr,tp)]=m
pickle.dump(R,open(f'{OUT}/tpsets.pkl','wb'))
