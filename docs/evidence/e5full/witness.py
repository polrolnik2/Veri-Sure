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
        self.scl_oen_reg = 1
        self.sda_oen_reg = 1
        self.cmd_ack_reg = 0
        self.busy_reg = 0
        self.al_reg = 0
        self.dout_reg = 0
        self._set_probes(False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, True)


    def _set_probes(self, cscl, csda, sscl, ssda, dscl, dsda, fscl, fsda,
                    filter_cnt, cnt_zero, clk_en, slave_wait, scl_sync,
                    sta_condition, sto_condition, sda_chk, idle, fsm_active,
                    start_sequence, stop_sequence, read_sequence, write_sequence,
                    filtered_scl_rising, filtered_scl_falling,
                    controller_probe):
        self.cscl = bool(cscl)
        self.csda = bool(csda)
        self.sscl = bool(sscl)
        self.ssda = bool(ssda)
        self.dscl = bool(dscl)
        self.dsda = bool(dsda)
        self.fscl = bool(fscl)
        self.fsda = bool(fsda)
        self.filter_cnt = bool(filter_cnt)
        self.cnt_zero = bool(cnt_zero)
        self.clk_en = bool(clk_en)
        self.slave_wait = bool(slave_wait)
        self.scl_sync = bool(scl_sync)
        self.sta_condition = bool(sta_condition)
        self.sto_condition = bool(sto_condition)
        self.sda_chk = bool(sda_chk)
        self.idle = bool(idle)
        self.fsm_active = bool(fsm_active)
        self.start_sequence = bool(start_sequence)
        self.stop_sequence = bool(stop_sequence)
        self.read_sequence = bool(read_sequence)
        self.write_sequence = bool(write_sequence)
        self.filtered_scl_rising = bool(filtered_scl_rising)
        self.filtered_scl_falling = bool(filtered_scl_falling)
        self.i2c_master_bit_ctrl = bool(controller_probe)


    def _majority(self, history):
        return 1 if (history[0] + history[1] + history[2]) >= 2 else 0


    def _update_inputs(self, i, enabled):
        old_scl = self.sSCL
        old_sda = self.sSDA
        self.cSCL1 = int(i['scl_i']) & 1
        self.cSDA1 = int(i['sda_i']) & 1
        self.cSCL2 = self.cSCL1
        self.cSDA2 = self.cSDA1
        sample = False
        interval = (int(i['clk_cnt']) & 0xffff) >> 2
        if not enabled:
            self.filter_counter = 0
        elif interval == 0:
            sample = True
            self.filter_counter = 0
        elif self.filter_counter == 0:
            sample = True
            self.filter_counter = interval
        else:
            self.filter_counter -= 1
        if sample and enabled:
            self.fSCL = [self.fSCL[1], self.fSCL[2], self.cSCL2]
            self.fSDA = [self.fSDA[1], self.fSDA[2], self.cSDA2]
            self.dSCL = self.sSCL
            self.dSDA = self.sSDA
            self.sSCL = self._majority(self.fSCL)
            self.sSDA = self._majority(self.fSDA)
        rising = (not old_scl) and bool(self.sSCL)
        falling = bool(old_scl) and (not self.sSCL)
        sta = (not self.sSDA) and bool(self.dSDA) and bool(self.sSCL)
        sto = bool(self.sSDA) and (not self.dSDA) and bool(self.sSCL)
        return sample, rising, falling, sta, sto


    def _line_outputs(self):
        if self.state == 'IDLE':
            self.scl_oen_reg = 1
            self.sda_oen_reg = 1
        elif self.state == 'START0':
            self.scl_oen_reg = 1
            self.sda_oen_reg = 1
        elif self.state == 'START1':
            self.scl_oen_reg = 1
            self.sda_oen_reg = 0
        elif self.state == 'START2':
            self.scl_oen_reg = 0
            self.sda_oen_reg = 0
        elif self.state == 'STOP0':
            self.scl_oen_reg = 0
            self.sda_oen_reg = 0
        elif self.state == 'STOP1':
            self.scl_oen_reg = 1
            self.sda_oen_reg = 0
        elif self.state == 'STOP2':
            self.scl_oen_reg = 1
            self.sda_oen_reg = 1
        elif self.state == 'READ0':
            self.scl_oen_reg = 0
            self.sda_oen_reg = 1
        elif self.state == 'READ1':
            self.scl_oen_reg = 1
            self.sda_oen_reg = 1
        elif self.state == 'READ2':
            self.scl_oen_reg = 0
            self.sda_oen_reg = 1
        elif self.state == 'WRITE0':
            self.scl_oen_reg = 0
            self.sda_oen_reg = 0 if self.din_latched == 0 else 1
        elif self.state == 'WRITE1':
            self.scl_oen_reg = 1
            self.sda_oen_reg = 0 if self.din_latched == 0 else 1
        elif self.state == 'WRITE2':
            self.scl_oen_reg = 0
            self.sda_oen_reg = 0 if self.din_latched == 0 else 1


    def _advance_fsm(self, clk_en, sta, sto):
        if sto and self.state != 'IDLE' and self.cmd_latched != 2:
            self.al_reg = 1
            self.state = 'IDLE'
            self.scl_oen_reg = 1
            self.sda_oen_reg = 1
            return
        if self.al_reg:
            self.state = 'IDLE'
            self.scl_oen_reg = 1
            self.sda_oen_reg = 1
            return
        if not clk_en:
            return
        if self.state == 'IDLE':
            command = int(self._current_cmd) & 0xf
            if command in (1, 2, 4, 8):
                self.cmd_latched = command
                self.din_latched = int(self._current_din) & 1
                self.state = {1: 'START0', 2: 'STOP0', 4: 'WRITE0', 8: 'READ0'}[command]
        elif self.state == 'START0':
            self.state = 'START1'
        elif self.state == 'START1':
            self.state = 'START2'
        elif self.state == 'START2':
            self.state = 'IDLE'
            self.cmd_ack_reg = 1
        elif self.state == 'STOP0':
            self.state = 'STOP1'
        elif self.state == 'STOP1':
            if self.sSCL:
                self.state = 'STOP2'
        elif self.state == 'STOP2':
            self.state = 'IDLE'
            self.cmd_ack_reg = 1
        elif self.state == 'READ0':
            self.state = 'READ1'
        elif self.state == 'READ1':
            if self.sSCL:
                self.state = 'READ2'
        elif self.state == 'READ2':
            self.state = 'IDLE'
            self.cmd_ack_reg = 1
        elif self.state == 'WRITE0':
            self.state = 'WRITE1'
        elif self.state == 'WRITE1':
            if self.sSCL:
                self.state = 'WRITE2'
        elif self.state == 'WRITE2':
            self.state = 'IDLE'
            self.cmd_ack_reg = 1


    def step(self, i):
        o = {p: None for p in self.OUTPUT_PORTS}
        if int(i.get('nReset', 1)) == 0:
            self.reset()
        elif int(i.get('rst', 0)):
            self.reset()
        else:
            self.cmd_ack_reg = 0
            enabled = bool(int(i.get('ena', 0)) & 1)
            _, rising, falling, sta, sto = self._update_inputs(i, enabled)
            released_scl = bool(self.scl_oen_reg)
            released_sda = bool(self.sda_oen_reg)
            slave_wait = released_scl and (not bool(self.sSCL)) and self.state != 'IDLE'
            scl_sync = released_scl and falling
            if sta:
                self.busy_reg = 1
            if sto:
                self.busy_reg = 0
            if rising:
                self.dout_reg = int(self.sSDA) & 1
            if self.state == 'WRITE1' and self.din_latched and released_sda and not self.sSDA:
                self.al_reg = 1
            if enabled and not slave_wait and (self.cnt == 0 or scl_sync):
                clk_en = True
                self.cnt = int(i.get('clk_cnt', 0)) & 0xffff
            elif not enabled:
                clk_en = False
                self.cnt = int(i.get('clk_cnt', 0)) & 0xffff
            elif slave_wait:
                clk_en = False
            else:
                clk_en = False
                self.cnt = (self.cnt - 1) & 0xffff
            if not enabled:
                self.filter_counter = 0
            self._current_cmd = int(i.get('cmd', 0)) & 0xf
            self._current_din = int(i.get('din', 0)) & 1
            if enabled:
                self._advance_fsm(clk_en, sta, sto)
            else:
                self.state = self.state
            self._line_outputs()
            self._set_probes(self.cSCL2, self.cSDA2, self.sSCL, self.sSDA,
                             self.dSCL, self.dSDA, self.fSCL[-1], self.fSDA[-1],
                             self.filter_counter == 0, self.cnt == 0, clk_en,
                             slave_wait, scl_sync, sta, sto,
                             self.state == 'WRITE1' and self.din_latched == 1,
                             self.state == 'IDLE', self.state != 'IDLE',
                             self.state.startswith('START'), self.state.startswith('STOP'),
                             self.state.startswith('READ'), self.state.startswith('WRITE'),
                             rising, falling, True)
        o['cmd_ack'] = int(self.cmd_ack_reg) & 1
        o['busy'] = int(self.busy_reg) & 1
        o['al'] = int(self.al_reg) & 1
        o['dout'] = int(self.dout_reg) & 1
        o['scl_o'] = 0
        o['scl_oen'] = int(self.scl_oen_reg) & 1
        o['sda_o'] = 0
        o['sda_oen'] = int(self.sda_oen_reg) & 1
        return o
