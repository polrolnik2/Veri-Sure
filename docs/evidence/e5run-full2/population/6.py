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
        self.cnt = 0
        self.filter_counter = 0
        self.sync_scl = 1
        self.sync_scl_d = 1
        self.sync_sda = 1
        self.sync_sda_d = 1
        self.f_scl = [1, 1, 1]
        self.f_sda = [1, 1, 1]
        self.s_scl = 1
        self.s_sda = 1
        self.d_scl = 1
        self.d_sda = 1
        self.dout_reg = 0
        self.busy_reg = 0
        self.al_reg = 0
        self.cmd_ack_reg = 0
        self.scl_oen_reg = 1
        self.sda_oen_reg = 1
        self.clk_en_probe = 0
        self.cnt_zero_probe = 0
        self.filter_expired_probe = 0
        self.slave_wait_probe = 0
        self.scl_sync_probe = 0
        self.filtered_rise_probe = 0
        self.sta_probe = 0
        self.sto_probe = 0
        self.sda_chk_probe = 0
        self._update_probes()


    def _majority(self, values):
        return 1 if (values[0] + values[1] + values[2]) >= 2 else 0


    def _filter_step(self, i):
        self.sync_scl_d = self.sync_scl
        self.sync_sda_d = self.sync_sda
        self.sync_scl = 1 if i['scl_i'] else 0
        self.sync_sda = 1 if i['sda_i'] else 0
        self.filter_expired_probe = 0
        if not i['ena']:
            self.filter_counter = 0
            return
        interval = (i['clk_cnt'] & 0xffff) >> 2
        if interval == 0 or self.filter_counter == 0:
            self.filter_counter = interval
            self.f_scl = [self.f_scl[1], self.f_scl[2], self.sync_scl]
            self.f_sda = [self.f_sda[1], self.f_sda[2], self.sync_sda]
            self.filter_expired_probe = 1
        else:
            self.filter_counter = (self.filter_counter - 1) & 0xffff
        old_scl = self.s_scl
        old_sda = self.s_sda
        self.s_scl = self._majority(self.f_scl)
        self.s_sda = self._majority(self.f_sda)
        self.d_scl = old_scl
        self.d_sda = old_sda
        self.filtered_rise_probe = 1 if (self.s_scl and not old_scl) else 0
        self.sta_probe = 1 if ((not self.s_sda) and self.d_sda and self.s_scl) else 0
        self.sto_probe = 1 if (self.s_sda and (not self.d_sda) and self.s_scl) else 0


    def _timing_step(self, i):
        self.clk_en_probe = 0
        self.cnt_zero_probe = 1 if self.cnt == 0 else 0
        if not i['ena']:
            self.cnt = i['clk_cnt'] & 0xffff
            return
        released_scl = self.scl_oen_reg == 1
        self.slave_wait_probe = 1 if (released_scl and not self.s_scl) else 0
        if self.slave_wait_probe:
            return
        falling_sync = released_scl and self.d_scl and not self.s_scl
        self.scl_sync_probe = 1 if falling_sync else 0
        if falling_sync or self.cnt == 0:
            self.cnt = i['clk_cnt'] & 0xffff
            self.clk_en_probe = 1
        else:
            self.cnt = (self.cnt - 1) & 0xffff


    def _phase_outputs(self, phase):
        if phase == 'START0':
            return 1, 1
        if phase == 'START1':
            return 1, 0
        if phase == 'START2':
            return 0, 0
        if phase == 'STOP0':
            return 0, 0
        if phase == 'STOP1':
            return 1, 0
        if phase == 'STOP2':
            return 1, 1
        if phase == 'READ0':
            return 0, 1
        if phase == 'READ1':
            return 1, 1
        if phase == 'READ2':
            return 0, 1
        if phase == 'WRITE0':
            return 0, 1 if self.din_latched else 0
        if phase == 'WRITE1':
            return 1, 1 if self.din_latched else 0
        if phase == 'WRITE2':
            return 0, 1 if self.din_latched else 0
        return 1, 1


    def _fsm_step(self, i):
        self.cmd_ack_reg = 0
        if self.sto_probe and self.state != 'IDLE' and self.state not in ('STOP0', 'STOP1', 'STOP2'):
            self.al_reg = 1
            self.state = 'IDLE'
            self.scl_oen_reg = 1
            self.sda_oen_reg = 1
            return
        if self.state.startswith('WRITE') and self.state == 'WRITE1' and self.din_latched and not self.s_sda:
            self.al_reg = 1
            self.state = 'IDLE'
            self.scl_oen_reg = 1
            self.sda_oen_reg = 1
            return
        if not i['ena'] or not self.clk_en_probe:
            return
        if self.state == 'IDLE':
            command = i['cmd'] & 0xf
            if command == 1:
                self.cmd_latched = command
                self.state = 'START0'
            elif command == 2:
                self.cmd_latched = command
                self.state = 'STOP0'
            elif command == 4:
                self.cmd_latched = command
                self.din_latched = 1 if i['din'] else 0
                self.state = 'WRITE0'
            elif command == 8:
                self.cmd_latched = command
                self.state = 'READ0'
            return
        nxt = {
            'START0': 'START1',
            'START1': 'START2',
            'STOP0': 'STOP1',
            'STOP1': 'STOP2',
            'READ0': 'READ1',
            'READ1': 'READ2',
            'WRITE0': 'WRITE1',
            'WRITE1': 'WRITE2'
        }
        if self.state in ('START2', 'STOP2', 'READ2', 'WRITE2'):
            self.cmd_ack_reg = 1
            if self.state == 'START2':
                self.busy_reg = 1
            elif self.state == 'STOP2':
                self.busy_reg = 0
            self.state = 'IDLE'
        elif self.state in nxt:
            if self.state in ('STOP1', 'READ1') and not self.s_scl:
                return
            self.state = nxt[self.state]


    def _update_outputs(self):
        phase = self.state
        if phase == 'IDLE' and self.cmd_ack_reg:
            phase = 'IDLE'
        self.scl_oen_reg, self.sda_oen_reg = self._phase_outputs(phase)
        if self.state == 'IDLE' and self.al_reg:
            self.scl_oen_reg = 1
            self.sda_oen_reg = 1


    def _update_probes(self):
        self.idle = self.state == 'IDLE'
        self.cnt_zero = bool(self.cnt_zero_probe)
        self.clk_en = bool(self.clk_en_probe)
        self.slave_wait = bool(self.slave_wait_probe)
        self.scl_sync = bool(self.scl_sync_probe)
        self.cscl = bool(self.sync_scl)
        self.csda = bool(self.sync_sda)
        self.filter_cnt = bool(self.filter_counter)
        self.filter_cnt_expired = bool(self.filter_expired_probe)
        self.fscl = bool(self._majority(self.f_scl))
        self.fsda = bool(self._majority(self.f_sda))
        self.sscl = bool(self.s_scl)
        self.ssda = bool(self.s_sda)
        self.dscl = bool(self.d_scl)
        self.dsda = bool(self.d_sda)
        self.sta_condition = bool(self.sta_probe)
        self.sto_condition = bool(self.sto_probe)
        self.active_command = self.state != 'IDLE'
        self.sda_chk = self.state == 'WRITE1' and bool(self.din_latched)
        self.filtered_scl_rise = bool(self.filtered_rise_probe)
        self.start_sequence = self.state.startswith('START')
        self.stop_sequence = self.state.startswith('STOP')
        self.read_sequence = self.state.startswith('READ')
        self.write_sequence = self.state.startswith('WRITE')


    def step(self, i):
        o = {p: None for p in self.OUTPUT_PORTS}
        if not i['nReset']:
            self.reset()
        elif i['rst']:
            self.reset()
        else:
            old_scl = self.s_scl
            self._filter_step(i)
            if self.filtered_rise_probe:
                self.dout_reg = 1 if self.s_sda else 0
            if self.sta_probe:
                self.busy_reg = 1
            if self.sto_probe:
                self.busy_reg = 0
            self._timing_step(i)
            self._fsm_step(i)
            self._update_outputs()
            self._update_probes()
        o['cmd_ack'] = 1 if self.cmd_ack_reg else 0
        o['busy'] = 1 if self.busy_reg else 0
        o['al'] = 1 if self.al_reg else 0
        o['dout'] = 1 if self.dout_reg else 0
        o['scl_o'] = 0
        o['scl_oen'] = 1 if self.scl_oen_reg else 0
        o['sda_o'] = 0
        o['sda_oen'] = 1 if self.sda_oen_reg else 0
        return o
