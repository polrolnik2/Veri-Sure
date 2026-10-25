"""hyb_run.py DESIGN MODE -- run DESIGN's byte FSM over the golden bit controller (own bit_ctrl stripped),
MODE = id|swap|bin (command-encoding adapter), or 'own' (unchanged design, sanity check). Writes traces + summary."""
import json, re, subprocess, sys, os
from pathlib import Path
Q=Path('/tmp/claude-0/-home-user-Veri-Sure/12bb865e-7a51-5506-b55a-e5ac7cf72a4a/scratchpad/qual/i2c_master_byte_ctrl')
EQ=Path('/tmp/claude-0/-home-user-Veri-Sure/12bb865e-7a51-5506-b55a-e5ac7cf72a4a/scratchpad/eq')
G=Path('/home/user/Veri-Sure/benchmarks/chipverilog/Des/i2c')
M='i2c_master_byte_ctrl'
d, mode = sys.argv[1], sys.argv[2]
src = Path(sys.argv[3]) if len(sys.argv)>3 else Q/'src'/f'{d}.sv'
txt = src.read_text()
H = Q/'hyb'
work = H/'work'; work.mkdir(exist_ok=True)
tag=f'{d}.{mode}'
files=[str(H/'tb.v')]
if mode in ('own','tx'):
    files.append(str(src))
    if mode=='tx': files.append(str(H/'golden_bit_renamed.v'))
else:
    stripped = re.sub(r'^\s*module\s+i2c_master_bit_ctrl\b.*?^\s*endmodule\b', '', txt, flags=re.S|re.M)
    assert 'module i2c_master_bit_ctrl' not in stripped
    p = work/f'{tag}.sv'; p.write_text(stripped)
    files += [str(p), str(H/f'shim_{mode}.v'), str(H/'golden_bit_renamed.v')]
vvp = work/f'{tag}.vvp'
c = subprocess.run(['iverilog','-g2012','-s','tb','-o',str(vvp),f'-I{G/M}',f'-I{G}',*files],capture_output=True,text=True)
if c.returncode: print('COMPILE ERROR', c.stderr[-2000:]); sys.exit(1)
RST = os.environ.get('RSTPFX') == '1'
NPFX = 3
def stimtxt(r):
    src = EQ/'stimtxt'/r/f'{M}.txt'
    if not RST: return src
    dst = Q/'stimtxt_rst'/f'{r}.txt'
    if not dst.is_file():
        dst.parent.mkdir(exist_ok=True)
        rows=[]
        for line in src.read_text().splitlines():
            rows.append(line)
            if line.strip()=='0':
                rows += ['1 1 0 0 0 0 0 0 0 0 0 1 1']*NPFX
        dst.write_text('\n'.join(rows)+'\n')
    return dst
stims = {r: json.loads((EQ/'stim'/r/f'{M}.json').read_text()) for r in ('luna12','luna13','luna14')}
res={}
for r in stims:
    o = work/f'{tag}.{r}.out'
    subprocess.run(['vvp','-n',str(vvp),f'+in={stimtxt(r)}',f'+out={o}'],capture_output=True,text=True,timeout=3600)
    tps, cur = sorted(stims[r]['tps']), -1
    per={tp:[] for tp in tps}
    for line in o.read_text().splitlines():
        if line=='#': cur+=1; skip = NPFX if RST else 0; continue
        if skip: skip-=1; continue
        per[tps[cur]].append(line.split())
    res[r]=per; o.unlink()
vvp.unlink(missing_ok=True)
TD = H/('traces_rst' if RST else 'traces'); TD.mkdir(exist_ok=True)
(TD/f'{tag}.json').write_text(json.dumps(res))
print(tag,'ok',flush=True)
