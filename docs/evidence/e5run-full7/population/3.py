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
        self.cscl_1 = 1
        self.cscl_2 = 1
        self.csda_1 = 1
        self.csda_2 = 1
        self.fscl_hist = [1, 1, 1]
        self.fsda_hist = [1, 1, 1]
        self.sscl = 1
        self.ssda = 1
        self.dscl = 1
        self.dsda = 1
        self.busy_reg = 0
        self.al_reg = 0
        self.dout_reg = 0
        self.ack_reg = 0
        self._set_probes(0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 0, 0)


    def _set_probes(self, clk_en, cnt_zero, filter_tick, fscl, fsda,
                    sta, sscl, ssda, dscl, dsda, sto, scl_sync):
        self.idle = self.state == 'IDLE'
        self.clk_en = bool(clk_en)
        self.cnt_zero = bool(cnt_zero)
        self.filter_cnt = bool(filter_tick)
        self.fscl = bool(fscl)
        self.fsda = bool(fsda)
        self.sscl = bool(sscl)
        self.ssda = bool(ssda)
        self.dscl = bool(dscl)
        self.dsda = bool(dsda)
        self.sta_condition = bool(sta)
        self.sto_condition = bool(sto)
        self.active_command = self.state != 'IDLE'
        self.start_sequence = self.state.startswith('START_')
        self.stop_sequence = self.state.startswith('STOP_')
        self.read_sequence = self.state.startswith('READ_')
        self.write_sequence = self.state.startswith('WRITE_')
        self.write_stable_high_phase = self.state == 'WRITE_HIGH'
        self.read_sample_window = self.state == 'READ_HIGH'
        self.sda_chk = self.state == 'WRITE_HIGH' and bool(self.din_latched)
        self.scl_sync = bool(scl_sync)
        self.cscl = bool(self.cscl_2)
        self.csda = bool(self.csda_2)
        self.slave_wait = bool(self.state in ('START_PULL', 'STOP_SCL_HIGH',
                                              'STOP_RELEASE', 'READ_HIGH',
                                              'WRITE_HIGH') and self.scl_oen == 1
                               and self.sscl == 0)


    def _outputs_for_state(self):
        scl = 1
        sda = 1
        if self.state == 'START_PULL':
            scl, sda = 1, 0
        elif self.state == 'START_LOW':
            scl, sda = 0, 0
        elif self.state == 'STOP_LOW':
            scl, sda = 0, 0
        elif self.state == 'STOP_SCL_HIGH':
            scl, sda = 1, 0
        elif self.state == 'STOP_RELEASE':
            scl, sda = 1, 1
        elif self.state == 'READ_HIGH':
            scl, sda = 1, 1
        elif self.state == 'READ_LOW':
            scl, sda = 0, 1
        elif self.state == 'WRITE_LOW':
            scl, sda = 0, 0 if self.din_latched == 0 else 1
        elif self.state == 'WRITE_HIGH':
            scl, sda = 1, 0 if self.din_latched == 0 else 1
        elif self.state == 'WRITE_END':
            scl, sda = 0, 0 if self.din_latched == 0 else 1
        return scl, sda


    def step(self, i):
        o = {p: None for p in self.OUTPUT_PORTS}

        if not i.get('nReset', 1):
            self.reset()
        elif i.get('rst', 0):
            self.reset()
        else:
            self.ack_reg = 0

            old_sscl = self.sscl
            old_ssda = self.ssda

            self.cscl_2 = self.cscl_1
            self.cscl_1 = int(i.get('scl_i', 1)) & 1
            self.csda_2 = self.csda_1
            self.csda_1 = int(i.get('sda_i', 1)) & 1

            filter_tick = 0
            sampled_scl = 0
            sampled_sda = 0
            if i.get('ena', 0):
                interval = int(i.get('clk_cnt', 0)) >> 2
                if interval < 1:
                    interval = 1
                if self.filter_counter == 0:
                    filter_tick = 1
                    self.filter_counter = interval - 1
                    self.fscl_hist = [self.fscl_hist[1], self.fscl_hist[2], self.cscl_2]
                    self.fsda_hist = [self.fsda_hist[1], self.fsda_hist[2], self.csda_2]
                    sampled_scl = 1
                    sampled_sda = 1
                else:
                    self.filter_counter -= 1
            else:
                self.filter_counter = 0

            if filter_tick:
                self.sscl = 1 if sum(self.fscl_hist) >= 2 else 0
                self.ssda = 1 if sum(self.fsda_hist) >= 2 else 0

            self.dscl = old_sscl
            self.dsda = old_ssda
            sta = int((self.ssda == 0) and (old_ssda == 1) and (self.sscl == 1))
            sto = int((self.ssda == 1) and (old_ssda == 0) and (self.sscl == 1))
            sync = int((old_sscl == 1) and (self.sscl == 0) and
                       (self.scl_oen == 1 if hasattr(self, 'scl_oen') else self.state in
                        ('START_PULL', 'STOP_SCL_HIGH', 'STOP_RELEASE', 'READ_HIGH', 'WRITE_HIGH')))

            if sta:
                self.busy_reg = 1
            if sto:
                self.busy_reg = 0

            scl_oen, sda_oen = self._outputs_for_state()
            slave_wait = bool(scl_oen == 1 and self.sscl == 0 and
                              self.state in ('START_PULL', 'STOP_SCL_HIGH',
                                             'STOP_RELEASE', 'READ_HIGH', 'WRITE_HIGH'))

            if self.state != 'IDLE' and sto and self.state not in ('STOP_LOW', 'STOP_SCL_HIGH', 'STOP_RELEASE'):
                self.al_reg = 1
                self.state = 'IDLE'
            elif self.state == 'WRITE_HIGH' and self.din_latched and self.ssda == 0:
                self.al_reg = 1
                self.state = 'IDLE'
            elif i.get('ena', 0):
                cnt_zero = self.cnt == 0
                clk_en = int(cnt_zero and not slave_wait and not sync)
                if cnt_zero or sync:
                    self.cnt = int(i.get('clk_cnt', 0)) & 0xffff
                else:
                    self.cnt = (self.cnt - 1) & 0xffff

                if clk_en:
                    if self.state == 'IDLE':
                        c = int(i.get('cmd', 0)) & 0xf
                        if c in (1, 2, 4, 8):
                            self.cmd_latched = c
                            self.din_latched = int(i.get('din', 0)) & 1
                            if c == 1:
                                self.state = 'START_RELEASE'
                            elif c == 2:
                                self.state = 'STOP_LOW'
                            elif c == 4:
                                self.state = 'WRITE_LOW'
                            else:
                                self.state = 'READ_LOW'
                    elif self.state == 'START_RELEASE':
                        self.state = 'START_PULL'
                    elif self.state == 'START_PULL':
                        self.state = 'START_LOW'
                    elif self.state == 'START_LOW':
                        self.state = 'IDLE'
                        self.ack_reg = 1
                    elif self.state == 'STOP_LOW':
                        self.state = 'STOP_SCL_HIGH'
                    elif self.state == 'STOP_SCL_HIGH':
                        self.state = 'STOP_RELEASE'
                    elif self.state == 'STOP_RELEASE':
                        self.state = 'IDLE'
                        self.ack_reg = 1
                    elif self.state == 'READ_LOW':
                        self.state = 'READ_HIGH'
                    elif self.state == 'READ_HIGH':
                        self.state = 'READ_END'
                    elif self.state == 'READ_END':
                        self.state = 'IDLE'
                        self.ack_reg = 1
                    elif self.state == 'WRITE_LOW':
                        self.state = 'WRITE_HIGH'
                    elif self.state == 'WRITE_HIGH':
                        self.state = 'WRITE_END'
                    elif self.state == 'WRITE_END':
                        self.state = 'IDLE'
                        self.ack_reg = 1
            else:
                self.cnt = int(i.get('clk_cnt', 0)) & 0xffff

            if self.sscl and not old_sscl:
                self.dout_reg = self.ssda

            scl_oen, sda_oen = self._outputs_for_state()
            self.scl_oen = scl_oen
            self.sda_oen = sda_oen
            self._set_probes(int(self.cnt == 0), int(self.cnt == 0), filter_tick,
                             sampled_scl, sampled_sda, sta, self.sscl, self.ssda,
                             self.dscl, self.dsda, sto, sync)
            self.slave_wait = bool(self.scl_oen == 1 and self.sscl == 0 and
                                   self.state in ('START_PULL', 'STOP_SCL_HIGH',
                                                  'STOP_RELEASE', 'READ_HIGH', 'WRITE_HIGH'))

        o['cmd_ack'] = int(self.ack_reg) & 1
        o['busy'] = int(self.busy_reg) & 1
        o['al'] = int(self.al_reg) & 1
        o['dout'] = int(self.dout_reg) & 1
        o['scl_o'] = 0
        o['scl_oen'] = int(getattr(self, 'scl_oen', 1)) & 1
        o['sda_o'] = 0
        o['sda_oen'] = int(getattr(self, 'sda_oen', 1)) & 1
        return o
