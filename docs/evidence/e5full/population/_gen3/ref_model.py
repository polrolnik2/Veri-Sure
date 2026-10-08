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
        self._reset_state()


    def _reset_state(self):
        self.state = 'IDLE'
        self.phase = 0
        self.cmd_latched = 0
        self.din_latched = 0
        self.cSCL = [1, 1]
        self.cSDA = [1, 1]
        self.fSCL = [1, 1, 1]
        self.fSDA = [1, 1, 1]
        self.sSCL = 1
        self.sSDA = 1
        self.dSCL = 1
        self.dSDA = 1
        self.cnt = 0
        self.filter_counter = 0
        self.dout_reg = 0
        self.busy_reg = 0
        self.al_reg = 0
        self.cmd_ack_reg = 0
        self.scl_oen_reg = 1
        self.sda_oen_reg = 1
        self._previous_scl = 1
        self._previous_sda = 1
        self._tick = 0
        self._slave_wait = 0
        self._scl_sync = 0
        self._sta = 0
        self._sto = 0
        self._sda_chk = 0
        self._filtered_rising = 0
        self._filtered_falling = 0
        self._sample_shift = 0
        self._update_probes()


    def _majority(self, h):
        return 1 if (h[0] + h[1] + h[2]) >= 2 else 0


    def _reset_requested(self, i):
        return (not i.get('nReset', 1)) or bool(i.get('rst', 0))


    def _sync_filter(self, i):
        old_scl = self.sSCL
        old_sda = self.sSDA
        self.cSCL[0] = int(bool(i.get('scl_i', 1)))
        self.cSCL[1] = self.cSCL[0]
        self.cSDA[0] = int(bool(i.get('sda_i', 1)))
        self.cSDA[1] = self.cSDA[0]
        interval = max(1, (self.mask(i.get('clk_cnt', 0), 16) >> 2))
        do_sample = False
        if not i.get('ena', 0):
            self.filter_counter = 0
        elif self.filter_counter <= 0:
            do_sample = True
            self.filter_counter = interval - 1
        else:
            self.filter_counter -= 1
        if do_sample:
            self.fSCL = [self.fSCL[1], self.fSCL[2], self.cSCL[1]]
            self.fSDA = [self.fSDA[1], self.fSDA[2], self.cSDA[1]]
            self._sample_shift = 1
        else:
            self._sample_shift = 0
        self.sSCL = self._majority(self.fSCL)
        self.sSDA = self._majority(self.fSDA)
        self.dSCL = old_scl
        self.dSDA = old_sda
        self._filtered_rising = int((not old_scl) and self.sSCL)
        self._filtered_falling = int(old_scl and (not self.sSCL))
        self._sta = int((not self.sSDA) and self.dSDA and self.sSCL)
        self._sto = int(self.sSDA and (not self.dSDA) and self.sSCL)
        self._previous_scl = old_scl
        self._previous_sda = old_sda


    def _timing(self, i):
        self._tick = 0
        self._scl_sync = int(self.scl_oen_reg and self._filtered_falling)
        self._slave_wait = int(self.scl_oen_reg and (not self.sSCL))
        reload_value = self.mask(i.get('clk_cnt', 0), 16)
        if not i.get('ena', 0):
            self.cnt = reload_value
            return
        if self._slave_wait:
            return
        if self._scl_sync:
            self.cnt = reload_value
            self._tick = 1
            return
        if self.cnt <= 0:
            self._tick = 1
            self.cnt = reload_value
        else:
            self.cnt = self.mask(self.cnt - 1, 16)


    def _arbitration_and_bus_status(self):
        if self._sta:
            self.busy_reg = 1
        if self._sto:
            self.busy_reg = 0
        if self.state != 'IDLE' and self._sto and self.cmd_latched != 2:
            self.al_reg = 1
            self.state = 'IDLE'
            self.phase = 0
            self.scl_oen_reg = 1
            self.sda_oen_reg = 1
        if self._sda_chk and self.sda_oen_reg and not self.sSDA:
            self.al_reg = 1
            self.state = 'IDLE'
            self.phase = 0
            self.scl_oen_reg = 1
            self.sda_oen_reg = 1


    def _set_phase_outputs(self):
        if self.state == 'IDLE':
            self.scl_oen_reg = 1
            self.sda_oen_reg = 1
            self._sda_chk = 0
        elif self.state == 'START':
            self._sda_chk = 0
            if self.phase == 0:
                self.scl_oen_reg, self.sda_oen_reg = 1, 1
            elif self.phase == 1:
                self.scl_oen_reg, self.sda_oen_reg = 1, 0
            else:
                self.scl_oen_reg, self.sda_oen_reg = 0, 0
        elif self.state == 'STOP':
            self._sda_chk = 0
            if self.phase == 0:
                self.scl_oen_reg, self.sda_oen_reg = 0, 0
            elif self.phase == 1:
                self.scl_oen_reg, self.sda_oen_reg = 1, 0
            else:
                self.scl_oen_reg, self.sda_oen_reg = 1, 1
        elif self.state == 'READ':
            self._sda_chk = 0
            if self.phase == 0:
                self.scl_oen_reg, self.sda_oen_reg = 0, 1
            elif self.phase == 1:
                self.scl_oen_reg, self.sda_oen_reg = 1, 1
            else:
                self.scl_oen_reg, self.sda_oen_reg = 0, 1
        elif self.state == 'WRITE':
            self.sda_oen_reg = 1 if self.din_latched else 0
            if self.phase == 0:
                self.scl_oen_reg = 0
                self._sda_chk = 0
            elif self.phase == 1:
                self.scl_oen_reg = 1
                self._sda_chk = int(bool(self.din_latched))
            else:
                self.scl_oen_reg = 0
                self._sda_chk = 0


    def _fsm(self, i):
        if not i.get('ena', 0):
            if self.state == 'IDLE':
                self._set_phase_outputs()
            return
        if self.state == 'IDLE':
            if self._tick:
                command = self.mask(i.get('cmd', 0), 4)
                if command in (1, 2, 4, 8):
                    self.cmd_latched = command
                    self.din_latched = int(bool(i.get('din', 0)))
                    self.phase = 0
                    self.state = {1: 'START', 2: 'STOP', 4: 'WRITE', 8: 'READ'}[command]
            self._set_phase_outputs()
            return
        self._set_phase_outputs()
        if self._tick and not self._slave_wait:
            if self.phase < 2:
                self.phase += 1
            else:
                self.state = 'IDLE'
                self.phase = 0
                self.cmd_ack_reg = 1
                self._set_phase_outputs()


    def _update_probes(self):
        self.cscl = bool(self.cSCL[1])
        self.csda = bool(self.cSDA[1])
        self.sscl = bool(self.sSCL)
        self.ssda = bool(self.sSDA)
        self.dscl = bool(self.dSCL)
        self.dsda = bool(self.dSDA)
        self.fscl = bool(self._sample_shift)
        self.fsda = bool(self._sample_shift)
        self.filter_cnt = bool(self.filter_counter == 0)
        self.cnt_zero = bool(self.cnt == 0)
        self.clk_en = bool(self._tick)
        self.slave_wait = bool(self._slave_wait)
        self.scl_sync = bool(self._scl_sync)
        self.sta_condition = bool(self._sta)
        self.sto_condition = bool(self._sto)
        self.sda_chk = bool(self._sda_chk)
        self.idle = self.state == 'IDLE'
        self.fsm_active = not self.idle
        self.start_sequence = self.state == 'START'
        self.stop_sequence = self.state == 'STOP'
        self.read_sequence = self.state == 'READ'
        self.write_sequence = self.state == 'WRITE'
        self.filtered_scl_rising = bool(self._filtered_rising)
        self.filtered_scl_falling = bool(self._filtered_falling)
        self.i2c_master_bit_ctrl = True


    def step(self, i):
        o = {p: None for p in self.OUTPUT_PORTS}
        if not i.get('nReset', 1):
            self._reset_state()
        elif i.get('rst', 0):
            self._reset_state()
        else:
            self.cmd_ack_reg = 0
            self._sync_filter(i)
            self._timing(i)
            if self._filtered_rising:
                self.dout_reg = int(bool(self.sSDA))
            self._arbitration_and_bus_status()
            self._fsm(i)
            if self.al_reg:
                self.state = 'IDLE'
                self.scl_oen_reg = 1
                self.sda_oen_reg = 1
            self._update_probes()
        o['cmd_ack'] = int(bool(self.cmd_ack_reg))
        o['busy'] = int(bool(self.busy_reg))
        o['al'] = int(bool(self.al_reg))
        o['dout'] = int(bool(self.dout_reg))
        o['scl_o'] = 0
        o['scl_oen'] = int(bool(self.scl_oen_reg))
        o['sda_o'] = 0
        o['sda_oen'] = int(bool(self.sda_oen_reg))
        return o
