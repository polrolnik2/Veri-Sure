import json,collections
exec(open('modes.py').read().split('def main')[0])
# ref model as a design, on its own run's segments only; also designs restricted to own-run segments
res=collections.defaultdict(collections.Counter); nseg=collections.Counter()
for k,s in enumerate(segs):
  g=gold_sig(s); gv=[h(x) for x in s['g']]
  r=s['run']; nseg[r]+=1
  refv=list(s['ref'])
  for p,a,b in zip(O,gv,refv):
    if a!=b: res[(r,'ref')][mode(s,g,p,a,b)]+=0  # placeholder
  seen=set()
  for p,a,b in zip(O,gv,refv):
    if a!=b:
      m=mode(s,g,p,a,b)
      if m not in seen: res[(r,'ref')][m]+=1; seen.add(m)
  for d in D['designs']:
    if not d.startswith(r): continue
    seen=set()
    for p,a,b in zip(O,gv,[h(x) for x in s[d]]):
      if a!=b:
        m=mode(s,g,p,a,b)
        if m not in seen: res[(r,d)][m]+=1; seen.add(m)
for r in ['luna12','luna13','luna14','luna15']:
  print('==',r,'own segs',nseg[r])
  for key in sorted(k for k in res if k[0]==r):
    print('  ',key[1], {m.split(' ')[0]:n for m,n in sorted(res[key].items()) if n})
