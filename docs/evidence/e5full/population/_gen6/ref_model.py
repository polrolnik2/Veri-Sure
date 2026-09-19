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
        self.state = 'IDLE'
        self.cmd_latched = 0
        self.tx = 1
        self.c1_scl = 1
        self.c2_scl = 1
        self.c1_sda = 1
        self.c2_sda = 1
        self.f_scl = [1, 1, 1]
        self.f_sda = [1, 1, 1]
        self.s_scl = 1
        self.s_sda = 1
        self.d_scl = 1
        self.d_sda = 1
        self.cnt = 0
        self.fc = 0
        self.cmd_ack_r = 0
        self.busy_r = 0
        self.al_r = 0
        self.dout_r = 0
        self.scl_oen_r = 1
        self.sda_oen_r = 1
        self._set_probes(0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)


    def _reset(self):
        self.state = 'IDLE'
        self.cmd_latched = 0
        self.tx = 1
        self.c1_scl = 1
        self.c2_scl = 1
        self.c1_sda = 1
        self.c2_sda = 1
        self.f_scl = [1, 1, 1]
        self.f_sda = [1, 1, 1]
        self.s_scl = 1
        self.s_sda = 1
        self.d_scl = 1
        self.d_sda = 1
        self.cnt = 0
        self.fc = 0
        self.cmd_ack_r = 0
        self.busy_r = 0
        self.al_r = 0
        self.dout_r = 0
        self.scl_oen_r = 1
        self.sda_oen_r = 1


    def _majority(self, h):
        return 1 if (h[0] + h[1] + h[2]) >= 2 else 0


    def _sample_filter(self, i):
        self.c1_scl = i['scl_i'] & 1
        self.c2_scl = self.c1_scl
        self.c1_sda = i['sda_i'] & 1
        self.c2_sda = self.c1_sda
        interval = (i['clk_cnt'] & 0xffff) >> 2
        if interval < 1:
            interval = 1
        sampled = False
        if not i['ena']:
            self.fc = 0
        elif self.fc <= 0:
            sampled = True
            self.fc = interval - 1
        else:
            self.fc -= 1
        old_scl = self.s_scl
        old_sda = self.s_sda
        self.d_scl = old_scl
        self.d_sda = old_sda
        if sampled:
            self.f_scl = [self.f_scl[1], self.f_scl[2], self.c2_scl]
            self.f_sda = [self.f_sda[1], self.f_sda[2], self.c2_sda]
            self.s_scl = self._majority(self.f_scl)
            self.s_sda = self._majority(self.f_sda)
        self.filter_expired = bool(sampled)
        self.filtered_scl_rising = bool((not old_scl) and self.s_scl)
        self.filtered_scl_falling = bool(old_scl and (not self.s_scl))
        self.sta_condition = bool((not self.s_sda) and self.d_sda and self.s_scl)
        self.sto_condition = bool(self.s_sda and (not self.d_sda) and self.s_scl)
        if self.sta_condition:
            self.busy_r = 1
        if self.sto_condition:
            self.busy_r = 0
        if self.filtered_scl_rising:
            self.dout_r = self.s_sda


    def _divider(self, i):
        reload_value = i['clk_cnt'] & 0xffff
        released_scl = bool(self.scl_oen_r)
        self.slave_wait_r = bool(released_scl and not self.s_scl)
        self.scl_sync_r = bool(released_scl and self.filtered_scl_falling)
        self.cnt_zero_r = bool(self.cnt == 0)
        self.clk_en_r = 0
        if not i['ena']:
            self.cnt = reload_value
            return
        if self.slave_wait_r:
            return
        if self.scl_sync_r or self.cnt == 0:
            self.cnt = reload_value
            self.clk_en_r = 1
        else:
            self.cnt -= 1


    def _outputs_for_state(self):
        scl = 1
        sda = 1
        if self.state in ('START2', 'STOP0', 'READ2', 'WRITE2'):
            scl = 0
        if self.state == 'START1':
            sda = 0
        elif self.state in ('STOP0', 'STOP1'):
            sda = 0
        elif self.state in ('WRITE0', 'WRITE1'):
            sda = 0 if not self.tx else 1
        self.scl_oen_r = scl
        self.sda_oen_r = sda


    def _fsm(self, i):
        self.cmd_ack_r = 0
        active = self.state != 'IDLE'
        if active and self.sto_condition and self.cmd_latched != 2:
            self.al_r = 1
            self.state = 'IDLE'
            self.scl_oen_r = 1
            self.sda_oen_r = 1
            return
        if self.state == 'WRITE1' and self.tx and not self.s_sda:
            self.al_r = 1
            self.state = 'IDLE'
            self.scl_oen_r = 1
            self.sda_oen_r = 1
            return
        if not i['ena'] or not self.clk_en_r:
            return
        if self.state == 'IDLE':
            c = i['cmd'] & 0xf
            if c in (1, 2, 4, 8):
                self.cmd_latched = c
                self.tx = i['din'] & 1
                if c == 1:
                    self.state = 'START0'
                elif c == 2:
                    self.state = 'STOP0'
                elif c == 4:
                    self.state = 'WRITE0'
                else:
                    self.state = 'READ0'
        elif self.state == 'START0':
            self.state = 'START1'
        elif self.state == 'START1':
            self.state = 'START2'
        elif self.state == 'START2':
            self.state = 'IDLE'
            self.cmd_ack_r = 1
        elif self.state == 'STOP0':
            self.state = 'STOP1'
        elif self.state == 'STOP1':
            self.state = 'STOP2'
        elif self.state == 'STOP2':
            self.state = 'IDLE'
            self.cmd_ack_r = 1
        elif self.state == 'READ0':
            self.state = 'READ1'
        elif self.state == 'READ1':
            self.state = 'READ2'
        elif self.state == 'READ2':
            self.state = 'IDLE'
            self.cmd_ack_r = 1
        elif self.state == 'WRITE0':
            self.state = 'WRITE1'
        elif self.state == 'WRITE1':
            self.state = 'WRITE2'
        elif self.state == 'WRITE2':
            self.state = 'IDLE'
            self.cmd_ack_r = 1


    def _set_probes(self, *_):
        self.cscl = bool(self.c2_scl)
        self.csda = bool(self.c2_sda)
        self.sscl = bool(self.s_scl)
        self.ssda = bool(self.s_sda)
        self.dscl = bool(self.d_scl)
        self.dsda = bool(self.d_sda)
        self.fscl = bool(self.f_scl[-1])
        self.fsda = bool(self.f_sda[-1])
        self.filter_cnt = bool(getattr(self, 'filter_expired', False))
        self.cnt_zero = bool(getattr(self, 'cnt_zero_r', False))
        self.clk_en = bool(getattr(self, 'clk_en_r', False))
        self.slave_wait = bool(getattr(self, 'slave_wait_r', False))
        self.scl_sync = bool(getattr(self, 'scl_sync_r', False))
        self.sta_condition = bool(getattr(self, 'sta_condition', False))
        self.sto_condition = bool(getattr(self, 'sto_condition', False))
        self.sda_chk = bool(self.state == 'WRITE1' and self.tx)
        self.idle = bool(self.state == 'IDLE')
        self.fsm_active = bool(self.state != 'IDLE')
        self.start_sequence = bool(self.state.startswith('START'))
        self.stop_sequence = bool(self.state.startswith('STOP'))
        self.read_sequence = bool(self.state.startswith('READ'))
        self.write_sequence = bool(self.state.startswith('WRITE'))
        self.i2c_master_bit_ctrl = True


    def step(self, i):
        o = {p: None for p in self.OUTPUT_PORTS}
        if not i['nReset']:
            self._reset()
        else:
            if i['rst']:
                self._reset()
            else:
                self._sample_filter(i)
                self._outputs_for_state()
                self._divider(i)
                self._fsm(i)
                self._outputs_for_state()
        self._set_probes()
        o['cmd_ack'] = self.cmd_ack_r & 1
        o['busy'] = self.busy_r & 1
        o['al'] = self.al_r & 1
        o['dout'] = self.dout_r & 1
        o['scl_o'] = 0
        o['scl_oen'] = self.scl_oen_r & 1
        o['sda_o'] = 0
        o['sda_oen'] = self.sda_oen_r & 1
        return o
