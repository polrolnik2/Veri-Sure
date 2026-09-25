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
    PROBE_PORTS = ['idle', 'cnt_zero', 'clk_en', 'slave_wait', 'scl_sync', 'cscl', 'csda', 'filter_cnt', 'filter_cnt_expired', 'fscl', 'fsda', 'sscl', 'ssda', 'dscl', 'dsda', 'sta_condition', 'sto_condition', 'active_command', 'sda_chk', 'filtered_scl_rise', 'start_sequence', 'stop_sequence', 'read_sequence', 'write_sequence']
    LATENCY_CYCLES = 1

    def __init__(self):
        self.reset()


    def reset(self):
        self._reset_state()


    def _reset_state(self):
        self.state = 'IDLE'
        self.cmd_latched = 0
        self.din_latched = 0
        self.cmd_ack_r = 0
        self.busy_r = 0
        self.al_r = 0
        self.dout_r = 0
        self.scl_oen_r = 1
        self.sda_oen_r = 1
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
        self.cnt = 0
        self.filter_counter = 0
        self._probes()


    def _majority(self, h):
        return 1 if (h[0] + h[1] + h[2]) >= 2 else 0


    def _filter_step(self, i, enabled):
        self.cSCL1 = int(i['scl_i']) & 1
        self.cSCL = self.cSCL1
        self.cSDA1 = int(i['sda_i']) & 1
        self.cSDA = self.cSDA1
        expired = False
        interval = (int(i['clk_cnt']) & 0xffff) >> 2
        if not enabled:
            self.filter_counter = 0
        elif interval == 0 or self.filter_counter == 0:
            expired = True
            self.filter_counter = interval
            self.fSCL = [self.fSCL[1], self.fSCL[2], self.cSCL]
            self.fSDA = [self.fSDA[1], self.fSDA[2], self.cSDA]
        else:
            self.filter_counter = (self.filter_counter - 1) & 0xffff
        old_scl = self.sSCL
        old_sda = self.sSDA
        if enabled and expired:
            self.sSCL = self._majority(self.fSCL)
            self.sSDA = self._majority(self.fSDA)
        self.dSCL = old_scl
        self.dSDA = old_sda
        return expired, (old_scl == 0 and self.sSCL == 1), (old_scl == 1 and self.sSCL == 0), (old_sda == 1 and self.sSDA == 0), (old_sda == 0 and self.sSDA == 1)


    def _state_outputs(self):
        scl = 1
        sda = 1
        if self.state in ('START_SDA', 'START_LOW'):
            sda = 0
        if self.state == 'START_LOW':
            scl = 0
        elif self.state == 'STOP_SDA':
            sda = 0
        elif self.state == 'STOP_SCL':
            sda = 0
        elif self.state == 'READ_HIGH':
            scl = 1
            sda = 1
        elif self.state == 'READ_LOW':
            scl = 0
            sda = 1
        elif self.state == 'WRITE_SET':
            scl = 0
            sda = 0 if self.din_latched == 0 else 1
        elif self.state == 'WRITE_HIGH':
            scl = 1
            sda = 0 if self.din_latched == 0 else 1
        elif self.state == 'WRITE_LOW':
            scl = 0
            sda = 0 if self.din_latched == 0 else 1
        self.scl_oen_r = scl
        self.sda_oen_r = sda


    def _probes(self, expired=False, clk_en=False, slave_wait=False, scl_sync=False,
                filtered_scl_rise=False, sta=False, sto=False):
        self.idle = self.state == 'IDLE'
        self.cnt_zero = self.cnt == 0
        self.clk_en = bool(clk_en)
        self.slave_wait = bool(slave_wait)
        self.scl_sync = bool(scl_sync)
        self.cscl = bool(self.cSCL)
        self.csda = bool(self.cSDA)
        self.filter_cnt = bool(self.filter_counter == 0)
        self.filter_cnt_expired = bool(expired)
        self.fscl = bool(self._majority(self.fSCL))
        self.fsda = bool(self._majority(self.fSDA))
        self.sscl = bool(self.sSCL)
        self.ssda = bool(self.sSDA)
        self.dscl = bool(self.dSCL)
        self.dsda = bool(self.dSDA)
        self.sta_condition = bool(sta)
        self.sto_condition = bool(sto)
        self.active_command = self.state != 'IDLE'
        self.sda_chk = self.state == 'WRITE_HIGH' and self.din_latched == 1
        self.filtered_scl_rise = bool(filtered_scl_rise)
        self.start_sequence = self.state in ('START_RELEASE', 'START_SDA', 'START_LOW')
        self.stop_sequence = self.state in ('STOP_SDA', 'STOP_SCL', 'STOP_RELEASE')
        self.read_sequence = self.state in ('READ_LOW', 'READ_HIGH', 'READ_DONE')
        self.write_sequence = self.state in ('WRITE_SET', 'WRITE_HIGH', 'WRITE_LOW')


    def step(self, i):
        o = {p: None for p in self.OUTPUT_PORTS}
        if int(i['nReset']) == 0:
            self._reset_state()
        elif int(i['rst']) != 0:
            self._reset_state()
        else:
            self.cmd_ack_r = 0
            enabled = int(i['ena']) != 0
            self._state_outputs()
            released_scl_wait = self.scl_oen_r == 1 and self.sSCL == 0
            old_scl = self.sSCL
            expired, scl_rise, scl_fall, sda_fall, sda_rise = self._filter_step(i, enabled)
            sta = bool(sda_fall and self.sSCL)
            sto = bool(sda_rise and self.sSCL)
            self.busy_r = 1 if sta else (0 if sto else self.busy_r)
            released_scl_wait = self.scl_oen_r == 1 and self.sSCL == 0
            scl_sync = bool(self.scl_oen_r == 1 and old_scl == 1 and self.sSCL == 0)
            if not enabled:
                self.cnt = int(i['clk_cnt']) & 0xffff
                clk_en = False
            elif released_scl_wait:
                clk_en = False
            elif scl_sync:
                self.cnt = int(i['clk_cnt']) & 0xffff
                clk_en = True
            elif self.cnt == 0:
                self.cnt = int(i['clk_cnt']) & 0xffff
                clk_en = True
            else:
                self.cnt = (self.cnt - 1) & 0xffff
                clk_en = False
            if enabled and clk_en:
                if self.state == 'IDLE':
                    c = int(i['cmd']) & 0xf
                    if c in (1, 2, 4, 8):
                        self.cmd_latched = c
                        self.din_latched = int(i['din']) & 1
                        self.state = {1: 'START_RELEASE', 2: 'STOP_SDA', 4: 'WRITE_SET', 8: 'READ_LOW'}[c]
                elif self.state == 'START_RELEASE':
                    self.state = 'START_SDA'
                elif self.state == 'START_SDA':
                    self.state = 'START_LOW'
                elif self.state == 'START_LOW':
                    self.state = 'IDLE'
                    self.cmd_ack_r = 1
                elif self.state == 'STOP_SDA':
                    self.state = 'STOP_SCL'
                elif self.state == 'STOP_SCL':
                    if self.sSCL:
                        self.state = 'STOP_RELEASE'
                elif self.state == 'STOP_RELEASE':
                    self.state = 'IDLE'
                    self.cmd_ack_r = 1
                elif self.state == 'READ_LOW':
                    self.state = 'READ_HIGH'
                elif self.state == 'READ_HIGH':
                    if self.sSCL:
                        self.state = 'READ_DONE'
                elif self.state == 'READ_DONE':
                    self.state = 'IDLE'
                    self.cmd_ack_r = 1
                elif self.state == 'WRITE_SET':
                    self.state = 'WRITE_HIGH'
                elif self.state == 'WRITE_HIGH':
                    if self.din_latched == 1 and self.sSDA == 0:
                        self.al_r = 1
                        self.state = 'IDLE'
                        self.scl_oen_r = 1
                        self.sda_oen_r = 1
                    elif self.sSCL:
                        self.state = 'WRITE_LOW'
                elif self.state == 'WRITE_LOW':
                    self.state = 'IDLE'
                    self.cmd_ack_r = 1
            if self.state != 'IDLE' and sto and self.cmd_latched != 2:
                self.al_r = 1
                self.state = 'IDLE'
                self.scl_oen_r = 1
                self.sda_oen_r = 1
            if scl_rise:
                self.dout_r = self.sSDA
            self._state_outputs()
            if self.al_r:
                self.state = 'IDLE'
                self.scl_oen_r = 1
                self.sda_oen_r = 1
            self._probes(expired, clk_en, released_scl_wait, scl_sync, scl_rise, sta, sto)
        o['cmd_ack'] = int(self.cmd_ack_r) & 1
        o['busy'] = int(self.busy_r) & 1
        o['al'] = int(self.al_r) & 1
        o['dout'] = int(self.dout_r) & 1
        o['scl_o'] = 0
        o['scl_oen'] = int(self.scl_oen_r) & 1
        o['sda_o'] = 0
        o['sda_oen'] = int(self.sda_oen_r) & 1
        return o
