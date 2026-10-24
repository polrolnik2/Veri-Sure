import json, sys
EQ='/tmp/claude-0/-home-user-Veri-Sure/12bb865e-7a51-5506-b55a-e5ac7cf72a4a/scratchpad/eq'
Q='/tmp/claude-0/-home-user-Veri-Sure/12bb865e-7a51-5506-b55a-e5ac7cf72a4a/scratchpad/qual/i2c_master_bit_ctrl'
M='i2c_master_bit_ctrl'
SN={0:'idle',1:'start_a',2:'start_b',4:'start_c',8:'start_d',0x10:'start_e',0x20:'stop_a',0x40:'stop_b',0x80:'stop_c',0x100:'stop_d',0x200:'rd_a',0x400:'rd_b',0x800:'rd_c',0x1000:'rd_d',0x2000:'wr_a',0x4000:'wr_b',0x8000:'wr_c',0x10000:'wr_d'}
RT=json.load(open(f'{Q}/reset_tps.json'))
G=json.load(open(f'{Q}/work/gBp.json'))
d=sys.argv[1]; sr=sys.argv[2]
t=json.load(open(f'{EQ}/out/{M}/{d}.json'))[sr]
ports=['cmd_ack','busy','al','dout','scl_o','scl_oen','sda_o','sda_oen']
found={}
for tp in RT[sr]:
    g=G[sr][tp]; x=t[tp]
    for i in range(1,len(g)):
        st=SN.get(int(g[i][8],16),'?'); prev=SN.get(int(g[i-1][8],16),'?')
        def P(k): return ports.index(k)
        if 'startwin' not in found and st=='start_e' and g[i][P('scl_oen')]=='1' and x[i][P('scl_oen')]=='0': found['startwin']=(tp,i,st,'scl_oen g=1 d=0')
        if 'rdwin' not in found and st=='rd_d' and g[i][P('scl_oen')]=='1' and x[i][P('scl_oen')]=='0': found['rdwin']=(tp,i,st,'scl_oen g=1 d=0')
        if 'wrwin' not in found and st=='wr_d' and g[i][P('scl_oen')]=='1' and x[i][P('scl_oen')]=='0': found['wrwin']=(tp,i,st,'scl_oen g=1 d=0')
        if 'stopwin' not in found and st=='stop_d' and g[i][P('sda_oen')]=='0' and x[i][P('sda_oen')]=='1': found['stopwin']=(tp,i,st,'sda_oen g=0 d=1')
        if 'trail' not in found and g[i][0]=='1' and x[i][0]=='0' and prev in ('start_e','stop_d','rd_d','wr_d'): found['trail']=(tp,i,prev+'->idle','cmd_ack g=1 d=0')
        if 'alstick' not in found and x[i][2]=='1' and g[i][2]=='0' and any(g[j][2]=='1' for j in range(max(1,i-20),i)): found['alstick']=(tp,i,st,'al g=0 d=1 (golden pulse ended)')
        if 'w0' not in found and x[i][2]=='1' and g[i][2]=='0' and st=='wr_d' and g[i][P('sda_oen')]=='0': found['w0']=(tp,i,st,'al g=0 d=1, own sda_oen=0')
        if 'busy' not in found and x[i][1]!=g[i][1]: found['busy']=(tp,i,st,f'busy g={g[i][1]} d={x[i][1]}')
for k,v in found.items(): print(k, v)
