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
        self.reset_state()


    def reset_state(self):
        self.state = 'idle'
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
        self.ack_reg = 0
        self.clk_en_reg = 0
        self.filter_tick_reg = 0
        self.scl_sync_reg = 0
        self.slave_wait_reg = 0
        self.sda_chk_reg = 0
        self.update_probes()


    def majority(self, h):
        return 1 if (h[0] + h[1] + h[2]) >= 2 else 0


    def filter_inputs(self, i, enabled):
        old_scl = self.sSCL
        old_sda = self.sSDA
        self.cSCL1 = i['scl_i'] & 1
        self.cSCL2 = self.cSCL1
        self.cSDA1 = i['sda_i'] & 1
        self.cSDA2 = self.cSDA1
        self.filter_tick_reg = 0
        if not enabled:
            self.filter_counter = 0
        else:
            interval = (i['clk_cnt'] & 0xffff) >> 2
            if interval == 0 or self.filter_counter == 0:
                self.filter_tick_reg = 1
                self.filter_counter = interval
                self.fSCL = [self.fSCL[1], self.fSCL[2], self.cSCL2]
                self.fSDA = [self.fSDA[1], self.fSDA[2], self.cSDA2]
                self.sSCL = self.majority(self.fSCL)
                self.sSDA = self.majority(self.fSDA)
            else:
                self.filter_counter -= 1
        self.dSCL = old_scl
        self.dSDA = old_sda
        rising_scl = (not old_scl) and self.sSCL
        sta = (not self.sSDA) and self.dSDA and self.sSCL
        sto = self.sSDA and (not self.dSDA) and self.sSCL
        if rising_scl:
            self.dout_reg = self.sSDA
        return bool(sta), bool(sto), bool(rising_scl)


    def timing(self, i, enabled):
        self.clk_en_reg = 0
        if not enabled:
            self.cnt = i['clk_cnt'] & 0xffff
            self.slave_wait_reg = 0
            return
        released_scl = self.output_values()[0] == 1
        self.slave_wait_reg = bool(released_scl and not self.sSCL)
        falling_sync = bool(released_scl and self.dSCL and not self.sSCL)
        self.scl_sync_reg = 1 if falling_sync else 0
        if self.slave_wait_reg:
            return
        if falling_sync or self.cnt == 0:
            self.clk_en_reg = 1
            self.cnt = i['clk_cnt'] & 0xffff
        else:
            self.cnt = (self.cnt - 1) & 0xffff


    def bus_events(self, sta, sto):
        if sta:
            self.busy_reg = 1
        if sto:
            self.busy_reg = 0
        unexpected_stop = sto and self.state != 'idle' and self.cmd_latched != 0x2
        arbitration = bool(self.sda_chk_reg and self.sSDA == 0)
        if unexpected_stop or arbitration:
            self.al_reg = 1
            self.state = 'idle'
            self.sda_chk_reg = 0


    def command_fsm(self, i):
        if self.al_reg or not self.clk_en_reg:
            return
        if self.state == 'idle':
            cmd = i['cmd'] & 0xf
            if cmd in (0x1, 0x2, 0x4, 0x8):
                self.cmd_latched = cmd
                self.din_latched = i['din'] & 1
                if cmd == 0x1:
                    self.state = 'start_release'
                elif cmd == 0x2:
                    self.state = 'stop_drive'
                elif cmd == 0x4:
                    self.state = 'write_low'
                else:
                    self.state = 'read_low'
            return
        if self.state == 'start_release':
            self.state = 'start_sda_low'
        elif self.state == 'start_sda_low':
            self.state = 'start_scl_low'
        elif self.state == 'start_scl_low':
            self.state = 'idle'
            self.ack_reg = 1
        elif self.state == 'stop_drive':
            self.state = 'stop_scl_release'
        elif self.state == 'stop_scl_release':
            if self.sSCL:
                self.state = 'stop_sda_release'
        elif self.state == 'stop_sda_release':
            self.state = 'idle'
            self.ack_reg = 1
        elif self.state == 'read_low':
            self.state = 'read_high'
        elif self.state == 'read_high':
            if self.sSCL:
                self.state = 'read_scl_low'
        elif self.state == 'read_scl_low':
            self.state = 'idle'
            self.ack_reg = 1
        elif self.state == 'write_low':
            self.state = 'write_high'
        elif self.state == 'write_high':
            self.sda_chk_reg = bool(self.din_latched)
            if self.sSCL:
                self.state = 'write_scl_low'
        elif self.state == 'write_scl_low':
            self.sda_chk_reg = 0
            self.state = 'idle'
            self.ack_reg = 1


    def output_values(self):
        scl_oen = 1
        sda_oen = 1
        if self.state in ('start_scl_low', 'read_scl_low', 'write_low', 'write_scl_low', 'stop_drive'):
            scl_oen = 0
        if self.state in ('start_sda_low', 'stop_drive'):
            sda_oen = 0
        elif self.state in ('write_low', 'write_high', 'write_scl_low'):
            sda_oen = 0 if self.din_latched == 0 else 1
        return scl_oen, sda_oen


    def update_probes(self):
        self.idle = self.state == 'idle'
        self.clk_en = bool(self.clk_en_reg)
        self.cnt_zero = self.cnt == 0
        self.slave_wait = bool(self.slave_wait_reg)
        self.scl_sync = bool(self.scl_sync_reg)
        self.cscl = bool(self.cSCL2)
        self.csda = bool(self.cSDA2)
        self.filter_cnt = bool(self.filter_tick_reg)
        self.fscl = bool(self.filter_tick_reg)
        self.fsda = bool(self.filter_tick_reg)
        self.sscl = bool(self.sSCL)
        self.ssda = bool(self.sSDA)
        self.dscl = bool(self.dSCL)
        self.dsda = bool(self.dSDA)
        self.sta_condition = bool((not self.sSDA) and self.dSDA and self.sSCL)
        self.sto_condition = bool(self.sSDA and (not self.dSDA) and self.sSCL)
        self.active_command = self.state != 'idle'
        self.sda_chk = bool(self.sda_chk_reg)
        self.start_sequence = self.state.startswith('start_')
        self.stop_sequence = self.state.startswith('stop_')
        self.read_sequence = self.state.startswith('read_')
        self.write_sequence = self.state.startswith('write_')
        self.write_stable_high_phase = self.state == 'write_high'
        self.read_sample_window = self.state == 'read_high'


    def step(self, i):
        o = {p: None for p in self.OUTPUT_PORTS}
        if not (i.get('nReset', 1) & 1):
            self.reset_state()
        elif i.get('rst', 0) & 1:
            self.reset_state()
        else:
            self.ack_reg = 0
            enabled = bool(i.get('ena', 0) & 1)
            sta, sto, _ = self.filter_inputs(i, enabled)
            self.timing(i, enabled)
            self.bus_events(sta, sto)
            self.command_fsm(i)
            if not enabled:
                self.state = self.state if self.state == 'idle' else self.state
            self.update_probes()
        scl_oen, sda_oen = self.output_values()
        o['cmd_ack'] = self.ack_reg & 1
        o['busy'] = self.busy_reg & 1
        o['al'] = self.al_reg & 1
        o['dout'] = self.dout_reg & 1
        o['scl_o'] = 0
        o['scl_oen'] = scl_oen & 1
        o['sda_o'] = 0
        o['sda_oen'] = sda_oen & 1
        return o
