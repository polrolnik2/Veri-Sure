import glob,os
R='res'
scen=sorted(set(os.path.basename(f).split('.')[0] for f in glob.glob(R+'/*.log')))
designs=['golden','golden_sbdef']+[f'{r}.{k}' for r in ['luna12','luna13','luna14'] for k in ['gen1','gen2','gen3','r0','final']]
def load(s,d):
    L=[l.split('|') for l in open(f'{R}/{s}.{d}.log') if l.startswith('E')]
    # normalize: outputs part = fields 1 and 2 (dc outs, biu outs)
    return [(' '.join(x[1].split()).lower(), ' '.join(x[2].split()).lower()) for x in L]
def txn(s,d):
    return [l.split(' ',2)[2].strip().lower() for l in open(f'{R}/{s}.{d}.log') if l.startswith('BIU') or l.startswith('DC')]
print('edge-level agreement of each design with each ref model / golden_sbdef over directed scenarios; T = identical transaction log in k/7 scenarios')
hdr=['ref_luna12','ref_luna13','ref_luna14','golden_sbdef','golden']
print(f'{"":14s}'+''.join(f'{h:>20s}' for h in hdr))
for d in designs+['ref_luna12','ref_luna13','ref_luna14']:
    row=''
    for h in hdr:
        n=ok=0; t=0
        for s in scen:
            a=load(s,d); b=load(s,h)
            for x,y in zip(a,b):
                n+=1; ok+= x==y
            t+= txn(s,d)==txn(s,h)
        row+=f'{ok/n:>13.3f} T{t}/{len(scen)}'
    print(f'{d:14s}'+row)
