# closed-loop directed run of each run's ref model, same sequence as tb_dir.v; emits the same text format
import sys, json, importlib.util
sys.path.insert(0,'/home/user/Veri-Sure')
EQ='/tmp/claude-0/-home-user-Veri-Sure/12bb865e-7a51-5506-b55a-e5ac7cf72a4a/scratchpad/eq'
Q='/tmp/claude-0/-home-user-Veri-Sure/12bb865e-7a51-5506-b55a-e5ac7cf72a4a/scratchpad/qual/i2c_master_bit_ctrl'
cnt=int(sys.argv[1]) if len(sys.argv)>1 else 7
res={}
for r in ['luna12','luna13','luna14','luna15']:
    spec=importlib.util.spec_from_file_location('rm'+r, f'{EQ}/corpora/{r}/i2c_master_bit_ctrl/ref_model.py')
    mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    m=mod.Model()
    st=dict(cyc=0, cmd=0, din=0, nReset=0, stretch=0, slave=1)
    lines=[]
    def tick():
        i=dict(clk=0,rst=0,nReset=st['nReset'],ena=1,clk_cnt=cnt,cmd=st['cmd'],din=st['din'],scl_i=1,sda_i=1)
        o=m.outputs(dict(i))
        i['scl_i']=int(o['scl_oen']) & (1-st['stretch']); i['sda_i']=int(o['sda_oen']) & st['slave']
        o=m.outputs(dict(i))
        lines.append(f"{st['cyc']} {st['cmd']} {st['din']} {o['cmd_ack']} {o['busy']} {o['al']} {o['dout']} {o['scl_oen']} {o['sda_oen']} {i['scl_i']}")
        m.advance(dict(i)); st['cyc']+=1
        return o
    def docmd(c,d,stretch_after_release=False):
        st['cmd']=c; st['din']=d; t0=st['cyc']; o=None; sw=None
        while True:
            o=tick()
            if stretch_after_release:
                if sw is None and o['scl_oen']==1 and st['cyc']-t0>2: sw=st['cyc']; st['stretch']=1
                if sw is not None and st['cyc']-sw>=30: st['stretch']=0
            if o['cmd_ack'] or st['cyc']-t0>=400: break
        st['cmd']=0; tick()
        for _ in range(3): tick()
    def rs():
        st['nReset']=0; tick(); tick(); st['nReset']=1
        for _ in range(40): tick()
    rs()
    for name,c,d in [('START',1,0),('WRITE1',4,1),('READ1',8,0),('STOP',2,0)]:
        lines.append('# '+name); docmd(c,d)
    for _ in range(20): tick()
    lines.append('# START2'); docmd(1,0)
    lines.append('# STOP2'); docmd(2,0)
    rs(); docmd(1,0)
    lines.append('# WRITE0'); docmd(4,0)
    lines.append('# AFTERW0_WRITE1'); docmd(4,1)
    rs(); docmd(1,0); docmd(4,0)
    lines.append('# ARBLOSS'); st['slave']=0; st['cmd']=4; st['din']=1; t0=st['cyc']
    while True:
        o=tick()
        if o['cmd_ack'] or o['al'] or st['cyc']-t0>=400: break
    st['slave']=1; st['cmd']=0
    for _ in range(30): tick()
    lines.append('# AFTERAL_START'); docmd(1,0)
    lines.append('# AFTERAL_STOP'); docmd(2,0)
    rs(); docmd(1,0)
    lines.append('# WRITE1STRETCH'); docmd(4,1,True)
    res['ref.'+r]='\n'.join(lines)
json.dump(res,open(f'{Q}/work/dirref2_cnt{cnt}.json','w'))
