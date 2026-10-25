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
        self.cnt = 0
        self.filter_counter = 0
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
        self.busy_reg = 0
        self.al_reg = 0
        self.dout_reg = 0
        self.ack_reg = 0
        self._update_probes(0, 0, 0, 0, 0)


    def _update_probes(self, clk_en, cnt_zero, filter_sample, scl_sync, sta, sto=None):
        self.idle = self.state == 'IDLE'
        self.clk_en = int(bool(clk_en))
        self.cnt_zero = int(bool(cnt_zero))
        self.slave_wait = int(self.state in ('START1', 'STOP1', 'READ1', 'WRITE1', 'WRITE2') and self._scl_released() and not self.sSCL)
        self.scl_sync = int(bool(scl_sync))
        self.cscl = int(self.cSCL2)
        self.csda = int(self.cSDA2)
        self.filter_cnt = int(bool(filter_sample))
        self.fscl = int(bool(filter_sample))
        self.fsda = int(bool(filter_sample))
        self.sscl = int(self.sSCL)
        self.ssda = int(self.sSDA)
        self.dscl = int(self.dSCL)
        self.dsda = int(self.dSDA)
        self.sta_condition = int(bool(sta))
        self.sto_condition = int(bool(sto if sto is not None else 0))
        self.active_command = int(self.state != 'IDLE')
        self.sda_chk = int(self.state == 'WRITE2' and not self.din_latched)
        self.start_sequence = int(self.state.startswith('START'))
        self.stop_sequence = int(self.state.startswith('STOP'))
        self.read_sequence = int(self.state.startswith('READ'))
        self.write_sequence = int(self.state.startswith('WRITE'))
        self.write_stable_high_phase = int(self.state == 'WRITE2')
        self.read_sample_window = int(self.state == 'READ1')


    def _scl_released(self):
        return self.state in ('START0', 'START1', 'STOP1', 'READ1', 'WRITE1', 'WRITE2')


    def _outputs_for_state(self):
        scl_oen = 1
        sda_oen = 1
        if self.state in ('START1',):
            sda_oen = 0
        elif self.state in ('START2',):
            scl_oen = 0
            sda_oen = 0
        elif self.state in ('STOP0',):
            scl_oen = 0
            sda_oen = 0
        elif self.state in ('STOP1',):
            sda_oen = 0
        elif self.state in ('STOP2',):
            scl_oen = 1
            sda_oen = 1
        elif self.state in ('READ0',):
            sda_oen = 1
            scl_oen = 0
        elif self.state in ('READ1',):
            sda_oen = 1
            scl_oen = 1
        elif self.state in ('READ2',):
            sda_oen = 1
            scl_oen = 0
        elif self.state in ('WRITE0',):
            scl_oen = 0
            sda_oen = 0 if not self.din_latched else 1
        elif self.state in ('WRITE1', 'WRITE2'):
            scl_oen = 1
            sda_oen = 0 if not self.din_latched else 1
        elif self.state in ('WRITE3',):
            scl_oen = 0
            sda_oen = 0 if not self.din_latched else 1
        return scl_oen, sda_oen


    def _update_filter(self, i):
        old_scl = self.sSCL
        old_sda = self.sSDA
        self.cSCL1 = int(i['scl_i']) & 1
        self.cSCL2 = self.cSCL1
        self.cSDA1 = int(i['sda_i']) & 1
        self.cSDA2 = self.cSDA1
        interval = (int(i['clk_cnt']) & 0xffff) >> 2
        if interval < 1:
            interval = 1
        sample = self.filter_counter == 0
        if sample:
            self.fSCL = [self.cSCL2, self.fSCL[0], self.fSCL[1]]
            self.fSDA = [self.cSDA2, self.fSDA[0], self.fSDA[1]]
            self.sSCL = int(sum(self.fSCL) >= 2)
            self.sSDA = int(sum(self.fSDA) >= 2)
            self.filter_counter = interval - 1
        else:
            self.filter_counter -= 1
        self.dSCL = old_scl
        self.dSDA = old_sda
        sta = int((not self.sSDA) and self.dSDA and self.sSCL)
        sto = int(self.sSDA and (not self.dSDA) and self.sSCL)
        return sample, sta, sto, old_scl, old_sda


    def _timing_tick(self, i, slave_wait, scl_sync):
        if not i['ena']:
            self.cnt = int(i['clk_cnt']) & 0xffff
            return 0, 0
        if slave_wait:
            return 0, 0
        if scl_sync:
            self.cnt = int(i['clk_cnt']) & 0xffff
            return 1, 1
        if self.cnt == 0:
            self.cnt = int(i['clk_cnt']) & 0xffff
            return 1, 1
        self.cnt = (self.cnt - 1) & 0xffff
        return 0, 0


    def _command_fsm(self, i, clk_en, sto_condition, scl_sync):
        if self.al_reg:
            self.state = 'IDLE'
            return
        if sto_condition and self.state != 'IDLE' and self.cmd_latched != 2:
            self.al_reg = 1
            self.state = 'IDLE'
            return
        if not clk_en or not i['ena']:
            return
        if self.state == 'IDLE':
            cmd = int(i['cmd']) & 0xf
            if cmd in (1, 2, 4, 8):
                self.cmd_latched = cmd
                self.din_latched = int(i['din']) & 1
                self.state = {1: 'START0', 2: 'STOP0', 4: 'WRITE0', 8: 'READ0'}[cmd]
            return
        if self.state == 'START0':
            self.state = 'START1'
        elif self.state == 'START1':
            self.state = 'START2'
        elif self.state == 'START2':
            self.state = 'IDLE'
            self.ack_reg = 1
        elif self.state == 'STOP0':
            self.state = 'STOP1'
        elif self.state == 'STOP1':
            if self.sSCL:
                self.state = 'STOP2'
        elif self.state == 'STOP2':
            self.state = 'IDLE'
            self.ack_reg = 1
        elif self.state == 'READ0':
            self.state = 'READ1'
        elif self.state == 'READ1':
            if self.sSCL:
                self.state = 'READ2'
        elif self.state == 'READ2':
            self.state = 'IDLE'
            self.ack_reg = 1
        elif self.state == 'WRITE0':
            self.state = 'WRITE1'
        elif self.state == 'WRITE1':
            if self.sSCL:
                self.state = 'WRITE2'
        elif self.state == 'WRITE2':
            if self.din_latched and not self.sSDA:
                self.al_reg = 1
                self.state = 'IDLE'
            else:
                self.state = 'WRITE3'
        elif self.state == 'WRITE3':
            self.state = 'IDLE'
            self.ack_reg = 1


    def _update_status(self, sta_condition, sto_condition, old_scl, old_sda):
        if sta_condition:
            self.busy_reg = 1
        if sto_condition:
            self.busy_reg = 0
        if self.state == 'READ1' and not old_scl and self.sSCL:
            self.dout_reg = self.sSDA


    def step(self, i):
        o = {p: None for p in self.OUTPUT_PORTS}
        self.ack_reg = 0
        if not int(i.get('nReset', 1)):
            self.reset()
        elif int(i.get('rst', 0)):
            self.reset()
        else:
            if i['ena']:
                sample, sta, sto, old_scl, old_sda = self._update_filter(i)
            else:
                sample, sta, sto, old_scl, old_sda = (0, 0, 0, self.sSCL, self.sSDA)
                self.filter_counter = 0
            scl_sync = int(self._scl_released() and old_scl and not self.sSCL)
            wait = int(self._scl_released() and not self.sSCL)
            clk_en, sync_reload = self._timing_tick(i, wait, scl_sync)
            if sync_reload:
                scl_sync = 1
            self._update_status(sta, sto, old_scl, old_sda)
            self._command_fsm(i, clk_en, sto, scl_sync)
            if self.al_reg:
                self.state = 'IDLE'
            self._update_probes(clk_en, self.cnt == 0, sample, scl_sync, sta, sto)
        scl_oen, sda_oen = self._outputs_for_state()
        if self.al_reg:
            scl_oen = 1
            sda_oen = 1
        o['cmd_ack'] = int(self.ack_reg)
        o['busy'] = int(self.busy_reg)
        o['al'] = int(self.al_reg)
        o['dout'] = int(self.dout_reg)
        o['scl_o'] = 0
        o['scl_oen'] = int(scl_oen) & 1
        o['sda_o'] = 0
        o['sda_oen'] = int(sda_oen) & 1
        return o
