# Python mirror of tbd.v for the run reference models
import sys, importlib.util
sys.path.insert(0,'/home/user/Veri-Sure')
EQ='/tmp/claude-0/-home-user-Veri-Sure/12bb865e-7a51-5506-b55a-e5ac7cf72a4a/scratchpad/eq'
def load(run):
    spec=importlib.util.spec_from_file_location('rm_'+run, f'{EQ}/corpora/{run}/or1200_sb/ref_model.py')
    m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m.Model
def run(Model, scen_path, out_path):
    L=open(scen_path).read().split()
    N,LAT,ERRADR,NCYC=int(L[0]),int(L[1]),int(L[2],16),int(L[3])
    T=[tuple(int(x,16) for x in L[4+4*k:8+4*k]) for k in range(N)]
    m=Model(); fo=open(out_path,'w')
    z=dict(rst=1,dcsb_dat_i=0,dcsb_adr_i=0,dcsb_cyc_i=0,dcsb_stb_i=0,dcsb_we_i=0,dcsb_sel_i=0,dcsb_cab_i=0,sbbiu_dat_i=0,sbbiu_ack_i=0,sbbiu_err_i=0)
    for _ in range(2): m.outputs(z); m.advance(z)
    idx=cnt=0; sack=serr=0; srd=0
    for c in range(NCYC):
        i=dict(z); i['rst']=0
        if idx<N:
            we,adr,dat,sel=T[idx]; i.update(dcsb_cyc_i=1,dcsb_stb_i=1,dcsb_we_i=we&1,dcsb_adr_i=adr,dcsb_dat_i=dat,dcsb_sel_i=sel&15)
        i.update(sbbiu_ack_i=sack,sbbiu_err_i=serr,sbbiu_dat_i=srd)
        o=m.outputs(i)
        fo.write("E %d %d %d %d %d %08x %08x | %d %d %08x | %d %d %d %08x %08x %x %d | %d %d\n"%(c,idx,i['dcsb_cyc_i'],i['dcsb_we_i'],i['dcsb_stb_i'],i['dcsb_adr_i'],i['dcsb_dat_i'],
            o['dcsb_ack_o'],o['dcsb_err_o'],o['dcsb_dat_o'],o['sbbiu_cyc_o'],o['sbbiu_stb_o'],o['sbbiu_we_o'],o['sbbiu_adr_o'],o['sbbiu_dat_o'],o['sbbiu_sel_o'],o['sbbiu_cab_o'],sack,serr))
        if sack or serr: fo.write("BIU %d cyc=%d stb=%d we=%d adr=%08x dat=%08x sel=%x %s\n"%(c,o['sbbiu_cyc_o'],o['sbbiu_stb_o'],o['sbbiu_we_o'],o['sbbiu_adr_o'],o['sbbiu_dat_o'],o['sbbiu_sel_o'],'ERR' if serr else 'ACK'))
        if o['dcsb_ack_o'] or o['dcsb_err_o']: fo.write("DC %d idx=%d %s dat_o=%08x\n"%(c,idx,'ERR' if o['dcsb_err_o'] else 'ACK',o['dcsb_dat_o']))
        sn=en=0; rn=0
        if o['sbbiu_cyc_o'] and o['sbbiu_stb_o'] and not (sack or serr):
            if cnt>=LAT:
                if o['sbbiu_adr_o']==ERRADR: en=1
                else: sn=1
                rn=o['sbbiu_adr_o']^0xA5A5A5A5; cnt=0
            else: cnt+=1
        elif not (o['sbbiu_cyc_o'] and o['sbbiu_stb_o']): cnt=0
        if idx<N and (o['dcsb_ack_o'] or o['dcsb_err_o']): idx+=1
        m.advance(i)
        sack,serr,srd=sn,en,rn
    fo.close()
if __name__=='__main__':
    run(load(sys.argv[1]), sys.argv[2], sys.argv[3])
