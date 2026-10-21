import json, sys
EQ='/tmp/claude-0/-home-user-Veri-Sure/12bb865e-7a51-5506-b55a-e5ac7cf72a4a/scratchpad/eq'
M='i2c_master_bit_ctrl'
sr, tp = sys.argv[1], sys.argv[2]
designs = sys.argv[3].split(',')
lo = int(sys.argv[4]) if len(sys.argv)>4 else 0
hi = int(sys.argv[5]) if len(sys.argv)>5 else 10**9
s=json.load(open(f'{EQ}/stim/{sr}/{M}.json'))
ins=s['inputs']; outs=s['outputs']
import os; GN=os.environ.get('GOLD','golden'); T={'golden':(json.load(open(f'{EQ}/out/{M}/golden.json')) if GN=='golden' else json.load(open('/tmp/claude-0/-home-user-Veri-Sure/12bb865e-7a51-5506-b55a-e5ac7cf72a4a/scratchpad/qual/i2c_master_bit_ctrl/work/'+GN+'.json')))[sr][tp]}
for d in designs: T[d]=json.load(open(f'{EQ}/out/{M}/{d}.json' if not d.startswith(('cx_','cy_','m','g')) else '/tmp/claude-0/-home-user-Veri-Sure/12bb865e-7a51-5506-b55a-e5ac7cf72a4a/scratchpad/qual/i2c_master_bit_ctrl/work/'+d+'.json'))[sr][tp]
rows=s['tps'][tp]['rows']; ref=s['tps'][tp]['ref']
print('notes', s['tps'][tp].get('notes'))
ab={'cmd_ack':'k','busy':'b','al':'a','dout':'d','scl_o':'','scl_oen':'C','sda_o':'','sda_oen':'D'}
sel=[i for i,o in enumerate(outs) if ab[o]]
hdr='edge rst nR ena cnt cmd din scl sda | ' + '  '.join(f"{n[:6]:>6}" for n in ['ref','golden']+designs)
print('outputs order:', ''.join(ab[outs[i]] for i in sel))
print(hdr)
prev=None
import os
CH=os.environ.get('CH')
for i in range(max(lo,0), min(hi,len(rows))):
    r=rows[i]
    key=(tuple(r),)+tuple(tuple(T[d][i]) for d in ['golden']+designs)+(tuple(ref[i]) if i<len(ref) else (),)
    if CH and key==prev: continue
    prev=key
    iv=dict(zip(ins,r))
    def f(v): return ''.join(str(v[k]) for k in sel)
    line=f"{i:4d} {iv['rst']} {iv['nReset']} {iv['ena']} {iv['clk_cnt']:3d} {iv['cmd']:2d} {iv['din']} {iv['scl_i']} {iv['sda_i']} | {f(ref[i]) if i<len(ref) else '-':>6}  " + '  '.join(f"{f(T[d][i]):>6}" for d in ['golden']+designs)
    gl=f(T['golden'][i])
    flags=''.join('*' if any(a!=b and b!='x' for a,b in zip(f(T[d][i]),gl)) else '.' for d in designs)
    print(line, flags)
