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
    PROBE_PORTS = ['idle', 'clk_en', 'cnt_zero', 'slave_wait', 'scl_sync', 'cscl', 'csda', 'filter_cnt', 'fscl', 'fsda', 'sscl', 'ssda', 'dscl', 'dsda', 'sta_condition', 'sto_condition', 'active_command', 'sda_chk', 'start_sequence', 'stop_sequence', 'read_sequence', 'write_sequence', 'write_stable_high_phase', 'read_sample_window']
    LATENCY_CYCLES = 1

    def __init__(self):
        self.reset()


    def reset(self):
        self.state = 'IDLE'
        self.cmd_latched = 0
        self.din_latched = 0
        self.cSCL1 = 1
        self.cSCL2 = 1
        self.cSDA1 = 1
        self.cSDA2 = 1
        self.fSCL = [1, 1, 1]
        self.fSDA = [1, 1, 1]
        self.sSCL = 1
        self.sSDA = 1
        self.dSCL = 1
        self.dSDA = 1
        self.cnt = 0
        self.filter_counter = 0
        self.cmd_ack_r = 0
        self.busy_r = 0
        self.al_r = 0
        self.dout_r = 0
        self.clk_en_probe = 0
        self.cnt_zero_probe = 1
        self.filter_expired_probe = 0
        self.scl_sync_probe = 0
        self.sta_probe = 0
        self.sto_probe = 0
        self.slave_wait_probe = 0
        self._update_probes()


    def _reset_state(self, clk_cnt):
        self.state = 'IDLE'
        self.cmd_latched = 0
        self.din_latched = 0
        self.cSCL1 = 1
        self.cSCL2 = 1
        self.cSDA1 = 1
        self.cSDA2 = 1
        self.fSCL = [1, 1, 1]
        self.fSDA = [1, 1, 1]
        self.sSCL = 1
        self.sSDA = 1
        self.dSCL = 1
        self.dSDA = 1
        self.cnt = self.mask(clk_cnt, 16)
        self.filter_counter = 0
        self.cmd_ack_r = 0
        self.busy_r = 0
        self.al_r = 0
        self.dout_r = 0
        self.clk_en_probe = 0
        self.cnt_zero_probe = 1
        self.filter_expired_probe = 0
        self.scl_sync_probe = 0
        self.sta_probe = 0
        self.sto_probe = 0
        self.slave_wait_probe = 0


    def _outputs_for_state(self):
        scl = 1
        sda = 1
        if self.state in ('START_SDA', 'START_LOW'):
            sda = 0
        if self.state == 'START_LOW':
            scl = 0
        elif self.state in ('STOP_SDA', 'STOP_LOW'):
            scl = 0
            sda = 0
        elif self.state == 'STOP_HIGH':
            scl = 1
            sda = 0
        elif self.state == 'READ_LOW':
            scl = 0
            sda = 1
        elif self.state == 'READ_HIGH':
            scl = 1
            sda = 1
        elif self.state == 'WRITE_LOW':
            scl = 0
            sda = 0 if self.din_latched == 0 else 1
        elif self.state == 'WRITE_HIGH':
            scl = 1
            sda = 0 if self.din_latched == 0 else 1
        return scl, sda


    def _sample_filter(self, i, enabled):
        self.cSCL1 = int(i['scl_i']) & 1
        self.cSDA1 = int(i['sda_i']) & 1
        self.cSCL2 = self.cSCL1
        self.cSDA2 = self.cSDA1
        self.filter_expired_probe = 0
        if not enabled:
            self.filter_counter = 0
            return
        interval = int(i['clk_cnt']) >> 2
        if interval < 1:
            interval = 1
        if self.filter_counter <= 0:
            self.filter_expired_probe = 1
            self.fSCL = [self.fSCL[1], self.fSCL[2], self.cSCL2]
            self.fSDA = [self.fSDA[1], self.fSDA[2], self.cSDA2]
            old_scl = self.sSCL
            old_sda = self.sSDA
            self.sSCL = 1 if sum(self.fSCL) >= 2 else 0
            self.sSDA = 1 if sum(self.fSDA) >= 2 else 0
            self.dSCL = old_scl
            self.dSDA = old_sda
            self.filter_counter = interval - 1
        else:
            self.filter_counter -= 1


    def _timing(self, i, slave_wait):
        self.clk_en_probe = 0
        self.cnt_zero_probe = 0
        if not int(i['ena']):
            self.cnt = self.mask(i['clk_cnt'], 16)
            self.cnt_zero_probe = 1
            return
        if slave_wait:
            return
        if self.cnt == 0:
            self.clk_en_probe = 1
            self.cnt_zero_probe = 1
            self.cnt = self.mask(i['clk_cnt'], 16)
        else:
            self.cnt -= 1


    def _fsm(self, i):
        if not self.clk_en_probe or not int(i['ena']):
            return
        if self.state == 'IDLE':
            c = int(i['cmd']) & 15
            if c in (1, 2, 4, 8):
                self.cmd_latched = c
                self.din_latched = int(i['din']) & 1
                if c == 1:
                    self.state = 'START_SDA'
                elif c == 2:
                    self.state = 'STOP_SDA'
                elif c == 4:
                    self.state = 'WRITE_LOW'
                else:
                    self.state = 'READ_LOW'
        elif self.state == 'START_SDA':
            self.state = 'START_LOW'
        elif self.state == 'START_LOW':
            self.state = 'IDLE'
            self.cmd_ack_r = 1
        elif self.state == 'STOP_SDA':
            self.state = 'STOP_HIGH'
        elif self.state == 'STOP_HIGH':
            if self.sSCL:
                self.state = 'STOP_DONE'
        elif self.state == 'STOP_DONE':
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
        elif self.state == 'WRITE_LOW':
            self.state = 'WRITE_HIGH'
        elif self.state == 'WRITE_HIGH':
            self.state = 'WRITE_DONE'
        elif self.state == 'WRITE_DONE':
            self.state = 'IDLE'
            self.cmd_ack_r = 1


    def _events(self, i, old_scl, old_sda):
        self.sta_probe = int((not self.sSDA) and old_sda and self.sSCL)
        self.sto_probe = int(self.sSDA and (not old_sda) and self.sSCL)
        if self.sta_probe:
            self.busy_r = 1
        if self.sto_probe:
            self.busy_r = 0
        released_scl = self._outputs_for_state()[0] == 1
        released_sda = self._outputs_for_state()[1] == 1
        self.slave_wait_probe = int(released_scl and not self.sSCL)
        self.scl_sync_probe = int(released_scl and old_scl and not self.sSCL)
        if self.state == 'WRITE_HIGH' and self.din_latched and not self.sSDA:
            self.al_r = 1
        if self.sto_probe and self.state not in ('IDLE', 'STOP_SDA', 'STOP_HIGH', 'STOP_DONE'):
            self.al_r = 1
        if self.al_r:
            self.state = 'IDLE'
            self.cmd_ack_r = 0


    def _update_probes(self):
        self.idle = int(self.state == 'IDLE')
        self.clk_en = int(bool(self.clk_en_probe))
        self.cnt_zero = int(bool(self.cnt_zero_probe))
        self.slave_wait = int(bool(self.slave_wait_probe))
        self.scl_sync = int(bool(self.scl_sync_probe))
        self.cscl = int(self.cSCL2)
        self.csda = int(self.cSDA2)
        self.filter_cnt = int(bool(self.filter_expired_probe))
        self.fscl = int(bool(self.filter_expired_probe))
        self.fsda = int(bool(self.filter_expired_probe))
        self.sscl = int(self.sSCL)
        self.ssda = int(self.sSDA)
        self.dscl = int(self.dSCL)
        self.dsda = int(self.dSDA)
        self.sta_condition = int(bool(self.sta_probe))
        self.sto_condition = int(bool(self.sto_probe))
        self.active_command = int(self.state != 'IDLE')
        self.sda_chk = int(self.state == 'WRITE_HIGH' and self.din_latched)
        self.start_sequence = int(self.state in ('START_SDA', 'START_LOW'))
        self.stop_sequence = int(self.state in ('STOP_SDA', 'STOP_HIGH', 'STOP_DONE'))
        self.read_sequence = int(self.state in ('READ_LOW', 'READ_HIGH', 'READ_DONE'))
        self.write_sequence = int(self.state in ('WRITE_LOW', 'WRITE_HIGH', 'WRITE_DONE'))
        self.write_stable_high_phase = int(self.state == 'WRITE_HIGH')
        self.read_sample_window = int(self.state == 'READ_HIGH')


    def step(self, i):
        o = {p: None for p in self.OUTPUT_PORTS}
        if not int(i.get('nReset', 1)):
            self._reset_state(i.get('clk_cnt', 0))
        elif int(i.get('rst', 0)):
            self._reset_state(i.get('clk_cnt', 0))
        else:
            self.cmd_ack_r = 0
            old_scl = self.sSCL
            old_sda = self.sSDA
            self._sample_filter(i, bool(i.get('ena', 0)))
            scl_req, sda_req = self._outputs_for_state()
            wait = bool(scl_req and not self.sSCL and self.state != 'IDLE')
            self.slave_wait_probe = int(wait)
            self._timing(i, wait)
            self._events(i, old_scl, old_sda)
            self._fsm(i)
            if self.state == 'READ_HIGH' and old_scl == 0 and self.sSCL == 1:
                self.dout_r = int(self.sSDA)
            if self.scl_sync_probe:
                self.cnt = self.mask(i['clk_cnt'], 16)
            self._update_probes()
        scl_oen, sda_oen = self._outputs_for_state()
        o['cmd_ack'] = int(self.cmd_ack_r)
        o['busy'] = int(self.busy_r)
        o['al'] = int(self.al_r)
        o['dout'] = int(self.dout_r)
        o['scl_o'] = 0
        o['scl_oen'] = int(scl_oen)
        o['sda_o'] = 0
        o['sda_oen'] = int(sda_oen)
        return o
