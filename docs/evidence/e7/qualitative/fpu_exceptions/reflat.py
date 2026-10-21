import json,collections
EQ='/tmp/claude-0/-home-user-Veri-Sure/12bb865e-7a51-5506-b55a-e5ac7cf72a4a/scratchpad/eq'
for r in ['luna12','luna13','luna14','luna15']:
  st=json.load(open(f'{EQ}/stim/{r}/fpu_exceptions.json')); O=st['outputs']
  lat={p:collections.Counter() for p in O}
  for tp,v in st['tps'].items():
    rows=v['rows']; t=v['ref']; s=0
    for k in range(1,len(rows)+1):
      if k==len(rows) or rows[k]!=rows[s]:
        if k-s>=12 and s>0 and rows[s][2]==1 and rows[s][1]==0 and rows[s-1][2]==1 and rows[s-1][1]==0:
          e=k-1
          for pi,p in enumerate(O):
            fin=t[e][pi]
            if t[s-1][pi]==fin: continue
            j=e
            while j>s and t[j-1][pi]==fin: j-=1
            lat[p][j-s]+=1
        s=k
  print(r,'ref', {p:dict(lat[p].most_common(3)) for p in O})
