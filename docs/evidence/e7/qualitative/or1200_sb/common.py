import json, os
EQ='/tmp/claude-0/-home-user-Veri-Sure/12bb865e-7a51-5506-b55a-e5ac7cf72a4a/scratchpad/eq'
RUNS=['luna12','luna13','luna14']
KINDS=['gen1','gen2','gen3','r0','final']
DESIGNS=[f'{r}.{k}' for r in RUNS for k in KINDS]
OUTS=['dcsb_dat_o','dcsb_ack_o','dcsb_err_o','sbbiu_dat_o','sbbiu_adr_o','sbbiu_cyc_o','sbbiu_stb_o','sbbiu_we_o','sbbiu_sel_o','sbbiu_cab_o']
_stim={}
def stim(run):
    if run not in _stim:
        _stim[run]=json.load(open(f'{EQ}/stim/{run}/or1200_sb.json'))
    return _stim[run]
_out={}
def trace(design, cl=False):
    key=(design,cl)
    if key not in _out:
        d='cl_out' if cl else 'out'
        _out[key]=json.load(open(f'{EQ}/{d}/or1200_sb/{design}.json'))
    return _out[key]
def toint(h):
    try: return int(h,16)
    except Exception: return None
def passthru(inp_names, row):
    i=dict(zip(inp_names,row))
    return [i['sbbiu_dat_i'],i['sbbiu_ack_i'],i['sbbiu_err_i'],i['dcsb_dat_i'],i['dcsb_adr_i'],i['dcsb_cyc_i'],i['dcsb_stb_i'],i['dcsb_we_i'],i['dcsb_sel_i'],i['dcsb_cab_i']]
