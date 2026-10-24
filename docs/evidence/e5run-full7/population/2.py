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
        self.cSCL1 = self.cSCL = 1
        self.cSDA1 = self.cSDA = 1
        self.fSCL = [1, 1, 1]
        self.fSDA = [1, 1, 1]
        self.sSCL = self.sSDA = 1
        self.dSCL = self.dSDA = 1
        self.cnt = 0
        self.filter_counter = 0
        self.busy_reg = 0
        self.al_reg = 0
        self.dout_reg = 0
        self.ack_reg = 0
        self.scl_oen_reg = 1
        self.sda_oen_reg = 1
        self._set_probes(0, 0, 0, 0, 1, 1, 0, 0, 0, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)


    def _set_probes(self, clk_en, cnt_zero, slave_wait, scl_sync, cscl, csda,
                    filter_cnt, fscl, fsda, sscl, ssda, dscl, dsda,
                    sta, sto, active, sda_chk, start, stop, read, write,
                    write_high, read_window, unused=0):
        self.idle = self.state == 'IDLE'
        self.clk_en = bool(clk_en)
        self.cnt_zero = bool(cnt_zero)
        self.slave_wait = bool(slave_wait)
        self.scl_sync = bool(scl_sync)
        self.cscl = bool(cscl)
        self.csda = bool(csda)
        self.filter_cnt = bool(filter_cnt)
        self.fscl = bool(fscl)
        self.fsda = bool(fsda)
        self.sscl = bool(sscl)
        self.ssda = bool(ssda)
        self.dscl = bool(dscl)
        self.dsda = bool(dsda)
        self.sta_condition = bool(sta)
        self.sto_condition = bool(sto)
        self.active_command = bool(active)
        self.sda_chk = bool(sda_chk)
        self.start_sequence = bool(start)
        self.stop_sequence = bool(stop)
        self.read_sequence = bool(read)
        self.write_sequence = bool(write)
        self.write_stable_high_phase = bool(write_high)
        self.read_sample_window = bool(read_window)


    def _reset_outputs(self, clk_cnt=0):
        self.state = 'IDLE'
        self.cmd_latched = 0
        self.din_latched = 0
        self.ack_reg = 0
        self.busy_reg = 0
        self.al_reg = 0
        self.dout_reg = 0
        self.scl_oen_reg = 1
        self.sda_oen_reg = 1
        self.cnt = int(clk_cnt) & 0xffff
        self.filter_counter = 0
        self.cSCL1 = self.cSCL = 1
        self.cSDA1 = self.cSDA = 1
        self.fSCL = [1, 1, 1]
        self.fSDA = [1, 1, 1]
        self.sSCL = self.sSDA = 1
        self.dSCL = self.dSDA = 1


    def _filter_inputs(self, i, ena):
        old_scl = self.sSCL
        old_sda = self.sSDA
        self.cSCL1 = int(i['scl_i']) & 1
        self.cSCL = self.cSCL1
        self.cSDA1 = int(i['sda_i']) & 1
        self.cSDA = self.cSDA1
        sampled = False
        if ena:
            interval = ((int(i['clk_cnt']) & 0xffff) >> 2)
            if self.filter_counter == 0:
                sampled = True
                self.filter_counter = interval
                self.fSCL = [self.fSCL[1], self.fSCL[2], self.cSCL]
                self.fSDA = [self.fSDA[1], self.fSDA[2], self.cSDA]
                self.sSCL = int(sum(self.fSCL) >= 2)
                self.sSDA = int(sum(self.fSDA) >= 2)
            else:
                self.filter_counter -= 1
        else:
            self.filter_counter = 0
        self.dSCL = old_scl
        self.dSDA = old_sda
        sta = (not self.sSDA) and bool(self.dSDA) and bool(self.sSCL)
        sto = bool(self.sSDA) and (not self.dSDA) and bool(self.sSCL)
        return sampled, sta, sto, old_scl


    def _timing(self, i, ena, slave_wait, scl_sync):
        reload_value = int(i['clk_cnt']) & 0xffff
        if not ena:
            self.cnt = reload_value
            return 0, True
        if slave_wait:
            return 0, False
        if scl_sync or self.cnt == 0:
            self.cnt = reload_value
            return 1, True
        self.cnt = (self.cnt - 1) & 0xffff
        return 0, False


    def _outputs_for_state(self):
        scl = 1
        sda = 1
        if self.state.startswith('START'):
            phase = int(self.state[-1])
            if phase == 1:
                sda = 0
            elif phase == 2:
                scl = 0
                sda = 0
        elif self.state.startswith('STOP'):
            phase = int(self.state[-1])
            if phase == 0:
                scl = 0
                sda = 0
            elif phase == 1:
                sda = 0
        elif self.state.startswith('READ'):
            phase = int(self.state[-1])
            if phase in (0, 2):
                scl = 0
        elif self.state.startswith('WRITE'):
            phase = int(self.state[-1])
            sda = 0 if self.din_latched == 0 else 1
            if phase in (0, 2):
                scl = 0
        self.scl_oen_reg = scl
        self.sda_oen_reg = sda


    def _finish(self):
        self.state = 'IDLE'
        self.scl_oen_reg = 1
        self.sda_oen_reg = 1
        self.ack_reg = 1


    def _advance_fsm(self, i, tick, sto, slave_wait):
        if not tick or slave_wait or self.al_reg:
            return
        if self.state == 'IDLE':
            cmd = int(i['cmd']) & 0xf
            if cmd in (1, 2, 4, 8):
                self.cmd_latched = cmd
                self.din_latched = int(i['din']) & 1
                self.state = {1: 'START0', 2: 'STOP0', 4: 'WRITE0', 8: 'READ0'}[cmd]
                self._outputs_for_state()
            return
        if self.state.startswith('WRITE') and self.state.endswith('1'):
            if self.din_latched and not self.sSDA:
                self.al_reg = 1
                self.state = 'IDLE'
                self.scl_oen_reg = 1
                self.sda_oen_reg = 1
                return
        if sto and not self.state.startswith('STOP'):
            self.al_reg = 1
            self.state = 'IDLE'
            self.scl_oen_reg = 1
            self.sda_oen_reg = 1
            return
        if self.state == 'START0':
            self.state = 'START1'
        elif self.state == 'START1':
            self.state = 'START2'
        elif self.state == 'START2':
            self._finish()
        elif self.state == 'STOP0':
            self.state = 'STOP1'
        elif self.state == 'STOP1':
            if self.sSCL:
                self.state = 'STOP2'
        elif self.state == 'STOP2':
            self.busy_reg = 0
            self._finish()
        elif self.state == 'READ0':
            self.state = 'READ1'
        elif self.state == 'READ1':
            if self.sSCL:
                self.state = 'READ2'
        elif self.state == 'READ2':
            self._finish()
        elif self.state == 'WRITE0':
            self.state = 'WRITE1'
        elif self.state == 'WRITE1':
            if self.sSCL:
                self.state = 'WRITE2'
        elif self.state == 'WRITE2':
            self._finish()
        self._outputs_for_state()


    def step(self, i):
        o = {p: None for p in self.OUTPUT_PORTS}
        if int(i.get('nReset', 1)) == 0:
            self._reset_outputs()
            self._set_probes(0, 0, 0, 0, 1, 1, 0, 0, 0, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
        elif int(i.get('rst', 0)):
            self._reset_outputs()
            self._set_probes(0, 0, 0, 0, 1, 1, 0, 0, 0, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
        else:
            self.ack_reg = 0
            ena = int(i.get('ena', 0)) & 1
            sampled, sta, sto, old_scl = self._filter_inputs(i, ena)
            released_scl = bool(self.scl_oen_reg)
            slave_wait = released_scl and not bool(self.sSCL)
            scl_sync = released_scl and bool(old_scl) and not bool(self.sSCL)
            tick, cnt_zero = self._timing(i, ena, slave_wait, scl_sync)
            if sta:
                self.busy_reg = 1
            if sto:
                self.busy_reg = 0
            if sampled and old_scl == 0 and self.sSCL == 1:
                self.dout_reg = self.sSDA
            if ena:
                self._advance_fsm(i, tick, sto, slave_wait)
            elif self.state == 'IDLE':
                self.scl_oen_reg = 1
                self.sda_oen_reg = 1
            self._outputs_for_state()
            active = self.state != 'IDLE'
            write = self.state.startswith('WRITE')
            start = self.state.startswith('START')
            stop = self.state.startswith('STOP')
            read = self.state.startswith('READ')
            phase = self.state[-1] if active else '-'
            write_high = write and phase == '1'
            read_window = read and phase == '1'
            sda_chk = write_high and bool(self.din_latched)
            self._set_probes(tick, cnt_zero, slave_wait, scl_sync,
                             self.cSCL, self.cSDA, sampled, sampled, sampled,
                             self.sSCL, self.sSDA, self.dSCL, self.dSDA,
                             sta, sto, active, sda_chk, start, stop, read, write,
                             write_high, read_window)
        o['cmd_ack'] = int(self.ack_reg) & 1
        o['busy'] = int(self.busy_reg) & 1
        o['al'] = int(self.al_reg) & 1
        o['dout'] = int(self.dout_reg) & 1
        o['scl_o'] = 0
        o['scl_oen'] = int(self.scl_oen_reg) & 1
        o['sda_o'] = 0
        o['sda_oen'] = int(self.sda_oen_reg) & 1
        return o
