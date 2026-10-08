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
        self.state = 'IDLE'
        self.phase = 0
        self.cmd_latched = 0
        self.din_latched = 0
        self.cnt = 0
        self.filter_counter = 0
        self.cSCL = 1
        self.cSDA = 1
        self.fSCL = [1, 1, 1]
        self.fSDA = [1, 1, 1]
        self.sSCL = 1
        self.sSDA = 1
        self.dSCL = 1
        self.dSDA = 1
        self.cmd_ack_r = 0
        self.busy_r = 0
        self.al_r = 0
        self.dout_r = 0
        self.scl_oen_r = 1
        self.sda_oen_r = 1
        self._update_probes()


    def _majority(self, values):
        return int(sum(int(x) for x in values) >= 2)


    def _update_probes(self, clk_en=0, slave_wait=0, scl_sync=0,
                       filter_expired=0, sta=0, sto=0, rise=0,
                       cnt_zero=0):
        self.idle = self.state == 'IDLE'
        self.cnt_zero = bool(cnt_zero)
        self.clk_en = bool(clk_en)
        self.slave_wait = bool(slave_wait)
        self.scl_sync = bool(scl_sync)
        self.cscl = bool(self.cSCL)
        self.csda = bool(self.cSDA)
        self.filter_cnt = bool(self.filter_counter)
        self.filter_cnt_expired = bool(filter_expired)
        self.fscl = bool(self._majority(self.fSCL))
        self.fsda = bool(self._majority(self.fSDA))
        self.sscl = bool(self.sSCL)
        self.ssda = bool(self.sSDA)
        self.dscl = bool(self.dSCL)
        self.dsda = bool(self.dSDA)
        self.sta_condition = bool(sta)
        self.sto_condition = bool(sto)
        self.active_command = self.state != 'IDLE'
        self.sda_chk = bool(self.state == 'WRITE' and self.phase == 2 and self.din_latched)
        self.filtered_scl_rise = bool(rise)
        self.start_sequence = self.state == 'START'
        self.stop_sequence = self.state == 'STOP'
        self.read_sequence = self.state == 'READ'
        self.write_sequence = self.state == 'WRITE'


    def _reset_state(self):
        self.state = 'IDLE'
        self.phase = 0
        self.cmd_latched = 0
        self.din_latched = 0
        self.cnt = 0
        self.filter_counter = 0
        self.cSCL = 1
        self.cSDA = 1
        self.fSCL = [1, 1, 1]
        self.fSDA = [1, 1, 1]
        self.sSCL = 1
        self.sSDA = 1
        self.dSCL = 1
        self.dSDA = 1
        self.cmd_ack_r = 0
        self.busy_r = 0
        self.al_r = 0
        self.dout_r = 0
        self.scl_oen_r = 1
        self.sda_oen_r = 1


    def _update_filter(self, i):
        old_scl = self.sSCL
        old_sda = self.sSDA
        self.cSCL = int(i['scl_i']) & 1
        self.cSDA = int(i['sda_i']) & 1
        expired = 0
        if not (int(i['ena']) & 1):
            self.filter_counter = 0
        else:
            interval = ((int(i['clk_cnt']) & 0xffff) >> 2)
            if interval == 0 or self.filter_counter == 0:
                expired = 1
                self.filter_counter = interval
                self.fSCL = [self.fSCL[1], self.fSCL[2], self.cSCL]
                self.fSDA = [self.fSDA[1], self.fSDA[2], self.cSDA]
            else:
                self.filter_counter = (self.filter_counter - 1) & 0xffff
        self.dSCL = old_scl
        self.dSDA = old_sda
        self.sSCL = self._majority(self.fSCL)
        self.sSDA = self._majority(self.fSDA)
        scl_fall = int(old_scl and not self.sSCL)
        scl_rise = int((not old_scl) and self.sSCL)
        sta = int((not self.sSDA) and old_sda and self.sSCL)
        sto = int(self.sSDA and (not old_sda) and self.sSCL)
        return expired, scl_fall, scl_rise, sta, sto


    def _update_divider(self, i, slave_wait, scl_sync):
        reload_value = int(i['clk_cnt']) & 0xffff
        if not (int(i['ena']) & 1):
            self.cnt = reload_value
            return 0
        if slave_wait:
            return 0
        if scl_sync or self.cnt == 0:
            self.cnt = reload_value
            return 1
        self.cnt = (self.cnt - 1) & 0xffff
        return 0


    def _fsm_outputs(self):
        scl = 1
        sda = 1
        if self.state == 'START':
            sda = 0 if self.phase >= 1 else 1
            scl = 0 if self.phase >= 2 else 1
        elif self.state == 'STOP':
            sda = 0 if self.phase < 2 else 1
            scl = 0 if self.phase == 0 else 1
        elif self.state == 'READ':
            sda = 1
            scl = 1 if self.phase == 1 else 0
        elif self.state == 'WRITE':
            sda = 0 if self.din_latched == 0 else 1
            scl = 1 if self.phase in (1, 2) else 0
        return scl, sda


    def _advance_fsm(self, i, clk_en, sto):
        self.cmd_ack_r = 0
        if self.state != 'IDLE' and sto and self.state != 'STOP':
            self.al_r = 1
            self.state = 'IDLE'
            self.phase = 0
            self.scl_oen_r = 1
            self.sda_oen_r = 1
            return
        if self.state == 'WRITE' and self.phase == 2 and self.din_latched and not self.sSDA:
            self.al_r = 1
            self.state = 'IDLE'
            self.phase = 0
            self.scl_oen_r = 1
            self.sda_oen_r = 1
            return
        if not clk_en or not (int(i['ena']) & 1):
            return
        if self.state == 'IDLE':
            command = int(i['cmd']) & 0xf
            if command in (1, 2, 4, 8):
                self.cmd_latched = command
                self.din_latched = int(i['din']) & 1
                self.phase = 0
                self.state = {1: 'START', 2: 'STOP', 4: 'WRITE', 8: 'READ'}[command]
        elif self.state == 'START':
            if self.phase < 2:
                self.phase += 1
            else:
                self.state = 'IDLE'
                self.phase = 0
                self.cmd_ack_r = 1
        elif self.state == 'STOP':
            if self.phase == 0:
                self.phase = 1
            elif self.phase == 1:
                if self.sSCL:
                    self.phase = 2
            else:
                self.state = 'IDLE'
                self.phase = 0
                self.cmd_ack_r = 1
        elif self.state == 'READ':
            if self.phase == 0:
                self.phase = 1
            elif self.phase == 1:
                if self.sSCL:
                    self.phase = 2
            else:
                self.state = 'IDLE'
                self.phase = 0
                self.cmd_ack_r = 1
        elif self.state == 'WRITE':
            if self.phase < 3:
                if self.phase == 1 and not self.sSCL:
                    return
                self.phase += 1
            else:
                self.state = 'IDLE'
                self.phase = 0
                self.cmd_ack_r = 1


    def step(self, i):
        o = {p: None for p in self.OUTPUT_PORTS}
        if not (int(i['nReset']) & 1):
            self._reset_state()
            self._update_probes(cnt_zero=1)
        elif int(i['rst']) & 1:
            self._reset_state()
            self._update_probes(cnt_zero=1)
        else:
            expired, scl_fall, scl_rise, sta, sto = self._update_filter(i)
            slave_wait = int(self.scl_oen_r and not self.sSCL)
            scl_sync = int(self.scl_oen_r and scl_fall)
            clk_en = self._update_divider(i, slave_wait, scl_sync)
            if scl_rise:
                self.dout_r = self.sSDA & 1
            if sta:
                self.busy_r = 1
            if sto:
                self.busy_r = 0
            self._advance_fsm(i, clk_en, sto)
            if self.al_r:
                self.scl_oen_r = 1
                self.sda_oen_r = 1
            else:
                self.scl_oen_r, self.sda_oen_r = self._fsm_outputs()
            self._update_probes(
                clk_en=clk_en,
                slave_wait=slave_wait,
                scl_sync=scl_sync,
                filter_expired=expired,
                sta=sta,
                sto=sto,
                rise=scl_rise,
                cnt_zero=int(self.cnt == 0),
            )
        o['cmd_ack'] = self.cmd_ack_r & 1
        o['busy'] = self.busy_r & 1
        o['al'] = self.al_r & 1
        o['dout'] = self.dout_r & 1
        o['scl_o'] = 0
        o['scl_oen'] = self.scl_oen_r & 1
        o['sda_o'] = 0
        o['sda_oen'] = self.sda_oen_r & 1
        return o
