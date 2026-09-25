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
        self.reset_state()


    def reset_state(self):
        self.state = 'IDLE'
        self.cmd_latched = 0
        self.din_latched = 0
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
        self.cmd_ack_reg = 0
        self.busy_reg = 0
        self.al_reg = 0
        self.dout_reg = 0
        self.scl_oen_reg = 1
        self.sda_oen_reg = 1
        self._update_probes(0, 0, 0, 0, 0, 0, 0, 0)


    def _majority(self, h):
        return 1 if (h[0] + h[1] + h[2]) >= 2 else 0


    def _update_probes(self, clk_en, cnt_zero, filter_expired, scl_sync, sta, sto, filtered_rise, sda_chk):
        self.idle = 1 if self.state == 'IDLE' else 0
        self.cnt_zero = 1 if cnt_zero else 0
        self.clk_en = 1 if clk_en else 0
        self.slave_wait = 1 if (self.scl_oen_reg and not self.sSCL) else 0
        self.scl_sync = 1 if scl_sync else 0
        self.cscl = 1 if self.cSCL else 0
        self.csda = 1 if self.cSDA else 0
        self.filter_cnt = 1 if self.filter_counter != 0 else 0
        self.filter_cnt_expired = 1 if filter_expired else 0
        self.fscl = 1 if self._majority(self.fSCL) else 0
        self.fsda = 1 if self._majority(self.fSDA) else 0
        self.sscl = 1 if self.sSCL else 0
        self.ssda = 1 if self.sSDA else 0
        self.dscl = 1 if self.dSCL else 0
        self.dsda = 1 if self.dSDA else 0
        self.sta_condition = 1 if sta else 0
        self.sto_condition = 1 if sto else 0
        self.active_command = 0 if self.state == 'IDLE' else 1
        self.sda_chk = 1 if sda_chk else 0
        self.filtered_scl_rise = 1 if filtered_rise else 0
        self.start_sequence = 1 if self.state.startswith('START') else 0
        self.stop_sequence = 1 if self.state.startswith('STOP') else 0
        self.read_sequence = 1 if self.state.startswith('READ') else 0
        self.write_sequence = 1 if self.state.startswith('WRITE') else 0


    def _filter_inputs(self, i, ena):
        old_scl = self.sSCL
        old_sda = self.sSDA
        self.cSCL1 = 1 if i['scl_i'] else 0
        self.cSCL = self.cSCL1
        self.cSDA1 = 1 if i['sda_i'] else 0
        self.cSDA = self.cSDA1
        expired = 0
        if not ena:
            self.filter_counter = 0
        else:
            interval = (i['clk_cnt'] & 0xffff) >> 2
            if interval == 0 or self.filter_counter == 0:
                expired = 1
                self.filter_counter = interval
                self.fSCL = [self.fSCL[1], self.fSCL[2], self.cSCL]
                self.fSDA = [self.fSDA[1], self.fSDA[2], self.cSDA]
                self.dSCL = self.sSCL
                self.dSDA = self.sSDA
                self.sSCL = self._majority(self.fSCL)
                self.sSDA = self._majority(self.fSDA)
            else:
                self.filter_counter = (self.filter_counter - 1) & 0xffff
        sta = (not self.sSDA) and self.dSDA and self.sSCL
        sto = self.sSDA and (not self.dSDA) and self.sSCL
        rise = self.sSCL and (not old_scl)
        return expired, int(sta), int(sto), int(rise), int(old_scl and not self.sSCL)


    def _timing(self, i, ena, slave_wait, scl_sync):
        if not ena:
            self.cnt = i['clk_cnt'] & 0xffff
            return 0, 0
        if slave_wait:
            return 0, 0
        if self.cnt == 0:
            self.cnt = i['clk_cnt'] & 0xffff
            return 1, 1
        self.cnt = (self.cnt - 1) & 0xffff
        return 0, 0


    def _command_fsm(self, i, tick, slave_wait, sta, sto, scl_fall):
        sda_chk = 0
        lost = 0
        if self.state == 'IDLE':
            if tick and i['ena']:
                c = i['cmd'] & 0xf
                if c in (1, 2, 4, 8):
                    self.cmd_latched = c
                    self.din_latched = i['din'] & 1
                    if c == 1:
                        self.state = 'START0'
                    elif c == 2:
                        self.state = 'STOP0'
                    elif c == 4:
                        self.state = 'WRITE0'
                    else:
                        self.state = 'READ0'
        elif tick and not slave_wait:
            if self.state == 'START0':
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
                sda_chk = 1 if self.din_latched else 0
                if self.din_latched and not self.sSDA:
                    lost = 1
                elif self.sSCL:
                    self.state = 'WRITE2'
            elif self.state == 'WRITE2':
                self.state = 'IDLE'
                self.cmd_ack_reg = 1
        if sto and self.state != 'IDLE' and self.state not in ('STOP0', 'STOP1', 'STOP2'):
            lost = 1
        if lost:
            self.al_reg = 1
            self.state = 'IDLE'
            self.scl_oen_reg = 1
            self.sda_oen_reg = 1
            self.cmd_ack_reg = 0
        return sda_chk, lost


    def _drive_outputs(self):
        scl = 1
        sda = 1
        if self.state in ('START1', 'START2'):
            sda = 0
        elif self.state in ('STOP0',):
            sda = 0
        elif self.state in ('READ0', 'READ1', 'READ2'):
            sda = 1
        elif self.state.startswith('WRITE'):
            sda = 1 if self.din_latched else 0
        if self.state in ('START2', 'READ2', 'WRITE2'):
            scl = 0
        elif self.state in ('START0', 'START1', 'STOP1', 'STOP2', 'READ1', 'WRITE1'):
            scl = 1
        elif self.state == 'STOP0':
            scl = 0
        self.scl_oen_reg = scl
        self.sda_oen_reg = sda


    def step(self, i):
        o = {p: None for p in self.OUTPUT_PORTS}
        if not i.get('nReset', 1):
            self.reset_state()
        elif i.get('rst', 0):
            self.reset_state()
        else:
            self.cmd_ack_reg = 0
            expired, sta, sto, rise, scl_fall = self._filter_inputs(i, bool(i['ena']))
            if sta:
                self.busy_reg = 1
            if sto:
                self.busy_reg = 0
            if rise:
                self.dout_reg = self.sSDA
            released_scl = bool(self.scl_oen_reg)
            slave_wait = released_scl and not self.sSCL
            scl_sync = released_scl and bool(scl_fall)
            tick, cnt_zero = self._timing(i, bool(i['ena']), slave_wait, scl_sync)
            if scl_sync:
                self.cnt = i['clk_cnt'] & 0xffff
            sda_chk, lost = self._command_fsm(i, tick, slave_wait, sta, sto, scl_fall)
            self._drive_outputs()
            if not i['ena']:
                self.cnt = i['clk_cnt'] & 0xffff
            self._update_probes(tick, cnt_zero, expired, scl_sync, sta, sto, rise, sda_chk)
        o['cmd_ack'] = self.cmd_ack_reg & 1
        o['busy'] = self.busy_reg & 1
        o['al'] = self.al_reg & 1
        o['dout'] = self.dout_reg & 1
        o['scl_o'] = 0
        o['scl_oen'] = self.scl_oen_reg & 1
        o['sda_o'] = 0
        o['sda_oen'] = self.sda_oen_reg & 1
        return o


    def reset(self):
        self.reset_state()
