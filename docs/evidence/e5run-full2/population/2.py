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
        self.cmd_ack_reg = 0
        self.busy_reg = 0
        self.al_reg = 0
        self.dout_reg = 0
        self.scl_oen_reg = 1
        self.sda_oen_reg = 1
        self._set_probes(False, False, False, False, False, True, True,
                         False, False, True, True, True, True, True, True,
                         False, False, False, False, False, False, False,
                         False, False)


    def _majority(self, h):
        return 1 if (h[0] + h[1] + h[2]) >= 2 else 0


    def _set_probes(self, idle, cnt_zero, clk_en, slave_wait, scl_sync,
                    cscl, csda, filter_cnt, filter_cnt_expired, fscl, fsda,
                    sscl, ssda, dscl, dsda, sta_condition, sto_condition,
                    active_command, sda_chk, filtered_scl_rise, start_sequence,
                    stop_sequence, read_sequence, write_sequence):
        self.idle = bool(idle)
        self.cnt_zero = bool(cnt_zero)
        self.clk_en = bool(clk_en)
        self.slave_wait = bool(slave_wait)
        self.scl_sync = bool(scl_sync)
        self.cscl = bool(cscl)
        self.csda = bool(csda)
        self.filter_cnt = bool(filter_cnt)
        self.filter_cnt_expired = bool(filter_cnt_expired)
        self.fscl = bool(fscl)
        self.fsda = bool(fsda)
        self.sscl = bool(sscl)
        self.ssda = bool(ssda)
        self.dscl = bool(dscl)
        self.dsda = bool(dsda)
        self.sta_condition = bool(sta_condition)
        self.sto_condition = bool(sto_condition)
        self.active_command = bool(active_command)
        self.sda_chk = bool(sda_chk)
        self.filtered_scl_rise = bool(filtered_scl_rise)
        self.start_sequence = bool(start_sequence)
        self.stop_sequence = bool(stop_sequence)
        self.read_sequence = bool(read_sequence)
        self.write_sequence = bool(write_sequence)


    def _outputs_for_state(self):
        scl = 1
        sda = 1
        if self.state in ('START_SDA', 'START_LOW', 'STOP_SDA', 'WRITE_LOW'):
            sda = 0
        if self.state in ('START_LOW', 'READ_LOW', 'WRITE_LOW'):
            scl = 0
        if self.state == 'STOP_SDA':
            scl = 0
        if self.state == 'STOP_RELEASE_SDA':
            scl = 1
            sda = 1
        if self.state == 'READ_HIGH':
            scl = 1
            sda = 1
        if self.state == 'WRITE_HIGH':
            scl = 1
            sda = 0 if self.din_latched == 0 else 1
        if self.state == 'WRITE_LOW_DONE':
            scl = 0
            sda = 0 if self.din_latched == 0 else 1
        return scl, sda


    def _filter_and_events(self, i):
        old_scl = self.sSCL
        old_sda = self.sSDA
        self.cSCL1 = int(i.get('scl_i', 1)) & 1
        self.cSDA1 = int(i.get('sda_i', 1)) & 1
        self.cSCL2 = self.cSCL1
        self.cSDA2 = self.cSDA1
        enabled = bool(i.get('ena', 0))
        interval = ((int(i.get('clk_cnt', 0)) & 0xffff) >> 2)
        expired = False
        if not enabled:
            self.filter_counter = 0
        elif interval == 0:
            expired = True
            self.filter_counter = 0
        elif self.filter_counter == 0:
            expired = True
            self.filter_counter = interval
        else:
            self.filter_counter = (self.filter_counter - 1) & 0xffff
        if expired:
            self.fSCL = [self.fSCL[1], self.fSCL[2], self.cSCL2]
            self.fSDA = [self.fSDA[1], self.fSDA[2], self.cSDA2]
            self.sSCL = self._majority(self.fSCL)
            self.sSDA = self._majority(self.fSDA)
        self.dSCL = old_scl
        self.dSDA = old_sda
        sta = bool((not self.sSDA) and self.dSDA and self.sSCL)
        sto = bool(self.sSDA and (not self.dSDA) and self.sSCL)
        rise = bool(self.sSCL and not self.dSCL)
        return expired, sta, sto, rise, old_scl


    def _timing(self, i, slave_wait, scl_sync):
        ena = bool(i.get('ena', 0))
        reload_value = int(i.get('clk_cnt', 0)) & 0xffff
        if not ena:
            self.cnt = reload_value
            return False, self.cnt == 0
        if slave_wait:
            return False, self.cnt == 0
        if scl_sync or self.cnt == 0:
            self.cnt = reload_value
            return True, True
        self.cnt = (self.cnt - 1) & 0xffff
        return False, False


    def _fsm(self, i, tick, sto, sta):
        self.cmd_ack_reg = 0
        if self.al_reg:
            self.state = 'IDLE'
            self.scl_oen_reg = 1
            self.sda_oen_reg = 1
            return
        if self.state == 'IDLE':
            if tick and bool(i.get('ena', 0)):
                cmd = int(i.get('cmd', 0)) & 0xf
                if cmd in (1, 2, 4, 8):
                    self.cmd_latched = cmd
                    self.din_latched = int(i.get('din', 0)) & 1
                    if cmd == 1:
                        self.state = 'START_RELEASE'
                    elif cmd == 2:
                        self.state = 'STOP_SDA'
                    elif cmd == 4:
                        self.state = 'WRITE_LOW'
                    else:
                        self.state = 'READ_LOW'
        elif tick:
            if self.state == 'START_RELEASE':
                self.state = 'START_SDA'
            elif self.state == 'START_SDA':
                self.state = 'START_LOW'
            elif self.state == 'START_LOW':
                self.state = 'IDLE'
                self.cmd_ack_reg = 1
            elif self.state == 'STOP_SDA':
                self.state = 'STOP_RELEASE_SCL'
            elif self.state == 'STOP_RELEASE_SCL':
                if self.sSCL:
                    self.state = 'STOP_RELEASE_SDA'
            elif self.state == 'STOP_RELEASE_SDA':
                self.state = 'IDLE'
                self.cmd_ack_reg = 1
            elif self.state == 'READ_LOW':
                self.state = 'READ_HIGH'
            elif self.state == 'READ_HIGH':
                self.state = 'READ_LOW_DONE'
            elif self.state == 'READ_LOW_DONE':
                self.state = 'IDLE'
                self.cmd_ack_reg = 1
            elif self.state == 'WRITE_LOW':
                self.state = 'WRITE_HIGH'
            elif self.state == 'WRITE_HIGH':
                self.state = 'WRITE_LOW_DONE'
            elif self.state == 'WRITE_LOW_DONE':
                self.state = 'IDLE'
                self.cmd_ack_reg = 1
        if self.state == 'IDLE':
            self.scl_oen_reg = 1
            self.sda_oen_reg = 1
        else:
            scl, sda = self._outputs_for_state()
            self.scl_oen_reg = scl
            self.sda_oen_reg = sda
        if sta:
            self.busy_reg = 1
        if sto:
            self.busy_reg = 0


    def _arbitration(self, sto):
        active = self.state != 'IDLE'
        sda_chk = self.state == 'WRITE_HIGH' and self.din_latched == 1
        lost = bool((sda_chk and self.sSDA == 0) or
                    (sto and active and self.cmd_latched != 2))
        if lost:
            self.al_reg = 1
            self.state = 'IDLE'
            self.scl_oen_reg = 1
            self.sda_oen_reg = 1
        return sda_chk, lost


    def _update_probes(self, cnt_zero, clk_en, slave_wait, scl_sync,
                       filter_expired, sta, sto, rise, sda_chk):
        self._set_probes(
            self.state == 'IDLE', cnt_zero, clk_en, slave_wait, scl_sync,
            self.cSCL2, self.cSDA2, self.filter_counter != 0, filter_expired,
            self._majority(self.fSCL), self._majority(self.fSDA),
            self.sSCL, self.sSDA, self.dSCL, self.dSDA, sta, sto,
            self.state != 'IDLE', sda_chk, rise,
            self.state.startswith('START'), self.state.startswith('STOP'),
            self.state.startswith('READ'), self.state.startswith('WRITE'))


    def step(self, i):
        o = {p: None for p in self.OUTPUT_PORTS}
        if not bool(i.get('nReset', 1)):
            self.reset()
        elif bool(i.get('rst', 0)):
            self.reset()
        else:
            filter_expired, sta, sto, rise, old_scl = self._filter_and_events(i)
            if rise:
                self.dout_reg = self.sSDA
            released_scl = self.scl_oen_reg == 1
            slave_wait = bool(released_scl and not self.sSCL)
            scl_sync = bool(released_scl and old_scl and not self.sSCL)
            clk_en, cnt_zero = self._timing(i, slave_wait, scl_sync)
            if not bool(i.get('ena', 0)):
                clk_en = False
            self._fsm(i, clk_en, sto, sta)
            sda_chk, _ = self._arbitration(sto)
            self._update_probes(cnt_zero, clk_en, slave_wait, scl_sync,
                                filter_expired, sta, sto, rise, sda_chk)
        o['cmd_ack'] = int(self.cmd_ack_reg) & 1
        o['busy'] = int(self.busy_reg) & 1
        o['al'] = int(self.al_reg) & 1
        o['dout'] = int(self.dout_reg) & 1
        o['scl_o'] = 0
        o['scl_oen'] = int(self.scl_oen_reg) & 1
        o['sda_o'] = 0
        o['sda_oen'] = int(self.sda_oen_reg) & 1
        return o
