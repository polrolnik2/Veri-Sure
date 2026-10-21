# derive per-design phase tables (ticks after decode) from the directed closed-loop RLE (clk_cnt=7, period 8)
import json
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
        secs[cur].append((p[7]+p[8], p[3]=='1'))
    return secs
T={}
for n,out in res.items():
    s=parse(out); tab={}
    for sec,align in [('START',2),('WRITE1',4),('READ1',4),('STOP',4)]:
        rows=s[sec]; a=[i for i,(k,ack) in enumerate(rows) if ack]
        if not a: tab[sec]=None; continue
        rows=rows[:a[0]+1]
        rle=[]
        for k,ack in rows:
            if rle and rle[-1][0]==k and not ack: rle[-1][1]+=1
            else: rle.append([k,1])
        # rle: last element is the ack row (level at ack)
        ticks=[]  # level per tick after decode (tick0 = decode)
        prevC=None
        for idx,(k,c) in enumerate(rle[:-1]):
            L=c
            if idx==0: L-=align
            elif k[0]=='1' and prevC=='0': L-=5   # SCL release -> filter/slave_wait stretch
            nph=max(0,round(L/P)) if idx>0 else round(L/P)
            # first segment: level existed before decode; nph ticks of it including decode
            ticks += [k]*nph if idx>0 else [k]*nph
            prevC=k[0]
        ticks.append(rle[-1][0]+'A')
        tab[sec]=ticks
    T[n]=tab
    print(f'{n:13s}', ' | '.join(f"{k[:2]}:{','.join(v) if v else None}" for k,v in tab.items()))
json.dump(T,open(f'{Q}/tables.json','w'),indent=1)
