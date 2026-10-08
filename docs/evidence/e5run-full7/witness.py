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
        self.busy_reg = 0
        self.al_reg = 0
        self.dout_reg = 0
        self.cmd_ack_reg = 0
        self.scl_oen_reg = 1
        self.sda_oen_reg = 1
        self._set_probes(0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)


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
        self.busy_reg = 0
        self.al_reg = 0
        self.dout_reg = 0
        self.cmd_ack_reg = 0
        self.scl_oen_reg = 1
        self.sda_oen_reg = 1


    def _set_probes(self, clk_en, cnt_zero, slave_wait, scl_sync, filter_expire, fscl, fsda, sta, sto, sda_chk, write_high, read_window, *unused):
        self.idle = self.state == 'IDLE'
        self.clk_en = bool(clk_en)
        self.cnt_zero = bool(cnt_zero)
        self.slave_wait = bool(slave_wait)
        self.scl_sync = bool(scl_sync)
        self.cscl = bool(self.cSCL2)
        self.csda = bool(self.cSDA2)
        self.filter_cnt = bool(filter_expire)
        self.fscl = bool(fscl)
        self.fsda = bool(fsda)
        self.sscl = bool(self.sSCL)
        self.ssda = bool(self.sSDA)
        self.dscl = bool(self.dSCL)
        self.dsda = bool(self.dSDA)
        self.sta_condition = bool(sta)
        self.sto_condition = bool(sto)
        self.active_command = self.state != 'IDLE'
        self.sda_chk = bool(sda_chk)
        self.start_sequence = self.state.startswith('S') and self.state != 'IDLE'
        self.stop_sequence = self.state.startswith('P')
        self.read_sequence = self.state.startswith('R')
        self.write_sequence = self.state.startswith('W')
        self.write_stable_high_phase = self.state == 'W_HIGH'
        self.read_sample_window = self.state == 'R_HIGH'


    def _update_inputs(self, i, ena, clk_cnt):
        self.cSCL1 = int(i['scl_i']) & 1
        self.cSDA1 = int(i['sda_i']) & 1
        old_scl = self.sSCL
        old_sda = self.sSDA
        self.cSCL2 = self.cSCL1 if self.cSCL1 in (0, 1) else 0
        self.cSDA2 = self.cSDA1 if self.cSDA1 in (0, 1) else 0
        interval = (self.mask(clk_cnt, 16) >> 2)
        if not ena:
            self.filter_counter = 0
            sample = False
        elif interval == 0 or self.filter_counter == 0:
            sample = True
            self.filter_counter = interval
        else:
            sample = False
            self.filter_counter = self.mask(self.filter_counter - 1, 16)
        if sample:
            self.fSCL = [self.fSCL[1], self.fSCL[2], self.cSCL2]
            self.fSDA = [self.fSDA[1], self.fSDA[2], self.cSDA2]
            self.sSCL = 1 if sum(self.fSCL) >= 2 else 0
            self.sSDA = 1 if sum(self.fSDA) >= 2 else 0
        self.dSCL = old_scl
        self.dSDA = old_sda
        sta = bool((not self.sSDA) and self.dSDA and self.sSCL)
        sto = bool(self.sSDA and (not self.dSDA) and self.sSCL)
        return sample, sta, sto


    def _update_fsm(self, i, tick, sta, sto, slave_wait):
        self.cmd_ack_reg = 0
        sda_chk = self.state == 'W_HIGH' and self.din_latched == 1
        if sto:
            if self.state != 'IDLE' and self.cmd_latched != 2:
                self.al_reg = 1
                self.state = 'IDLE'
                self.scl_oen_reg = 1
                self.sda_oen_reg = 1
                return sda_chk
            self.busy_reg = 0
        if sta:
            self.busy_reg = 1
        if self.al_reg:
            self.state = 'IDLE'
            self.scl_oen_reg = 1
            self.sda_oen_reg = 1
            return False
        if not tick or slave_wait:
            return sda_chk
        if self.state == 'IDLE':
            cmd = int(i['cmd']) & 15
            if cmd in (1, 2, 4, 8):
                self.cmd_latched = cmd
                self.din_latched = int(i['din']) & 1
                if cmd == 1:
                    self.state = 'S_RELEASE'
                elif cmd == 2:
                    self.state = 'P_LOW'
                elif cmd == 4:
                    self.state = 'W_LOW'
                else:
                    self.state = 'R_LOW'
        elif self.state == 'S_RELEASE':
            self.scl_oen_reg = 1
            self.sda_oen_reg = 0
            self.state = 'S_LOW'
        elif self.state == 'S_LOW':
            self.scl_oen_reg = 0
            self.sda_oen_reg = 0
            self.state = 'IDLE'
            self.cmd_ack_reg = 1
        elif self.state == 'P_LOW':
            self.sda_oen_reg = 0
            self.scl_oen_reg = 1
            self.state = 'P_HIGH'
        elif self.state == 'P_HIGH':
            if self.sSCL:
                self.sda_oen_reg = 1
                self.state = 'IDLE'
                self.cmd_ack_reg = 1
        elif self.state == 'R_LOW':
            self.sda_oen_reg = 1
            self.scl_oen_reg = 1
            self.state = 'R_HIGH'
        elif self.state == 'R_HIGH':
            if self.sSCL:
                self.scl_oen_reg = 0
                self.state = 'IDLE'
                self.cmd_ack_reg = 1
        elif self.state == 'W_LOW':
            self.sda_oen_reg = 0 if self.din_latched == 0 else 1
            self.scl_oen_reg = 1
            self.state = 'W_HIGH'
        elif self.state == 'W_HIGH':
            if self.din_latched and not self.sSDA:
                self.al_reg = 1
                self.state = 'IDLE'
                self.scl_oen_reg = 1
                self.sda_oen_reg = 1
            elif self.sSCL:
                self.scl_oen_reg = 0
                self.state = 'IDLE'
                self.cmd_ack_reg = 1
        return sda_chk


    def step(self, i):
        o = {p: None for p in self.OUTPUT_PORTS}
        clk_cnt = self.mask(int(i['clk_cnt']), 16)
        if not int(i['nReset']):
            self._reset_state(clk_cnt)
            self._set_probes(0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
        elif int(i['rst']):
            self._reset_state(clk_cnt)
            self._set_probes(0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
        else:
            ena = bool(int(i['ena']))
            sample, sta, sto = self._update_inputs(i, ena, clk_cnt)
            released_scl = self.scl_oen_reg == 1
            slave_wait = released_scl and not self.sSCL
            scl_sync = released_scl and self.dSCL and not self.sSCL
            cnt_zero = self.cnt == 0
            tick = False
            if not ena:
                self.cnt = clk_cnt
            elif slave_wait:
                pass
            elif scl_sync:
                self.cnt = clk_cnt
                tick = True
            elif cnt_zero:
                self.cnt = clk_cnt
                tick = True
            else:
                self.cnt = self.mask(self.cnt - 1, 16)
            self._update_fsm(i, tick, sta, sto, slave_wait)
            if self.sSCL and not self.dSCL:
                self.dout_reg = self.sSDA
            self._set_probes(tick, cnt_zero, slave_wait, scl_sync, sample, sample, sample, sta, sto, self.state == 'W_HIGH' and self.din_latched == 1, self.state == 'W_HIGH', self.state == 'R_HIGH')
        o['cmd_ack'] = self.mask(self.cmd_ack_reg, 1)
        o['busy'] = self.mask(self.busy_reg, 1)
        o['al'] = self.mask(self.al_reg, 1)
        o['dout'] = self.mask(self.dout_reg, 1)
        o['scl_o'] = 0
        o['scl_oen'] = self.mask(self.scl_oen_reg, 1)
        o['sda_o'] = 0
        o['sda_oen'] = self.mask(self.sda_oen_reg, 1)
        return o
