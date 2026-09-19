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
        self._set_probes()


    def _set_probes(self, *values):
        names = (
            'cnt_zero', 'clk_en', 'slave_wait', 'scl_sync', 'cscl', 'csda',
            'filter_cnt', 'filter_cnt_expired', 'fscl', 'fsda', 'sscl', 'ssda',
            'dscl', 'dsda', 'sta_condition', 'sto_condition', 'active_command',
            'sda_chk', 'filtered_scl_rise', 'start_sequence', 'stop_sequence',
            'read_sequence', 'write_sequence')
        vals = list(values[:len(names)])
        while len(vals) < len(names):
            vals.append(False)
        self.idle = self.state == 'IDLE'
        for name, value in zip(names, vals):
            setattr(self, name, bool(value))


    def _majority(self, history):
        return 1 if sum(history) >= 2 else 0


    def _outputs_for_state(self):
        if self.al_r or self.state == 'IDLE':
            return 1, 1
        if self.state == 'S0':
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
        if self.state in ('R0', 'R1', 'R2'):
            return (0, 1) if self.state != 'R2' else (0, 1)
        if self.state == 'W0':
            return 0, 1 if self.din_latched else 0
        if self.state == 'W1':
            return 1, 1 if self.din_latched else 0
        if self.state == 'W2':
            return 0, 1 if self.din_latched else 0
        return 1, 1


    def _filter_and_events(self, i, ena):
        old_scl = self.sSCL
        old_sda = self.sSDA
        self.cSCL1 = int(i['scl_i']) & 1
        self.cSCL = self.cSCL1
        self.cSDA1 = int(i['sda_i']) & 1
        self.cSDA = self.cSDA1
        interval = ((int(i['clk_cnt']) & 0xffff) >> 2)
        expired = False
        if not ena:
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
            self.dSCL = self.sSCL
            self.dSDA = self.sSDA
            self.fSCL = [self.fSCL[1], self.fSCL[2], self.cSCL]
            self.fSDA = [self.fSDA[1], self.fSDA[2], self.cSDA]
            self.sSCL = self._majority(self.fSCL)
            self.sSDA = self._majority(self.fSDA)
        rise = bool((not old_scl) and self.sSCL)
        sta = bool((not self.sSDA) and old_sda and self.sSCL)
        sto = bool(self.sSDA and (not old_sda) and self.sSCL)
        return expired, rise, sta, sto, old_scl


    def _advance_fsm(self, tick, wait, sta, sto):
        self.cmd_ack_r = 0
        if self.al_r:
            self.state = 'IDLE'
            self.scl_oen_r = 1
            self.sda_oen_r = 1
            return
        active = self.state != 'IDLE'
        unexpected_stop = active and self.state[0] != 'P'
        arbitration = self.state == 'W1' and bool(self.din_latched) and not self.sSDA
        if arbitration or (unexpected_stop and sto):
            self.al_r = 1
            self.state = 'IDLE'
            self.scl_oen_r = 1
            self.sda_oen_r = 1
            return
        if not tick or wait:
            return
        if self.state == 'IDLE':
            command = self.cmd_latched & 0xf
            if command == 1:
                self.state = 'S0'
            elif command == 2:
                self.state = 'P0'
            elif command == 4:
                self.state = 'W0'
            elif command == 8:
                self.state = 'R0'
            return
        prefix = self.state[0]
        phase = int(self.state[1])
        if phase < 2:
            self.state = prefix + str(phase + 1)
        else:
            self.state = 'IDLE'
            self.cmd_ack_r = 1


    def step(self, i):
        o = {p: None for p in self.OUTPUT_PORTS}
        if not int(i.get('nReset', 1)):
            self.reset()
        elif int(i.get('rst', 0)):
            self.reset()
        else:
            ena = bool(int(i.get('ena', 0)))
            expired, rise, sta, sto, old_scl = self._filter_and_events(i, ena)
            if sta:
                self.busy_r = 1
            if sto:
                self.busy_r = 0
            if rise:
                self.dout_r = self.sSDA
            pre_scl, pre_sda = self._outputs_for_state()
            wait = bool(pre_scl == 1 and not self.sSCL)
            sync = bool(pre_scl == 1 and old_scl and not self.sSCL)
            cnt_zero = self.cnt == 0
            tick = False
            if not ena:
                self.cnt = int(i['clk_cnt']) & 0xffff
            elif wait:
                tick = False
            elif sync or cnt_zero:
                tick = True
                self.cnt = int(i['clk_cnt']) & 0xffff
            else:
                self.cnt = (self.cnt - 1) & 0xffff
            if ena and self.state == 'IDLE' and tick:
                self.cmd_latched = int(i['cmd']) & 0xf
                self.din_latched = int(i['din']) & 1
            self._advance_fsm(tick if ena else False, wait, sta, sto)
            self.scl_oen_r, self.sda_oen_r = self._outputs_for_state()
            self._set_probes(
                cnt_zero, tick, wait, sync, self.cSCL, self.cSDA,
                self.filter_counter != 0, expired, self.fSCL[-1], self.fSDA[-1],
                self.sSCL, self.sSDA, self.dSCL, self.dSDA, sta, sto,
                self.state != 'IDLE',
                self.state == 'W1' and bool(self.din_latched), rise,
                self.state.startswith('S'), self.state.startswith('P'),
                self.state.startswith('R'), self.state.startswith('W'))
        o['cmd_ack'] = int(self.cmd_ack_r) & 1
        o['busy'] = int(self.busy_r) & 1
        o['al'] = int(self.al_r) & 1
        o['dout'] = int(self.dout_r) & 1
        o['scl_o'] = 0
        o['scl_oen'] = int(self.scl_oen_r) & 1
        o['sda_o'] = 0
        o['sda_oen'] = int(self.sda_oen_r) & 1
        return o
