import json,collections
D=json.load(open('settled.json'))
O=D['outputs']; segs=[s for s in D['segs'] if s['sc']['rst']==0]
def h(v): return int(v,16) if all(c in '0123456789abcdefABCDEF' for c in v) else 'X'
print('segments (no rst):',len(segs))
print('%-14s'%'design', ' '.join('%9s'%p for p in O), ' anyport')
for d in D['designs']+['ref']:
  mm=collections.Counter(); n=0; anym=0
  for s in segs:
    if d=='ref':
      if s['run']!=s['run']: continue
      vals=[x for x in s['ref']]
    else:
      vals=[h(x) for x in s[d]]
    g=[h(x) for x in s['g']]
    n+=1; a=0
    for p,gv,dv in zip(O,g,vals):
      if gv!=dv: mm[p]+=1; a=1
    anym+=a
  print('%-14s'%d, ' '.join('%8.1f%%'%(100*mm[p]/n) for p in O), ' %.1f%%'%(100*anym/n))
