import json, sys
Q='/tmp/claude-0/-home-user-Veri-Sure/12bb865e-7a51-5506-b55a-e5ac7cf72a4a/scratchpad/qual/i2c_master_bit_ctrl'
res=json.load(open(f'{Q}/work/dir2_cnt7.json')); res.update(json.load(open(f'{Q}/work/dirref2_cnt7.json')))
P=8
def parse(out):
    secs={}; cur=None
    for l in out.splitlines():
        if l.startswith('# '): cur=l[2:]; secs[cur]=[]; continue
        if cur is None: continue
        p=l.split()
        if len(p)<10: continue
        secs[cur].append(dict(ack=p[3],busy=p[4],al=p[5],dout=p[6],C=p[7],D=p[8]))
    return secs
sigs={}
for n,out in res.items():
    s=parse(out); sig={}
    for sec,lv in [('START','10'),('START2','10'),('WRITE1','11'),('READ1','11'),('STOP','10'),('STOP2','10'),('WRITE0','10'),('WRITE1STRETCH','11')]:
        rows=s[sec]
        ack=[i for i,r in enumerate(rows) if r['ack']=='1']
        al=any(r['al']=='1' for r in rows)
        if not ack: sig[sec]='NOACK'+('/al' if al else ''); continue
        a=ack[0]
        rle=[]
        for r in rows[:a]:
            k=r['C']+r['D']
            if rle and rle[-1][0]==k: rle[-1][1]+=1
            else: rle.append([k,1])
        idx=[i for i,(k,c) in enumerate(rle) if k==lv]
        if not idx: sig[sec]='nowin'; continue
        w=rle[idx[-1]][1]
        trail=sum(c for k,c in rle[idx[-1]+1:])
        adj=0 if sec.startswith('START') else 5
        if sec=='WRITE1STRETCH': adj=35
        wp=round((w-adj)/P); tp=round(trail/P)
        sig[sec]=f'W{wp}T{tp}'+('/al' if al else '')
    # arbitration
    ar=s['ARBLOSS']; alc=sum(r['al']=='1' for r in ar)
    sig['AL_len']=alc
    sig['AFTERAL_START']='ack' if any(r['ack']=='1' for r in s['AFTERAL_START']) else 'NOACK'
    sig['al_after']=sum(r['al']=='1' for r in s['AFTERAL_START']+s['AFTERAL_STOP'])
    sig['W0_al']=sum(r['al']=='1' for r in s['WRITE0'])
    sigs[n]=sig
    print(f"{n:13s}", ' '.join(f"{k[:6]}:{v}" for k,v in sig.items()))
json.dump(sigs,open(f'{Q}/phase_sigs.json','w'),indent=1)
