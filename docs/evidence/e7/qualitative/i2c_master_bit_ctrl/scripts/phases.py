# summarise directed sim: per command, RLE of (scl_oen,sda_oen) from cmd issue to ack, ack latency
import json, sys
Q='/tmp/claude-0/-home-user-Veri-Sure/12bb865e-7a51-5506-b55a-e5ac7cf72a4a/scratchpad/qual/i2c_master_bit_ctrl'
res=json.load(open(f'{Q}/work/dir_cnt{sys.argv[1]}.json')); res.update(json.load(open(f'{Q}/work/dirref_cnt{sys.argv[1]}.json')))
sel=sys.argv[2].split(',') if len(sys.argv)>2 else None
def parse(out):
    secs={}; cur=None
    for l in out.splitlines():
        if l.startswith('# '): cur=l[2:]; secs[cur]=[]; continue
        if cur is None: continue
        p=l.split()
        if len(p)<10: continue
        secs[cur].append(dict(cyc=int(p[0]),cmd=int(p[1]),ack=p[3],busy=p[4],al=p[5],dout=p[6],C=p[7],D=p[8]))
    return secs
for n,out in res.items():
    if sel and n not in sel: continue
    s=parse(out)
    line=[]
    for sec in ['START','WRITE0','WRITE1','READ1','READ0','STOP','START2','WRITE1STRETCH','STOP2']:
        rows=s.get(sec,[])
        if not rows: line.append(f'{sec}:-'); continue
        rle=[]
        for r in rows:
            key=r['C']+r['D']+('A' if r['ack']=='1' else '')
            if rle and rle[-1][0]==key: rle[-1][1]+=1
            else: rle.append([key,1])
        ack=[i for i,r in enumerate(rows) if r['ack']=='1']
        extra=''.join(f"{k}" for k in ['busy','al','dout'] )
        line.append(f"{sec}:ack@{ack[0] if ack else None} "+' '.join(f'{k}x{c}' for k,c in rle)+f" |b{rows[-1]['busy']}a{''.join(sorted(set(r['al'] for r in rows)))}d{rows[-1]['dout']}")
    print('==',n); print('\n'.join('   '+x for x in line))
