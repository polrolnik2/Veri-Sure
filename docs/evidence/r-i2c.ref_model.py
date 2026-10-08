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
    LATENCY_CYCLES = 0

    def _ensure_state(self):
        if not getattr(self, '_state_ready', False):
            self._reset_state()


    def _reset_state(self):
        self._state_ready = True
        self._phase = 'idle'
        self._command = 0
        self._cmd_ack = 0
        self._busy = 0
        self._al = 0
        self._dout = 0
        self._cnt = 0
        self._filter_cnt = 0
        self._cSCL0 = 1
        self._cSCL1 = 1
        self._cSDA0 = 1
        self._cSDA1 = 1
        self._fSCL = [1, 1, 1]
        self._fSDA = [1, 1, 1]
        self._dSCL = 1
        self._dSDA = 1


    def reset(self):
        self._reset_state()


    def _majority(self, samples):
        return 1 if samples[0] + samples[1] + samples[2] >= 2 else 0


    def _phase_outputs(self, din):
        din = self.mask(din, 1)
        scl_oen = 1
        sda_oen = 1
        sda_chk = 0

        if self._phase == 'start_b':
            sda_oen = 0
        elif self._phase == 'start_c':
            scl_oen = 0
            sda_oen = 0
        elif self._phase == 'stop_a':
            scl_oen = 0
            sda_oen = 0
        elif self._phase == 'stop_b':
            scl_oen = 1
            sda_oen = 0
        elif self._phase == 'stop_c':
            scl_oen = 1
            sda_oen = 1
        elif self._phase == 'read_a' or self._phase == 'read_d':
            scl_oen = 0
            sda_oen = 1
        elif self._phase == 'read_b' or self._phase == 'read_c':
            scl_oen = 1
            sda_oen = 1
        elif self._phase == 'write_a':
            scl_oen = 0
            sda_oen = din
        elif self._phase == 'write_b' or self._phase == 'write_c':
            scl_oen = 1
            sda_oen = din
            if din == 1:
                sda_chk = 1
        elif self._phase == 'write_d':
            scl_oen = 0
            sda_oen = din

        return scl_oen, sda_oen, sda_chk


    def _bus_events(self, din):
        sSCL = self._majority(self._fSCL)
        sSDA = self._majority(self._fSDA)
        scl_oen, sda_oen, sda_chk = self._phase_outputs(din)

        return {
            'sSCL': sSCL,
            'sSDA': sSDA,
            'start': 1 if self._dSDA == 1 and sSDA == 0 and sSCL == 1 else 0,
            'stop': 1 if self._dSDA == 0 and sSDA == 1 and sSCL == 1 else 0,
            'scl_rise': 1 if self._dSCL == 0 and sSCL == 1 else 0,
            'scl_sync': 1 if scl_oen == 1 and self._dSCL == 1 and sSCL == 0 else 0,
            'slave_wait': 1 if scl_oen == 1 and sSCL == 0 else 0,
            'sda_check': sda_chk,
            'sda_oen': sda_oen
        }


    def _update_inputs(self, scl_i, sda_i, ena, clk_cnt):
        scl_i = self.mask(scl_i, 1)
        sda_i = self.mask(sda_i, 1)
        clk_cnt = self.mask(clk_cnt, 16)

        old_cSCL0 = self._cSCL0
        old_cSDA0 = self._cSDA0
        old_cSCL1 = self._cSCL1
        old_cSDA1 = self._cSDA1

        self._dSCL = self._majority(self._fSCL)
        self._dSDA = self._majority(self._fSDA)

        self._cSCL0 = scl_i
        self._cSCL1 = old_cSCL0
        self._cSDA0 = sda_i
        self._cSDA1 = old_cSDA0

        if ena:
            if self._filter_cnt == 0:
                self._fSCL = [self._fSCL[1], self._fSCL[2], old_cSCL1]
                self._fSDA = [self._fSDA[1], self._fSDA[2], old_cSDA1]
                self._filter_cnt = self.mask(clk_cnt >> 2, 16)
            else:
                self._filter_cnt = self.mask(self._filter_cnt - 1, 16)
        else:
            self._filter_cnt = 0


    def _timing_tick(self, ena, clk_cnt, scl_sync, slave_wait):
        clk_cnt = self.mask(clk_cnt, 16)

        if not ena:
            self._cnt = clk_cnt
            return 0

        # A stretched SCL is a hard stop for the bit-time FSM.  Do not let
        # the edge which first notices the synchronized low level consume a
        # timing tick; progression resumes only after the slave_wait
        # condition has cleared.
        if slave_wait:
            return 0

        if scl_sync:
            self._cnt = clk_cnt
            return 1

        if self._cnt == 0:
            self._cnt = clk_cnt
            return 1

        self._cnt = self.mask(self._cnt - 1, 16)
        return 0


    def _advance_fsm(self, cmd, sSCL):
        if self._phase == 'idle':
            if cmd == 1:
                self._phase = 'start_a'
                self._command = 1
            elif cmd == 2:
                self._phase = 'stop_a'
                self._command = 2
            elif cmd == 4:
                self._phase = 'write_a'
                self._command = 4
            elif cmd == 8:
                self._phase = 'read_a'
                self._command = 8
            return

        if self._phase == 'start_a':
            if sSCL == 1:
                self._phase = 'start_b'
        elif self._phase == 'start_b':
            self._phase = 'start_c'
        elif self._phase == 'start_c':
            self._phase = 'idle'
            self._command = 0
            self._cmd_ack = 1
        elif self._phase == 'stop_a':
            # SDA is already asserted low in stop_a.  The next phase is
            # entered once SCL is observed high, so that releasing SCL
            # cannot occur while it is still being held low externally.
            if sSCL == 1:
                self._phase = 'stop_b'
        elif self._phase == 'stop_b':
            if sSCL == 1:
                self._phase = 'stop_c'
        elif self._phase == 'stop_c':
            self._phase = 'idle'
            self._command = 0
            self._cmd_ack = 1
        elif self._phase == 'read_a':
            self._phase = 'read_b'
        elif self._phase == 'read_b':
            if sSCL == 1:
                self._phase = 'read_c'
        elif self._phase == 'read_c':
            self._phase = 'read_d'
        elif self._phase == 'read_d':
            self._phase = 'idle'
            self._command = 0
            self._cmd_ack = 1
        elif self._phase == 'write_a':
            self._phase = 'write_b'
        elif self._phase == 'write_b':
            if sSCL == 1:
                self._phase = 'write_c'
        elif self._phase == 'write_c':
            self._phase = 'write_d'
        elif self._phase == 'write_d':
            self._phase = 'idle'
            self._command = 0
            self._cmd_ack = 1


    def _outputs(self, i):
        din = self.mask(i['din'], 1)
        scl_oen, sda_oen, unused_sda_chk = self._phase_outputs(din)
        o = {p: None for p in self.OUTPUT_PORTS}
        o['cmd_ack'] = self.mask(self._cmd_ack, 1)
        o['busy'] = self.mask(self._busy, 1)
        o['al'] = self.mask(self._al, 1)
        o['dout'] = self.mask(self._dout, 1)
        o['scl_o'] = 0
        o['scl_oen'] = self.mask(scl_oen, 1)
        o['sda_o'] = 0
        o['sda_oen'] = self.mask(sda_oen, 1)
        return o


    def step(self, i):
        self._ensure_state()

        if self.mask(i['nReset'], 1) == 0:
            self._reset_state()
            return self._outputs(i)

        if self.mask(i['rst'], 1) == 1:
            self._reset_state()
            return self._outputs(i)

        ena = self.mask(i['ena'], 1)
        cmd = self.mask(i['cmd'], 4)
        din = self.mask(i['din'], 1)
        clk_cnt = self.mask(i['clk_cnt'], 16)

        # First advance the synchronizers/filter.  Event generation then
        # compares the newly filtered bus value with the delayed value from
        # the preceding sample, so a filtered edge is visible on the same
        # model clock on which it is produced.
        self._update_inputs(i['scl_i'], i['sda_i'], ena, clk_cnt)
        events = self._bus_events(din)
        self._cmd_ack = 0

        if events['scl_rise']:
            self._dout = events['sSDA']

        if events['start']:
            self._busy = 1
        elif events['stop']:
            self._busy = 0

        arbitration = events['sda_check'] == 1 and events['sSDA'] == 0
        stop_conflict = (events['stop'] == 1 and
                         self._phase != 'idle' and self._command != 2)
        abort = arbitration or stop_conflict
        if arbitration or stop_conflict:
            self._al = 1
            self._phase = 'idle'
            self._command = 0

        clk_en = self._timing_tick(ena, clk_cnt,
                                   events['scl_sync'], events['slave_wait'])

        if not abort and ena and clk_en:
            self._advance_fsm(cmd, events['sSCL'])

        return self._outputs(i)
