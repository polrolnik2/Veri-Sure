import json,collections
EQ='/tmp/claude-0/-home-user-Veri-Sure/12bb865e-7a51-5506-b55a-e5ac7cf72a4a/scratchpad/eq'
gold=json.load(open(f'{EQ}/out/fpu_exceptions/golden.json'))
def h(v):
  try: return int(v,16)
  except: return 'X'
r='luna12'
st=json.load(open(f'{EQ}/stim/{r}/fpu_exceptions.json')); O=st['outputs']
r0=json.load(open(f'{EQ}/out/fpu_exceptions/{r}.r0.json'))[r]
fi=json.load(open(f'{EQ}/out/fpu_exceptions/{r}.final.json'))[r]
c=collections.defaultdict(collections.Counter); ex={}
for tp,v in st['tps'].items():
  G=gold[r][tp]; rows=v['rows']
  for e,(row,ref) in enumerate(zip(rows,v['ref'])):
    typ='rst' if row[1] else ('en0' if row[2]==0 else ('en1-afterchange<=3' if e>0 and any(rows[j]!=row for j in range(max(0,e-3),e)) else 'en1-stable'))
    for pi,p in enumerate(O):
      a=h(r0[tp][e][pi]); b=h(fi[tp][e][pi]); g=h(G[e][pi]); rf=ref[pi]
      if a!=b:
        k=(('G' if a==g else '')+('R' if a==rf else '') or 'none')+'->'+(('G' if b==g else '')+('R' if b==rf else '') or 'none')
        c[typ][(p if p in('out','ex_enable') else 'flags',k)]+=1
        ex.setdefault((typ,p,k),(tp,e,G[e][pi],r0[tp][e][pi],fi[tp][e][pi],ref[pi]))
for t in c: print(t, dict(c[t].most_common()))
for k in [k for k in ex if k[0]=='rst'][:4]: print(k,ex[k])
for k in [k for k in ex if k[0]!='rst' and k[2]=='G->R'][:6]: print(k,ex[k])
