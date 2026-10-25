# simulate a design file (open loop) on all 4 stim runs with the sim.py testbench -> json
import json, subprocess, sys
from pathlib import Path
EQ=Path('/tmp/claude-0/-home-user-Veri-Sure/12bb865e-7a51-5506-b55a-e5ac7cf72a4a/scratchpad/eq')
Q=Path('/tmp/claude-0/-home-user-Veri-Sure/12bb865e-7a51-5506-b55a-e5ac7cf72a4a/scratchpad/qual/i2c_master_bit_ctrl')
M='i2c_master_bit_ctrl'
TASK='/home/user/Veri-Sure/benchmarks/chipverilog/Des/i2c/i2c_master_bit_ctrl'
name, src = sys.argv[1], sys.argv[2]
tb = sys.argv[3] if len(sys.argv)>3 else str(EQ/'work'/M/'tb.v')
vvp=Q/'work'/f'{name}.vvp'
c=subprocess.run(['iverilog','-g2012','-s','tb','-o',str(vvp),f'-I{TASK}',f'-I{TASK}/..',tb,src],capture_output=True,text=True)
if c.returncode: print(c.stderr); sys.exit(1)
res={}
for r in ['luna12','luna13','luna14','luna15']:
    st=json.load(open(EQ/'stim'/r/f'{M}.json'))
    o=Q/'work'/f'{name}.{r}.out'
    subprocess.run(['vvp','-n',str(vvp),f'+in={EQ}/stimtxt/{r}/{M}.txt',f'+out={o}'],capture_output=True,text=True)
    tps=sorted(st['tps']); cur=-1; per={tp:[] for tp in tps}
    for line in o.read_text().splitlines():
        if line=='#': cur+=1; continue
        per[tps[cur]].append(line.split())
    res[r]=per; o.unlink()
(Q/'work'/f'{name}.json').write_text(json.dumps(res))
print(name,'ok')
