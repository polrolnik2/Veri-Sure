import json,collections
from rs import keep
EQ='/tmp/claude-0/-home-user-Veri-Sure/12bb865e-7a51-5506-b55a-e5ac7cf72a4a/scratchpad/eq'
gold=json.load(open(f'{EQ}/out/fpu_exceptions/golden.json'))
def h(v):
  try: return int(v,16)
  except: return 'X'
for r in ['luna12','luna13','luna15']:
  st=json.load(open(f'{EQ}/stim/{r}/fpu_exceptions.json')); O=st['outputs']
  r0=json.load(open(f'{EQ}/out/fpu_exceptions/{r}.r0.json'))[r]
  fi=json.load(open(f'{EQ}/out/fpu_exceptions/{r}.final.json'))[r]
  c=collections.Counter(); cp=collections.defaultdict(collections.Counter); cr=collections.Counter()
  for tp,v in st['tps'].items():
    G=gold[r][tp]
    for e,(row,ref) in enumerate(zip(v['rows'],v['ref'])):
      if not keep(r,tp,e): continue
      for pi,p in enumerate(O):
        a=h(r0[tp][e][pi]); b=h(fi[tp][e][pi]); g=h(G[e][pi]); rf=ref[pi]
        if a!=b:
          k=('G' if b==g else '')+('R' if b==rf else '')
          k0=('G' if a==g else '')+('R' if a==rf else '')
          c[(k0 or 'none')+'->'+(k or 'none')]+=1; cp[p][(k0 or 'none')+'->'+(k or 'none')]+=1
          cr['rst' if row[1] else ('en0' if row[2]==0 else 'en1')]+=1
  tot=sum(c.values())
  print(r,'edges*ports changed',tot, dict(c.most_common()), dict(cr))
  for p in O: print('   ',p,dict(cp[p].most_common()))
