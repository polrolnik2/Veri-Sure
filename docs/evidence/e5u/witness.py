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
    PROBE_PORTS = ['in_idle', 'fsm_active', 'in_start_sequence', 'in_stop_sequence', 'in_read_sequence', 'in_write_sequence', 'clk_en_asserted', 'timing_counter_expired', 'filter_sample_tick', 'slave_wait_active', 'scl_sync_active', 'start_condition', 'stop_condition', 'filtered_scl_high', 'filtered_sda_low', 'filtered_scl_rising', 'sda_arbitration_check']
    LATENCY_CYCLES = 1

    def __init__(self):
        self.reset()


    def reset(self):
        self.state = 'IDLE'
        self.cmd_latched = 0
        self.din_latched = 0
        self.cmd_ack_r = 0
        self.busy_r = 0
        self.al_r = 0
        self.dout_r = 0
        self.cSCL = 1
        self.cSDA = 1
        self.fSCL = [1, 1, 1]
        self.fSDA = [1, 1, 1]
        self.sSCL = 1
        self.sSDA = 1
        self.dSCL = 1
        self.dSDA = 1
        self.cnt = 0
        self.filter_cnt = 0
        self.clk_en = 0
        self.filter_tick = 0
        self.slave_wait = 0
        self.scl_sync = 0
        self.start_cond = 0
        self.stop_cond = 0
        self.scl_rising = 0
        self.sda_chk = 0
        self._update_probes()


    def _majority(self, samples):
        return 1 if (samples[0] + samples[1] + samples[2]) >= 2 else 0


    def _filter_inputs(self, i):
        old_scl = self.sSCL
        old_sda = self.sSDA
        self.cSCL = self.cSCL_next
        self.cSDA = self.cSDA_next
        self.cSCL_next = int(i['scl_i']) & 1
        self.cSDA_next = int(i['sda_i']) & 1
        self.filter_tick = 0
        if int(i['ena']) & 1:
            interval = (int(i['clk_cnt']) & 0xffff) >> 2
            if interval == 0:
                self.filter_tick = 1
                self.filter_cnt = 0
            elif self.filter_cnt == 0:
                self.filter_tick = 1
                self.filter_cnt = interval
            else:
                self.filter_cnt = (self.filter_cnt - 1) & 0xffff
        else:
            self.filter_cnt = 0
        if self.filter_tick:
            self.fSCL = [self.fSCL[1], self.fSCL[2], self.cSCL]
            self.fSDA = [self.fSDA[1], self.fSDA[2], self.cSDA]
            self.sSCL = self._majority(self.fSCL)
            self.sSDA = self._majority(self.fSDA)
        self.dSCL = old_scl
        self.dSDA = old_sda
        self.start_cond = int((not self.sSDA) and old_sda and self.sSCL)
        self.stop_cond = int(self.sSDA and (not old_sda) and self.sSCL)
        self.scl_rising = int(self.sSCL and not old_scl)


    def _divider(self, i, released_scl):
        self.clk_en = 0
        self.scl_sync = int(released_scl and self.dSCL and not self.sSCL)
        if not (int(i['ena']) & 1):
            self.cnt = int(i['clk_cnt']) & 0xffff
            return
        if self.slave_wait:
            return
        if self.scl_sync:
            self.cnt = int(i['clk_cnt']) & 0xffff
            self.clk_en = 1
        elif self.cnt == 0:
            self.cnt = int(i['clk_cnt']) & 0xffff
            self.clk_en = 1
        else:
            self.cnt = (self.cnt - 1) & 0xffff


    def _line_enables(self):
        if self.state == 'IDLE':
            return 1, 1
        if self.state == 'ST0':
            return 1, 1
        if self.state == 'ST1':
            return 1, 0
        if self.state == 'ST2':
            return 0, 0
        if self.state == 'PO0':
            return 0, 0
        if self.state == 'PO1':
            return 1, 0
        if self.state == 'PO2':
            return 1, 1
        if self.state == 'RD0':
            return 0, 1
        if self.state == 'RD1':
            return 1, 1
        if self.state == 'RD2':
            return 0, 1
        if self.state == 'WR0':
            return 0, 0 if self.din_latched == 0 else 1
        if self.state == 'WR1':
            return 1, 0 if self.din_latched == 0 else 1
        if self.state == 'WR2':
            return 0, 0 if self.din_latched == 0 else 1
        return 1, 1


    def _command_fsm(self, i):
        self.cmd_ack_r = 0
        self.sda_chk = int(self.state == 'WR1' and self.din_latched == 1)
        if self.al_r:
            self.state = 'IDLE'
            return
        if self.state != 'IDLE' and self.stop_cond and self.cmd_latched != 2:
            self.al_r = 1
            self.state = 'IDLE'
            return
        if not (int(i['ena']) & 1) or not self.clk_en:
            return
        if self.state == 'IDLE':
            c = int(i['cmd']) & 0xf
            if c in (1, 2, 4, 8):
                self.cmd_latched = c
                self.din_latched = int(i['din']) & 1
                self.state = {1: 'ST0', 2: 'PO0', 4: 'WR0', 8: 'RD0'}[c]
            return
        if self.state == 'ST0':
            self.state = 'ST1'
        elif self.state == 'ST1':
            self.state = 'ST2'
        elif self.state == 'ST2':
            self.state = 'IDLE'
            self.cmd_ack_r = 1
        elif self.state == 'PO0':
            self.state = 'PO1'
        elif self.state == 'PO1':
            if self.sSCL:
                self.state = 'PO2'
        elif self.state == 'PO2':
            self.state = 'IDLE'
            self.cmd_ack_r = 1
        elif self.state == 'RD0':
            self.state = 'RD1'
        elif self.state == 'RD1':
            if self.sSCL:
                self.state = 'RD2'
        elif self.state == 'RD2':
            self.state = 'IDLE'
            self.cmd_ack_r = 1
        elif self.state == 'WR0':
            self.state = 'WR1'
        elif self.state == 'WR1':
            if self.sSCL:
                self.state = 'WR2'
        elif self.state == 'WR2':
            self.state = 'IDLE'
            self.cmd_ack_r = 1


    def _update_probes(self):
        self.in_idle = self.state == 'IDLE'
        self.fsm_active = not self.in_idle
        self.in_start_sequence = self.state.startswith('ST')
        self.in_stop_sequence = self.state.startswith('PO')
        self.in_read_sequence = self.state.startswith('RD')
        self.in_write_sequence = self.state.startswith('WR')
        self.clk_en_asserted = bool(self.clk_en)
        self.timing_counter_expired = bool(self.cnt == 0)
        self.filter_sample_tick = bool(self.filter_tick)
        self.slave_wait_active = bool(self.slave_wait)
        self.scl_sync_active = bool(self.scl_sync)
        self.start_condition = bool(self.start_cond)
        self.stop_condition = bool(self.stop_cond)
        self.filtered_scl_high = bool(self.sSCL)
        self.filtered_sda_low = not bool(self.sSDA)
        self.filtered_scl_rising = bool(self.scl_rising)
        self.sda_arbitration_check = bool(self.sda_chk)


    def step(self, i):
        o = {p: None for p in self.OUTPUT_PORTS}
        if not hasattr(self, 'cSCL_next'):
            self.cSCL_next = 1
            self.cSDA_next = 1
        if not (int(i.get('nReset', 1)) & 1):
            self.reset()
        elif int(i.get('rst', 0)) & 1:
            self.reset()
        else:
            old_scl_oen, _ = self._line_enables()
            self._filter_inputs(i)
            self.slave_wait = int(old_scl_oen and not self.sSCL)
            self._divider(i, old_scl_oen)
            if self.scl_rising:
                self.dout_r = self.sSDA
            if self.start_cond:
                self.busy_r = 1
            if self.stop_cond:
                self.busy_r = 0
            if self.state.startswith('WR') and self.state == 'WR1' and self.din_latched and not self.sSDA:
                self.al_r = 1
            self._command_fsm(i)
        scl_oen, sda_oen = self._line_enables()
        o['cmd_ack'] = int(self.cmd_ack_r) & 1
        o['busy'] = int(self.busy_r) & 1
        o['al'] = int(self.al_r) & 1
        o['dout'] = int(self.dout_r) & 1
        o['scl_o'] = 0
        o['scl_oen'] = int(scl_oen) & 1
        o['sda_o'] = 0
        o['sda_oen'] = int(sda_oen) & 1
        self._update_probes()
        return o
