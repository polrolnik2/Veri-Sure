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
        self.cmd_latched = 0
        self.din_latched = 0
        self.cSCL = 1
        self.cSCL_d = 1
        self.cSDA = 1
        self.cSDA_d = 1
        self.fSCL = [1, 1, 1]
        self.fSDA = [1, 1, 1]
        self.sSCL = 1
        self.sSDA = 1
        self.dSCL = 1
        self.dSDA = 1
        self.cnt = 0
        self.filter_counter = 0
        self.scl_oen_r = 1
        self.sda_oen_r = 1
        self.cmd_ack_r = 0
        self.busy_r = 0
        self.al_r = 0
        self.dout_r = 0
        self._update_probes(False, False, False, False, False, False, False, False,
                            False, False, False, False, False, False, False, False,
                            False, False, False, False, False, False, False, False,
                            True)


    def _update_probes(self, cscl, csda, sscl, ssda, dscl, dsda, fscl, fsda,
                       filter_cnt, cnt_zero, clk_en, slave_wait, scl_sync,
                       sta_condition, sto_condition, sda_chk, idle, fsm_active,
                       start_sequence, stop_sequence, read_sequence,
                       write_sequence, filtered_scl_rising,
                       filtered_scl_falling, controller):
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
        self.i2c_master_bit_ctrl = bool(controller)


    def _sample_inputs(self, i, ena):
        old_scl = self.sSCL
        old_sda = self.sSDA
        self.cSCL_d = self.cSCL
        self.cSDA_d = self.cSDA
        self.cSCL = int(i.get('scl_i', 1)) & 1
        self.cSDA = int(i.get('sda_i', 1)) & 1
        interval = (int(i.get('clk_cnt', 0)) & 0xffff) >> 2
        if interval == 0:
            interval = 1
        sampled = False
        if not ena:
            self.filter_counter = 0
        elif self.filter_counter == 0:
            self.fSCL = [self.fSCL[1], self.fSCL[2], self.cSCL_d]
            self.fSDA = [self.fSDA[1], self.fSDA[2], self.cSDA_d]
            self.filter_counter = interval - 1
            sampled = True
        else:
            self.filter_counter -= 1
        self.dSCL = self.sSCL
        self.dSDA = self.sSDA
        self.sSCL = int(sum(self.fSCL) >= 2)
        self.sSDA = int(sum(self.fSDA) >= 2)
        rising = (old_scl == 0 and self.sSCL == 1)
        falling = (old_scl == 1 and self.sSCL == 0)
        sta = bool(old_sda and not self.sSDA and self.sSCL)
        sto = bool(not old_sda and self.sSDA and self.sSCL)
        return sampled, rising, falling, sta, sto


    def _timing_tick(self, i, ena, slave_wait, scl_sync):
        reload_value = int(i.get('clk_cnt', 0)) & 0xffff
        if not ena:
            self.cnt = reload_value
            return False, False
        if slave_wait:
            return False, self.cnt == 0
        if scl_sync or self.cnt == 0:
            self.cnt = reload_value
            return True, True
        self.cnt = (self.cnt - 1) & 0xffff
        return False, False


    def _advance_fsm(self, i, tick, ena, slave_wait, sto):
        self.cmd_ack_r = 0
        if self.al_r:
            self.state = 'IDLE'
            self.scl_oen_r = 1
            self.sda_oen_r = 1
            return
        if not ena or slave_wait or not tick:
            return
        if self.state == 'IDLE':
            cmd = int(i.get('cmd', 0)) & 0xf
            if cmd in (1, 2, 4, 8):
                self.cmd_latched = cmd
                self.din_latched = int(i.get('din', 0)) & 1
                self.state = {1: 'START1', 2: 'STOP1', 4: 'WRITE1', 8: 'READ1'}[cmd]
            return
        if sto and self.cmd_latched != 2:
            self.al_r = 1
            self.state = 'IDLE'
            self.scl_oen_r = 1
            self.sda_oen_r = 1
            return
        if self.state == 'START1':
            self.scl_oen_r = 1
            self.sda_oen_r = 1
            self.state = 'START2'
        elif self.state == 'START2':
            self.scl_oen_r = 1
            self.sda_oen_r = 0
            self.state = 'START3'
        elif self.state == 'START3':
            self.scl_oen_r = 0
            self.sda_oen_r = 0
            self.state = 'IDLE'
            self.cmd_ack_r = 1
        elif self.state == 'STOP1':
            self.scl_oen_r = 0
            self.sda_oen_r = 0
            self.state = 'STOP2'
        elif self.state == 'STOP2':
            self.scl_oen_r = 1
            self.sda_oen_r = 0
            if self.sSCL:
                self.state = 'STOP3'
        elif self.state == 'STOP3':
            self.scl_oen_r = 1
            self.sda_oen_r = 1
            self.state = 'IDLE'
            self.cmd_ack_r = 1
        elif self.state == 'READ1':
            self.scl_oen_r = 0
            self.sda_oen_r = 1
            self.state = 'READ2'
        elif self.state == 'READ2':
            self.scl_oen_r = 1
            self.sda_oen_r = 1
            if self.sSCL:
                self.state = 'READ3'
        elif self.state == 'READ3':
            self.scl_oen_r = 0
            self.sda_oen_r = 1
            self.state = 'IDLE'
            self.cmd_ack_r = 1
        elif self.state == 'WRITE1':
            self.scl_oen_r = 0
            self.sda_oen_r = 0 if self.din_latched == 0 else 1
            self.state = 'WRITE2'
        elif self.state == 'WRITE2':
            self.scl_oen_r = 1
            self.sda_oen_r = 0 if self.din_latched == 0 else 1
            if self.sSCL:
                self.state = 'WRITE3'
        elif self.state == 'WRITE3':
            self.scl_oen_r = 0
            self.sda_oen_r = 0 if self.din_latched == 0 else 1
            self.state = 'IDLE'
            self.cmd_ack_r = 1


    def _update_status(self, sta, sto, rising):
        if sta:
            self.busy_r = 1
        if sto:
            self.busy_r = 0
        if rising:
            self.dout_r = self.sSDA
        if self.state == 'WRITE2' and self.din_latched == 1 and self.sSDA == 0:
            self.al_r = 1
            self.state = 'IDLE'
            self.scl_oen_r = 1
            self.sda_oen_r = 1


    def step(self, i):
        o = {p: None for p in self.OUTPUT_PORTS}
        if not (int(i.get('nReset', 1)) & 1):
            self._reset_state()
            sampled = rising = falling = sta = sto = False
            tick = cnt_zero = False
            slave_wait = scl_sync = False
        elif int(i.get('rst', 0)) & 1:
            self._reset_state()
            sampled = rising = falling = sta = sto = False
            tick = cnt_zero = False
            slave_wait = scl_sync = False
        else:
            ena = bool(int(i.get('ena', 0)) & 1)
            sampled, rising, falling, sta, sto = self._sample_inputs(i, ena)
            slave_wait = bool(self.scl_oen_r and not self.sSCL)
            scl_sync = bool(self.scl_oen_r and falling)
            tick, cnt_zero = self._timing_tick(i, ena, slave_wait, scl_sync)
            self._update_status(sta, sto, rising)
            self._advance_fsm(i, tick, ena, slave_wait, sto)
        self._update_probes(
            self.cSCL, self.cSDA, self.sSCL, self.sSDA,
            self.dSCL, self.dSDA, sampled, sampled,
            self.filter_counter == 0, cnt_zero, tick,
            slave_wait, scl_sync, sta, sto,
            self.state == 'WRITE2' and self.din_latched == 1,
            self.state == 'IDLE', self.state != 'IDLE',
            self.state.startswith('START'), self.state.startswith('STOP'),
            self.state.startswith('READ'), self.state.startswith('WRITE'),
            rising, falling, True)
        o['cmd_ack'] = int(self.cmd_ack_r) & 1
        o['busy'] = int(self.busy_r) & 1
        o['al'] = int(self.al_r) & 1
        o['dout'] = int(self.dout_r) & 1
        o['scl_o'] = 0
        o['scl_oen'] = int(self.scl_oen_r) & 1
        o['sda_o'] = 0
        o['sda_oen'] = int(self.sda_oen_r) & 1
        return o
