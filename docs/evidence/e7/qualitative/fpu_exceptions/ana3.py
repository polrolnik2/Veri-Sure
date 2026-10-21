import json,collections,sys
D=json.load(open('settled.json'))
O=D['outputs']; segs=[s for s in D['segs'] if s['sc']['rst']==0]
def h(v): return int(v,16) if all(c in '0123456789abcdefABCDEF' for c in v) else 'X'
port=sys.argv[1]; pi=O.index(port)
want=tuple(sys.argv[2:4]) if len(sys.argv)>3 and sys.argv[2]!='-' else None
def vk(v):
  if v=='X': return 'X'
  if port!='out': return str(v)
  s=v>>63; e=(v>>52)&0x7ff; f=v&((1<<52)-1)
  if e==0x7ff and f==0: return ('-' if s else '+')+'inf'
  if e==0x7ff: return ('-' if s else '+')+'nan%03x'%(f>>40)
  if e==0x7fe and f==(1<<52)-1: return ('-' if s else '+')+'max'
  if e==0 and f==0: return ('-' if s else '+')+'0'
  return 'num'
cnt=collections.defaultdict(collections.Counter); ex={}
for s in segs:
  g=h(s['g'][pi]); sc=s['sc']
  key=(sc['op'],sc['a'],sc['b'],'en%d'%sc['en'],'inz%d'%sc['inz'],'ovf%d'%sc['ovf'],'man%d'%(sc['man']!=0),'rm%d'%sc['rm'])
  for d in D['designs']:
    v=h(s[d][pi])
    if v!=g and (want is None or (vk(g),vk(v))==want):
      k2=(vk(g),vk(v))+key
      cnt[k2][d]+=1
      ex.setdefault(k2,(d,s['run'],s['tp'],s['e'],s['g'][pi],s[d][pi]))
tot={m:sum(c.values()) for m,c in cnt.items()}
for m in sorted(tot,key=lambda m:-tot[m])[:int(sys.argv[4]) if len(sys.argv)>4 else 30]:
  print(m, tot[m], 'nd',len(cnt[m]), ('all19' if len(cnt[m])==19 else sorted(cnt[m])), ex[m])
