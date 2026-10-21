"""Parametrised Python model of golden or1200_dc_fsm with deviation flags.
Flags off == golden (OR1200_DC_STORE_REFILL undefined, DCLS=4).
"""
import json
from pathlib import Path

EQ = Path("/tmp/claude-0/-home-user-Veri-Sure/12bb865e-7a51-5506-b55a-e5ac7cf72a4a/scratchpad/eq")
IDLE, CLOAD, LR3, CSTORE, SR4 = 0, 1, 2, 3, 4
OUTS = ['saved_addr', 'dcram_we', 'biu_read', 'biu_write', 'first_hit_ack',
        'first_miss_ack', 'first_miss_err', 'burst', 'tag_we', 'dc_addr']

FLAGS = [
    'SR',          # store-miss refill enabled (CSTORE miss&valid -> SREFILL4)
    'CI_COMB',     # ci sensed as ci_r|(cycstb&ci) everywhere (acks, exits, dcram/tag/burst) instead of golden mix
    'CI_REFILL',   # in refill states, cycstb&ci also masks dcram_we/tag_we (ungated ci_now)
    'ACK_EVAL',    # load first_hit_ack only while hitmiss_eval
    'ACK_CYC',     # load first_hit_ack also requires cycstb
    'EXIT_EVAL',   # load-hit exit (CLOAD->IDLE on !miss) only while hitmiss_eval
    'LATE_REFILL', # with EXIT_EVAL: after eval, valid -> LREFILL3 regardless of tagcomp_miss
    'BR_LOAD',     # biu_read requires load (no biu_read on store-miss eval cycle)
    'BR_CI',       # biu_read also asserted in CLOAD for ci accesses (load & ci_eff)
    'NO_ADDR_UP',  # no saved_addr[31:13] recapture in first CLOAD/CSTORE cycle
    'ERR_REFILL',  # biudata_error aborts LREFILL3/SREFILL4
    'DWE_BR',      # refill dcram_we additionally requires biu_read
    'ACK_NOERR',   # load first_hit_ack requires !biudata_error
    'LATE_IDLE',   # with EXIT_EVAL: after eval, valid & !miss -> IDLE (hit only recognised at valid)
    'CI_LIVE_WE',  # sub-part of CI_COMB: live cycstb&ci masks burst/dcram_we/tag_we in CLOAD/CSTORE
    'CI_CYC_GATE', # sub-part of CI_COMB: ci attribute only counted when cycstb=1 (acks, exits)
    'CI_HIT_R',    # sub-part of CI_COMB: latched cache_inhibit blocks the CLOAD hit exit
    'ACK_ABORT',   # hit acks (load and store) suppressed when aborting (he&!cyc) or on biudata_error
]


def h2i(s):
    return None if ('x' in s or 'z' in s) else int(s, 16)


