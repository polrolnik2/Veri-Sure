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
        self.cmd_ack_r = 0
        self.busy_r = 0
        self.al_r = 0
        self.dout_r = 0
        self.scl_oen_r = 1
        self.sda_oen_r = 1
        self.din_r = 0
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
        self._update_probes(False, False, False, False, False)


    def _majority(self, h):
        return 1 if sum(h) >= 2 else 0


    def _filter_inputs(self, i):
        old_scl = self.sSCL
        old_sda = self.sSDA
        self.cSCL1 = int(i['scl_i']) & 1
        self.cSCL2 = self.cSCL1
        self.cSDA1 = int(i['sda_i']) & 1
        self.cSDA2 = self.cSDA1
        expired = False
        if not i['ena']:
            self.filter_counter = 0
        else:
            interval = ((int(i['clk_cnt']) & 0xffff) >> 2)
            if interval == 0 or self.filter_counter == 0:
                expired = True
                self.filter_counter = interval
            else:
                self.filter_counter = (self.filter_counter - 1) & 0xffff
            if expired:
                self.fSCL = [self.fSCL[1], self.fSCL[2], self.cSCL2]
                self.fSDA = [self.fSDA[1], self.fSDA[2], self.cSDA2]
                self.dSCL = self.sSCL
                self.dSDA = self.sSDA
                self.sSCL = self._majority(self.fSCL)
                self.sSDA = self._majority(self.fSDA)
        rise = bool(not old_scl and self.sSCL)
        falling = bool(old_scl and not self.sSCL)
        sta = bool(not self.sSDA and self.dSDA and self.sSCL)
        sto = bool(self.sSDA and not self.dSDA and self.sSCL)
        return expired, rise, sta, sto, falling


    def _divider(self, i, slave_wait, scl_sync):
        if not i['ena']:
            self.cnt = int(i['clk_cnt']) & 0xffff
            return False
        if slave_wait:
            return False
        if scl_sync or self.cnt == 0:
            self.cnt = int(i['clk_cnt']) & 0xffff
            return True
        self.cnt = (self.cnt - 1) & 0xffff
        return False


    def _state_outputs(self):
        scl = 1
        sda = 1
        if self.state in ('ST1', 'ST2', 'ST_ACK'):
            sda = 0
        if self.state in ('ST2', 'ST_ACK'):
            scl = 0
        elif self.state in ('P0', 'P_ACK'):
            sda = 0
        elif self.state == 'P1':
            sda = 0
            scl = 1
        elif self.state == 'P2':
            scl = 1
            sda = 1
        elif self.state in ('R0', 'R1'):
            scl = 1
            sda = 1
        elif self.state in ('R2', 'R_ACK'):
            scl = 0
            sda = 1
        elif self.state in ('W0', 'W2', 'W_ACK'):
            scl = 0
            sda = 1 if self.din_r else 0
        elif self.state == 'W1':
            scl = 1
            sda = 1 if self.din_r else 0
        self.scl_oen_r = scl
        self.sda_oen_r = sda


    def _fsm(self, i, tick, sto):
        self.cmd_ack_r = 0
        active = self.state != 'IDLE'
        if active and sto and not self.state.startswith('P'):
            self.al_r = 1
            self.state = 'IDLE'
            self.scl_oen_r = 1
            self.sda_oen_r = 1
            return
        if self.state == 'W1' and self.din_r and not self.sSDA:
            self.al_r = 1
            self.state = 'IDLE'
            self.scl_oen_r = 1
            self.sda_oen_r = 1
            return
        if not tick or not i['ena']:
            return
        if self.state == 'IDLE':
            cmd = int(i['cmd']) & 0xf
            if cmd == 1:
                self.state = 'ST0'
            elif cmd == 2:
                self.state = 'P0'
            elif cmd == 4:
                self.din_r = int(i['din']) & 1
                self.state = 'W0'
            elif cmd == 8:
                self.state = 'R0'
        elif self.state == 'ST0':
            self.state = 'ST1'
        elif self.state == 'ST1':
            self.state = 'ST2'
        elif self.state == 'ST2':
            self.state = 'ST_ACK'
        elif self.state == 'ST_ACK':
            self.cmd_ack_r = 1
            self.state = 'IDLE'
        elif self.state == 'P0':
            self.state = 'P1'
        elif self.state == 'P1':
            if self.sSCL:
                self.state = 'P2'
        elif self.state == 'P2':
            self.state = 'P_ACK'
        elif self.state == 'P_ACK':
            self.cmd_ack_r = 1
            self.state = 'IDLE'
        elif self.state == 'R0':
            self.state = 'R1'
        elif self.state == 'R1':
            if self.sSCL:
                self.state = 'R2'
        elif self.state == 'R2':
            self.state = 'R_ACK'
        elif self.state == 'R_ACK':
            self.cmd_ack_r = 1
            self.state = 'IDLE'
        elif self.state == 'W0':
            self.state = 'W1'
        elif self.state == 'W1':
            if self.sSCL:
                self.state = 'W2'
        elif self.state == 'W2':
            self.state = 'W_ACK'
        elif self.state == 'W_ACK':
            self.cmd_ack_r = 1
            self.state = 'IDLE'


    def _update_probes(self, tick, filter_expired, scl_sync, rise, falling):
        self.idle = self.state == 'IDLE'
        self.cnt_zero = bool(self.cnt == 0)
        self.clk_en = bool(tick)
        self.slave_wait = bool(self.scl_oen_r and not self.sSCL)
        self.scl_sync = bool(scl_sync)
        self.cscl = bool(self.cSCL2)
        self.csda = bool(self.cSDA2)
        self.filter_cnt = bool(self.filter_counter == 0)
        self.filter_cnt_expired = bool(filter_expired)
        self.fscl = bool(self._majority(self.fSCL))
        self.fsda = bool(self._majority(self.fSDA))
        self.sscl = bool(self.sSCL)
        self.ssda = bool(self.sSDA)
        self.dscl = bool(self.dSCL)
        self.dsda = bool(self.dSDA)
        self.sta_condition = bool(not self.sSDA and self.dSDA and self.sSCL)
        self.sto_condition = bool(self.sSDA and not self.dSDA and self.sSCL)
        self.active_command = self.state != 'IDLE'
        self.sda_chk = bool(self.state == 'W1' and self.din_r)
        self.filtered_scl_rise = bool(rise)
        self.start_sequence = self.state.startswith('ST')
        self.stop_sequence = self.state.startswith('P')
        self.read_sequence = self.state.startswith('R')
        self.write_sequence = self.state.startswith('W')


    def step(self, i):
        o = {p: None for p in self.OUTPUT_PORTS}
        if not i['nReset'] or i['rst']:
            self.reset()
        else:
            filter_expired, rise, sta, sto, falling = self._filter_inputs(i)
            if sta:
                self.busy_r = 1
            if sto:
                self.busy_r = 0
            released_scl = bool(self.scl_oen_r)
            scl_sync = bool(released_scl and falling)
            slave_wait = bool(released_scl and not self.sSCL)
            tick = self._divider(i, slave_wait, scl_sync)
            if rise:
                self.dout_r = self.sSDA
            if self.al_r:
                self.state = 'IDLE'
                self.scl_oen_r = 1
                self.sda_oen_r = 1
            else:
                self._fsm(i, tick, sto)
                self._state_outputs()
            self._update_probes(tick, filter_expired, scl_sync, rise, falling)
        o['cmd_ack'] = int(self.cmd_ack_r) & 1
        o['busy'] = int(self.busy_r) & 1
        o['al'] = int(self.al_r) & 1
        o['dout'] = int(self.dout_r) & 1
        o['scl_o'] = 0
        o['scl_oen'] = int(self.scl_oen_r) & 1
        o['sda_o'] = 0
        o['sda_oen'] = int(self.sda_oen_r) & 1
        return o
