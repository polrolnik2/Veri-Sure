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

    def _reset_state(self):
        self.state = 'IDLE'
        self.cnt = 0
        self.filter_counter = 0
        self.cSCL1 = self.cSCL2 = 1
        self.cSDA1 = self.cSDA2 = 1
        self.fSCL = [1, 1, 1]
        self.fSDA = [1, 1, 1]
        self.sSCL = self.sSDA = 1
        self.dSCL = self.dSDA = 1
        self.busy_reg = 0
        self.al_reg = 0
        self.dout_reg = 0
        self.cmd_ack_reg = 0
        self.din_latched = 0
        self.ack_hold = None
        self._tick = 0
        self._cnt_zero = 0
        self._filter_expired = 0
        self._scl_sync = 0
        self._sta = 0
        self._sto = 0
        self._slave_wait = 0
        self._sda_chk = 0
        self._set_probes()


    def _set_probes(self):
        self.idle = bool(self.state == 'IDLE')
        self.clk_en = bool(self._tick)
        self.cnt_zero = bool(self._cnt_zero)
        self.filter_cnt = bool(self._filter_expired)
        self.slave_wait = bool(self._slave_wait)
        self.scl_sync = bool(self._scl_sync)
        self.cscl = bool(self.cSCL2)
        self.csda = bool(self.cSDA2)
        self.fscl = bool(self._filter_expired)
        self.fsda = bool(self._filter_expired)
        self.sscl = bool(self.sSCL)
        self.ssda = bool(self.sSDA)
        self.dscl = bool(self.dSCL)
        self.dsda = bool(self.dSDA)
        self.sta_condition = bool(self._sta)
        self.sto_condition = bool(self._sto)
        self.active_command = bool(self.state != 'IDLE')
        self.sda_chk = bool(self._sda_chk)
        self.start_sequence = bool(self.state in ('S0', 'S1', 'S2'))
        self.stop_sequence = bool(self.state in ('P0', 'P1', 'P2'))
        self.read_sequence = bool(self.state in ('R0', 'R1', 'R2'))
        self.write_sequence = bool(self.state in ('W0', 'W1', 'W2'))
        self.write_stable_high_phase = bool(self.state == 'W1')
        self.read_sample_window = bool(self.state == 'R1')


    def _output_enables(self):
        if self.al_reg:
            return 1, 1
        if self.ack_hold is not None and self.cmd_ack_reg:
            return self.ack_hold
        if self.state in ('IDLE', 'S0'):
            return 1, 1
        if self.state == 'S1':
            return 1, 0
        if self.state == 'S2':
            return 0, 0
        if self.state == 'P0':
            return 0, 0
        if self.state == 'P1':
            return 1, 0
        if self.state == 'P2':
            return 1, 1
        if self.state == 'R0':
            return 0, 1
        if self.state == 'R1':
            return 1, 1
        if self.state == 'R2':
            return 0, 1
        if self.state == 'W0':
            return 0, 0 if self.din_latched == 0 else 1
        if self.state == 'W1':
            return 1, 0 if self.din_latched == 0 else 1
        if self.state == 'W2':
            return 0, 0 if self.din_latched == 0 else 1
        return 1, 1


    def _update_inputs(self, i, ena):
        old_scl = self.sSCL
        old_sda = self.sSDA
        self.cSCL1 = int(i['scl_i']) & 1
        self.cSDA1 = int(i['sda_i']) & 1
        self.cSCL2 = self.cSCL1
        self.cSDA2 = self.cSDA1
        expired = False
        if ena:
            interval = ((int(i['clk_cnt']) & 0xffff) >> 2)
            if interval == 0:
                expired = True
            elif self.filter_counter == 0:
                expired = True
                self.filter_counter = interval
            else:
                self.filter_counter -= 1
            if expired:
                self.fSCL = [self.fSCL[1], self.fSCL[2], self.cSCL2]
                self.fSDA = [self.fSDA[1], self.fSDA[2], self.cSDA2]
        else:
            self.filter_counter = 0
        self.sSCL = int(sum(self.fSCL) >= 2)
        self.sSDA = int(sum(self.fSDA) >= 2)
        self.dSCL = old_scl
        self.dSDA = old_sda
        sta = int((not self.sSDA) and old_sda and self.sSCL)
        sto = int(self.sSDA and (not old_sda) and self.sSCL)
        return expired, sta, sto, old_scl


    def _advance_fsm(self, i, tick, sto):
        if self.al_reg:
            self.state = 'IDLE'
            self.ack_hold = None
            return
        if sto and self.state != 'IDLE' and self.state not in ('P0', 'P1', 'P2'):
            self.al_reg = 1
            self.state = 'IDLE'
            self.ack_hold = None
            return
        if not tick:
            return
        if self.state == 'IDLE':
            cmd = int(i['cmd']) & 0xf
            if cmd == 1:
                self.state = 'S0'
            elif cmd == 2:
                self.state = 'P0'
            elif cmd == 4:
                self.din_latched = int(i['din']) & 1
                self.state = 'W0'
            elif cmd == 8:
                self.state = 'R0'
        elif self.state == 'S0':
            self.state = 'S1'
        elif self.state == 'S1':
            self.state = 'S2'
        elif self.state == 'S2':
            self.state = 'IDLE'
            self.cmd_ack_reg = 1
            self.ack_hold = (0, 0)
        elif self.state == 'P0':
            self.state = 'P1'
        elif self.state == 'P1':
            if self.sSCL:
                self.state = 'P2'
        elif self.state == 'P2':
            self.state = 'IDLE'
            self.cmd_ack_reg = 1
            self.ack_hold = (1, 1)
        elif self.state == 'R0':
            self.state = 'R1'
        elif self.state == 'R1':
            if self.sSCL:
                self.state = 'R2'
        elif self.state == 'R2':
            self.state = 'IDLE'
            self.cmd_ack_reg = 1
            self.ack_hold = (0, 1)
        elif self.state == 'W0':
            self.state = 'W1'
        elif self.state == 'W1':
            if self.din_latched and not self.sSDA:
                self.al_reg = 1
                self.state = 'IDLE'
                self.ack_hold = None
            elif self.sSCL:
                self.state = 'W2'
        elif self.state == 'W2':
            self.state = 'IDLE'
            self.cmd_ack_reg = 1
            self.ack_hold = (0, 0 if self.din_latched == 0 else 1)


    def step(self, i):
        if not hasattr(self, 'state'):
            self._reset_state()
        if not int(i['nReset']):
            self._reset_state()
        elif int(i['rst']):
            self._reset_state()
        else:
            self.cmd_ack_reg = 0
            self.ack_hold = None
            ena = int(i['ena']) & 1
            expired, sta, sto, old_scl = self._update_inputs(i, ena)
            scl_oen, sda_oen = self._output_enables()
            released_scl = int(scl_oen == 1)
            slave_wait = int(released_scl and not self.sSCL)
            scl_sync = int(released_scl and old_scl and not self.sSCL)
            cnt_zero = int(self.cnt == 0)
            tick = 0
            if not ena:
                self.cnt = int(i['clk_cnt']) & 0xffff
            elif slave_wait:
                tick = 0
            elif scl_sync:
                self.cnt = int(i['clk_cnt']) & 0xffff
                tick = 1
            elif self.cnt == 0:
                self.cnt = int(i['clk_cnt']) & 0xffff
                tick = 1
            else:
                self.cnt = (self.cnt - 1) & 0xffff
            if sta:
                self.busy_reg = 1
            if sto:
                self.busy_reg = 0
            if self.sSCL and not old_scl:
                self.dout_reg = self.sSDA
            sda_chk = int(self.state == 'W1' and self.din_latched == 1)
            if sda_chk and not self.sSDA:
                self.al_reg = 1
                self.state = 'IDLE'
                self.ack_hold = None
            self._advance_fsm(i, int(tick and not slave_wait), sto)
            self._tick = int(tick and not slave_wait)
            self._cnt_zero = cnt_zero
            self._filter_expired = int(expired)
            self._scl_sync = scl_sync
            self._sta = sta
            self._sto = sto
            self._slave_wait = slave_wait
            self._sda_chk = sda_chk
            self._set_probes()
        scl_oen, sda_oen = self._output_enables()
        o = {p: None for p in self.OUTPUT_PORTS}
        o['cmd_ack'] = int(self.cmd_ack_reg)
        o['busy'] = int(self.busy_reg)
        o['al'] = int(self.al_reg)
        o['dout'] = int(self.dout_reg) & 1
        o['scl_o'] = 0
        o['scl_oen'] = int(scl_oen) & 1
        o['sda_o'] = 0
        o['sda_oen'] = int(sda_oen) & 1
        return o
