"""Generated reference model. Do not edit.

Derived from the specification via specflow S1 + refmodel. Frozen once
gate G4 passes: after the RTL exists, a wrong-RTL hypothesis and a
wrong-model hypothesis compete for every failing check, and the model is
the cheaper one to 'fix' -- which is how a reference model gets
retrofitted to match broken RTL.
"""

from specflow.refmodel.base import RefModel


class Model(RefModel):
    OUTPUT_PORTS = ['cmd_ack', 'busy', 'al', 'dout', 'scl_o', 'scl_oen', 'sda_o', 'sda_oen']
    PROBE_PORTS = ['cscl', 'csda', 'sscl', 'ssda', 'dscl', 'dsda', 'fscl', 'fsda', 'filter_cnt', 'cnt_zero', 'clk_en', 'slave_wait', 'scl_sync', 'sta_condition', 'sto_condition', 'sda_chk', 'idle', 'fsm_active', 'start_sequence', 'stop_sequence', 'read_sequence', 'write_sequence', 'filtered_scl_rising', 'filtered_scl_falling', 'i2c_master_bit_ctrl']
    LATENCY_CYCLES = 1

    def __init__(self):
        self.reset()


    def reset(self):
        self.state = 'IDLE'
        self.phase = 0
        self.cmd_latched = 0
        self.din_latched = 0
        self.cSCL1 = 1
        self.cSCL = 1
        self.cSDA1 = 1
        self.cSDA = 1
        self.fSCL = [1, 1, 1]
        self.fSDA = [1, 1, 1]
        self.sSCL = 1
        self.sSDA = 1
        self.dSCL = 1
        self.dSDA = 1
        self.prev_sSCL = 1
        self.prev_sSDA = 1
        self.cnt = 0
        self.filter_counter = 0
        self.cmd_ack_r = 0
        self.busy_r = 0
        self.al_r = 0
        self.dout_r = 0
        self._update_probes(0, 0, 0, 0, 0, 0, 0, 0)


    def _majority(self, h):
        return 1 if (h[0] + h[1] + h[2]) >= 2 else 0


    def _filter(self, i):
        self.cSCL1 = i['scl_i'] & 1
        self.cSCL = self.cSCL1
        self.cSDA1 = i['sda_i'] & 1
        self.cSDA = self.cSDA1
        interval = (i['clk_cnt'] & 0xffff) >> 2
        if not i['ena']:
            self.filter_counter = 0
        elif interval == 0 or self.filter_counter == 0:
            self.filter_counter = interval
            self.fSCL = [self.fSCL[1], self.fSCL[2], self.cSCL]
            self.fSDA = [self.fSDA[1], self.fSDA[2], self.cSDA]
        else:
            self.filter_counter = (self.filter_counter - 1) & 0xffff
        self.dSCL = self.sSCL
        self.dSDA = self.sSDA
        self.sSCL = self._majority(self.fSCL)
        self.sSDA = self._majority(self.fSDA)


    def _line_outputs(self):
        if self.state == 'IDLE':
            return 1, 1, 0
        if self.state == 'START':
            if self.phase == 0:
                return 1, 1, 0
            if self.phase == 1:
                return 1, 0, 0
            return 0, 0, 0
        if self.state == 'STOP':
            if self.phase == 0:
                return 0, 0, 0
            if self.phase == 1:
                return 1, 0, 0
            return 1, 1, 0
        if self.state == 'READ':
            if self.phase == 0:
                return 0, 1, 0
            if self.phase == 1:
                return 1, 1, 0
            return 0, 1, 0
        if self.state == 'WRITE':
            sda = 0 if self.din_latched == 0 else 1
            if self.phase == 0:
                return 0, sda, 1 if self.din_latched else 0
            if self.phase == 1:
                return 1, sda, 1 if self.din_latched else 0
            return 0, sda, 0
        return 1, 1, 0


    def _divider(self, i, slave_wait, scl_sync):
        clk_en = 0
        reload = i['clk_cnt'] & 0xffff
        if not i['ena']:
            self.cnt = reload
            return 0
        if slave_wait:
            return 0
        if scl_sync or self.cnt == 0:
            self.cnt = reload
            clk_en = 1
        else:
            self.cnt = (self.cnt - 1) & 0xffff
        return clk_en


    def _fsm(self, i, clk_en, slave_wait, sta, sto, sda_chk):
        if self.state == 'IDLE':
            if not i['ena'] or not clk_en:
                return
            c = i['cmd'] & 0xf
            if c == 1:
                self.state, self.phase = 'START', 0
            elif c == 2:
                self.state, self.phase = 'STOP', 0
            elif c == 4:
                self.state, self.phase = 'WRITE', 0
                self.din_latched = i['din'] & 1
            elif c == 8:
                self.state, self.phase = 'READ', 0
            return
        if self.al_r:
            self.state, self.phase = 'IDLE', 0
            return
        if sto and self.state != 'STOP':
            self.al_r = 1
            self.state, self.phase = 'IDLE', 0
            return
        if self.state == 'WRITE' and self.phase == 1 and self.din_latched and not self.sSDA:
            self.al_r = 1
            self.state, self.phase = 'IDLE', 0
            return
        if not i['ena'] or not clk_en or slave_wait:
            return
        if self.state in ('START', 'STOP', 'READ', 'WRITE'):
            if self.phase == 1 and self.state in ('START', 'STOP', 'READ', 'WRITE'):
                if self.state in ('START', 'STOP', 'READ', 'WRITE') and self._line_outputs()[0] and not self.sSCL:
                    return
            if self.phase < 2:
                self.phase += 1
            else:
                self.state, self.phase = 'IDLE', 0
                self.cmd_ack_r = 1


    def _update_probes(self, filter_expired, cnt_zero, clk_en, slave_wait, scl_sync, sta, sto, sda_chk):
        self.cscl = bool(self.cSCL)
        self.csda = bool(self.cSDA)
        self.sscl = bool(self.sSCL)
        self.ssda = bool(self.sSDA)
        self.dscl = bool(self.dSCL)
        self.dsda = bool(self.dSDA)
        self.fscl = bool(self.fSCL[-1])
        self.fsda = bool(self.fSDA[-1])
        self.filter_cnt = bool(filter_expired)
        self.cnt_zero = bool(cnt_zero)
        self.clk_en = bool(clk_en)
        self.slave_wait = bool(slave_wait)
        self.scl_sync = bool(scl_sync)
        self.sta_condition = bool(sta)
        self.sto_condition = bool(sto)
        self.sda_chk = bool(sda_chk)
        self.idle = self.state == 'IDLE'
        self.fsm_active = not self.idle
        self.start_sequence = self.state == 'START'
        self.stop_sequence = self.state == 'STOP'
        self.read_sequence = self.state == 'READ'
        self.write_sequence = self.state == 'WRITE'
        self.filtered_scl_rising = bool(self.sSCL and not self.prev_sSCL)
        self.filtered_scl_falling = bool(self.prev_sSCL and not self.sSCL)
        self.i2c_master_bit_ctrl = True


    def step(self, i):
        o = {p: None for p in self.OUTPUT_PORTS}
        if not i.get('nReset', 1):
            self.reset()
        elif i.get('rst', 0):
            self.reset()
        else:
            old_scl = self.sSCL
            old_sda = self.sSDA
            self._filter(i)
            sta = int((not self.sSDA) and self.dSDA and self.sSCL)
            sto = int(self.sSDA and (not self.dSDA) and self.sSCL)
            rising = int(self.sSCL and not old_scl)
            falling = int(old_scl and not self.sSCL)
            if sta:
                self.busy_r = 1
            if sto:
                self.busy_r = 0
            if rising:
                self.dout_r = self.sSDA
            scl_oen, sda_oen, sda_chk = self._line_outputs()
            slave_wait = bool(scl_oen and not self.sSCL and self.state != 'IDLE')
            scl_sync = bool(scl_oen and falling)
            clk_en = self._divider(i, slave_wait, scl_sync)
            self._fsm(i, clk_en, slave_wait, sta, sto, sda_chk)
            self.cmd_ack_r = 0 if self.cmd_ack_r else self.cmd_ack_r
            self.prev_sSCL = self.sSCL
            self.prev_sSDA = self.sSDA
            self._update_probes(self.filter_counter == 0, self.cnt == 0, clk_en, slave_wait, scl_sync, sta, sto, sda_chk)
        scl_oen, sda_oen, _ = self._line_outputs()
        o['cmd_ack'] = self.cmd_ack_r & 1
        o['busy'] = self.busy_r & 1
        o['al'] = self.al_r & 1
        o['dout'] = self.dout_r & 1
        o['scl_o'] = 0
        o['scl_oen'] = scl_oen & 1
        o['sda_o'] = 0
        o['sda_oen'] = sda_oen & 1
        return o