class M:
    def __init__(self, f):
        self.f = set(f)
        self.known = False

    def reset(self):
        self.known = True
        self.state = IDLE
        self.saved = 0
        self.he = 0
        self.store = 0
        self.load = 0
        self.cnt = 0
        self.ci_r = 0

    def cie(self, cyc, ci, refill_ok=False):
        """combinational cache-inhibit as the design sees it"""
        st = self.state
        if 'CI_COMB' in self.f:
            if st in (CLOAD, CSTORE):
                return self.ci_r | (cyc & ci)
            if refill_ok and 'CI_REFILL' in self.f:
                return self.ci_r | (cyc & ci)
            return self.ci_r
        return None

    def outputs(self, i):
        rst, en, cyc, ci, we, sel, miss, val, err, addr = i
        if rst:
            self.reset()
        if not self.known:
            return None
        f = self.f
        st = self.state
        CL, CS = st == CLOAD, st == CSTORE
        comb = 'CI_COMB' in f
        live = comb or 'CI_LIVE_WE' in f
        gate = comb or 'CI_CYC_GATE' in f
        # ci terms
        ci_ack = self.ci_r if 'FO' in f else ((self.ci_r | (cyc & ci)) if gate else (self.ci_r | ci))
        if live and (CL or CS):
            ci_we = self.ci_r | (cyc & ci)
        elif comb and 'CI_REFILL' in f:
            ci_we = self.ci_r | (cyc & ci)
        else:
            ci_we = self.ci_r
        fsha = CS and not miss and val and not ci_ack
        if 'ACK_ABORT' in f:
            fsha = fsha and not err and not (self.he and not cyc)
        if 'BR_LOAD' in f:
            br = (self.he and miss and self.load) or (not self.he and self.load)
        else:
            br = (self.he and miss) or (not self.he and self.load)
        if 'BR_CI' in f and CL and self.load and ci_ack:
            br = True
        br = bool(br)
        dwe_load = self.load and val and not ci_we
        if 'DWE_BR' in f:
            dwe_load = dwe_load and br
        dcram_we = (0xF if dwe_load else 0) | (sel if fsha else 0)
        tag_we = br and val and not ci_we
        bw = self.store
        dc_addr = self.saved if ((br or bw) and not self.he) else addr
        lha = CL and not miss and not ci_ack
        if 'ACK_EVAL' in f:
            lha = lha and self.he
        if 'ACK_CYC' in f:
            lha = lha and cyc
        if 'ACK_NOERR' in f:
            lha = lha and not err
        if 'ACK_ABORT' in f:
            lha = lha and not err and not (self.he and not cyc)
        fha = lha or fsha
        self.last_fsha = int(bool(fsha))
        fma = (CL or CS) and val
        fme = (CL or CS) and err
        burst = (CL and miss and not ci_we) or st == LR3 or (st == SR4 and 'SR' in f)
        return [self.saved, dcram_we, int(br), int(bw), int(bool(fha)), int(bool(fma)),
                int(bool(fme)), int(bool(burst)), int(bool(tag_we)), dc_addr & 0xFFFFFFFF]

    def advance(self, i):
        rst, en, cyc, ci, we, sel, miss, val, err, addr = i
        if rst or not self.known:
            if rst:
                self.reset()
            return
        f = self.f
        st = self.state
        comb = 'CI_COMB' in f
        gate = comb or 'CI_CYC_GATE' in f
        hitr = comb or 'CI_HIT_R' in f
        if st == IDLE:
            if en and cyc:
                self.state = CSTORE if we else CLOAD
                self.saved = addr
                self.he = 1
                self.store = 1 if we else 0
                self.load = 0 if we else 1
                self.ci_r = 0
            else:
                self.he = self.store = self.load = self.ci_r = 0
            return
        if st in (CLOAD, CSTORE):
            ci_seen = cyc and ci
            ci_now = self.ci_r if 'FO' in f else ((self.ci_r or ci_seen) if gate else (self.ci_r or ci))
            new_ci = 1 if ci_seen else self.ci_r
            if self.he and 'NO_ADDR_UP' not in f:
                self.saved = (addr & 0xFFFFE000) | (self.saved & 0x1FFF)
            abort = (self.he and not cyc) or err
            if abort or (ci_now and val):
                self.state = IDLE
                self.he = 0
                self.ci_r = 0
                if st == CLOAD:
                    self.load = 0
                else:
                    self.store = 0
                self.load = self.store = 0
                return
            self.ci_r = new_ci
            if st == CLOAD:
                hit_ok = (not miss) and not (self.ci_r if 'FO' in f else (ci_now if hitr else (ci_seen if gate else ci)))
                exit_eval = 'EXIT_EVAL' in f
                if miss and val and not ci_now:
                    self.state = LR3
                    self.saved = (self.saved & ~0xC) | ((((self.saved >> 2) + 1) & 3) << 2)
                    self.he = 0
                    self.cnt = 2
                    self.ci_r = 0
                elif hit_ok and (self.he or not exit_eval):
                    self.state = IDLE
                    self.he = 0
                    self.load = 0
                    self.ci_r = 0
                elif exit_eval and not self.he and val and not ci_now and 'LATE_REFILL' in f:
                    # late valid with tagcomp_miss==0 treated as refill
                    self.state = LR3
                    self.saved = (self.saved & ~0xC) | ((((self.saved >> 2) + 1) & 3) << 2)
                    self.cnt = 2
                elif exit_eval and not self.he and val and not ci_now and not miss and 'LATE_IDLE' in f:
                    self.state = IDLE
                    self.load = 0
                    self.ci_r = 0
                else:
                    self.he = 0
            else:  # CSTORE
                if miss and val and 'SR' in f:
                    self.state = SR4
                    self.he = 0
                    self.store = 0
                    self.load = 1
                    self.cnt = 3
                    self.ci_r = 0
                elif val:
                    self.state = IDLE
                    self.he = 0
                    self.store = 0
                    self.ci_r = 0
                else:
                    self.he = 0
            return
        if st in (LR3, SR4):
            if err and 'ERR_REFILL' in f:
                self.state = IDLE
                self.load = self.store = self.he = self.ci_r = 0
                return
            if val and self.cnt:
                self.cnt -= 1
                self.saved = (self.saved & ~0xC) | ((((self.saved >> 2) + 1) & 3) << 2)
            elif val:
                self.state = IDLE
                self.load = 0
            return
        self.state = IDLE


def stim(run):
    s = json.loads((EQ / 'stim' / run / 'or1200_dc_fsm.json').read_text())
    names = s['inputs']
    idx = [names.index(n) for n in ['rst', 'dc_en', 'dcqmem_cycstb_i', 'dcqmem_ci_i', 'dcqmem_we_i',
                                    'dcqmem_sel_i', 'tagcomp_miss', 'biudata_valid', 'biudata_error',
                                    'start_addr']]
    tps = {}
    for tp in sorted(s['tps']):
        tps[tp] = [[int(r[k] or 0) for k in idx] for r in s['tps'][tp]['rows']]
    refs = {tp: s['tps'][tp]['ref'] for tp in sorted(s['tps'])}
    return tps, refs


def run_model(flags, tps):
    m = M(flags)
    res = {}
    for tp, rows in tps.items():
        out = []
        for r in rows:
            out.append(m.outputs(r))
            m.advance(r)
        res[tp] = out
    return res


def load_trace(design):
    d = json.loads((EQ / 'out' / 'or1200_dc_fsm' / f'{design}.json').read_text())
    return {run: {tp: [[h2i(v) for v in row] for row in rows] for tp, rows in per.items()}
            for run, per in d.items()}


def compare(a, b):
    """count edge/cell mismatches where both known; returns (edges, mismatching_edges, cells_by_port)"""
    ne = nm = 0
    port = [0] * len(OUTS)
    for tp in a:
        for ra, rb in zip(a[tp], b[tp]):
            if ra is None or rb is None:
                continue
            ne += 1
            bad = False
            for k, (x, y) in enumerate(zip(ra, rb)):
                if x is None or y is None:
                    continue
                if x != y:
                    port[k] += 1
                    bad = True
            nm += bad
    return ne, nm, port


def run_model_fresh(flags, tps):
    res = {}
    for tp, rows in tps.items():
        m = M(flags); m.reset()
        out = []
        for r in rows:
            out.append(m.outputs(r))
            m.advance(r)
        res[tp] = out
    return res
