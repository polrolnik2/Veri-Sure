import subprocess, sys, json
from pathlib import Path
Q=Path('/tmp/claude-0/-home-user-Veri-Sure/12bb865e-7a51-5506-b55a-e5ac7cf72a4a/scratchpad/qual/i2c_master_bit_ctrl')
EQ=Path('/tmp/claude-0/-home-user-Veri-Sure/12bb865e-7a51-5506-b55a-e5ac7cf72a4a/scratchpad/eq')
E=Path('/home/user/Veri-Sure/docs/evidence/e7')
TASK='/home/user/Veri-Sure/benchmarks/chipverilog/Des/i2c/i2c_master_bit_ctrl'
def files():
    d={'golden':Q/'gv'/'gB.v'}
    for r in ['luna12','luna13','luna14','luna15']:
        for k in (1,2,3): d[f'{r}.gen{k}']=E/r/'ablation'/'i2c_master_bit_ctrl'/f'gen{k}'/'rtl_deliverable.sv'
        d[f'{r}.r0']=EQ/'designs'/r/'i2c_master_bit_ctrl'/'r0.sv'
        d[f'{r}.final']=E/r/'editor'/'i2c_master_bit_ctrl'/'rtl_deliverable.sv'
    return d
cnt=sys.argv[1] if len(sys.argv)>1 else '7'
only=sys.argv[2].split(',') if len(sys.argv)>2 else None
res={}
for n,f in files().items():
    if only and n not in only: continue
    v=Q/'work'/f'dir_{n}.vvp'
    c=subprocess.run(['iverilog','-g2012','-s','tb','-o',str(v),f'-I{TASK}',f'-I{TASK}/..',str(Q/'scripts'/'tb_dir2.v'),str(f)],capture_output=True,text=True)
    if c.returncode: print(n,'COMPILE',c.stderr[-300:]); continue
    p=subprocess.run(['vvp','-n',str(v),f'+cnt={cnt}'],capture_output=True,text=True,timeout=120)
    res[n]=p.stdout
(Q/'work'/f'dir2_cnt{cnt}.json').write_text(json.dumps(res))
print('done', len(res))
