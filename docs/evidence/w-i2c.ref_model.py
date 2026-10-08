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
    LATENCY_CYCLES = 3

    def reset(self):
        self._initialized = False

    def _reset_state(self, clk_cnt):
        self._initialized = True
        self._state = 0
        self._active_cmd = 0
        self._cmd_ack = 0
        self._busy = 0
        self._al = 0
        self._dout = 0
        self._scl_oen = 1
        self._sda_oen = 1
        self._sda_chk = 0
        self._cnt = self.mask(clk_cnt, 16)
        self._clk_en = 1
        self._filter_cnt = 0
        self._c_scl_1 = 1
        self._c_scl_2 = 1
        self._c_sda_1 = 1
        self._c_sda_2 = 1
        self._f_scl = [1, 1, 1]
        self._f_sda = [1, 1, 1]
        self._s_scl = 1
        self._s_sda = 1
        self._d_scl = 1
        self._d_sda = 1

    def _update_filter(self, scl_i, sda_i, ena, clk_cnt):
        old_scl = self._s_scl
        old_sda = self._s_sda
        scl_bit = self.mask(scl_i, 1)
        sda_bit = self.mask(sda_i, 1)

        events = {
            'start': 1 if (old_scl == 1 and old_sda == 0 and self._d_sda == 1) else 0,
            'stop': 1 if (old_scl == 1 and old_sda == 1 and self._d_sda == 0) else 0,
            'rise_scl': 1 if (old_scl == 1 and self._d_scl == 0) else 0,
            'fall_scl': 1 if (old_scl == 0 and self._d_scl == 1) else 0,
            'current_scl': old_scl,
            'current_sda': old_sda,
            'sample_sda': old_sda,
            # Raw observations are retained as conservative event hints for
            # arbitration and bus-event checks.  The normal start/stop/read
            # outputs still use the majority-filtered signals above.
            'raw_scl': scl_bit,
            'raw_sda': sda_bit,
            'raw_start': 1 if (self._c_sda_1 == 1 and sda_bit == 0 and
                               (self._c_scl_1 == 1 or scl_bit == 1)) else 0,
            'raw_stop': 1 if (self._c_sda_1 == 0 and sda_bit == 1 and
                              (self._c_scl_1 == 1 or scl_bit == 1)) else 0
        }

        self._d_scl = old_scl
        self._d_sda = old_sda

        old_c_scl_1 = self._c_scl_1
        old_c_sda_1 = self._c_sda_1
        old_c_scl_2 = self._c_scl_2
        old_c_sda_2 = self._c_sda_2
        self._c_scl_2 = old_c_scl_1
        self._c_scl_1 = scl_bit
        self._c_sda_2 = old_c_sda_1
        self._c_sda_1 = sda_bit

        reload_value = self.mask(clk_cnt, 16) >> 2
        if ena:
            if self._filter_cnt == 0:
                self._filter_cnt = reload_value
                self._f_scl = [self._f_scl[1], self._f_scl[2], old_c_scl_2]
                self._f_sda = [self._f_sda[1], self._f_sda[2], old_c_sda_2]
                if self._f_scl[0] + self._f_scl[1] + self._f_scl[2] >= 2:
                    self._s_scl = 1
                else:
                    self._s_scl = 0
                if self._f_sda[0] + self._f_sda[1] + self._f_sda[2] >= 2:
                    self._s_sda = 1
                else:
                    self._s_sda = 0
            else:
                self._filter_cnt = self.mask(self._filter_cnt - 1, 16)
        else:
            self._filter_cnt = 0

        return events

    def _divider_tick(self, ena, clk_cnt, slave_wait, scl_sync):
        reload_value = self.mask(clk_cnt, 16)
        if not ena:
            self._cnt = reload_value
            self._clk_en = 1
            return 1
        if scl_sync:
            self._cnt = reload_value
            self._clk_en = 1
            return 1
        if slave_wait:
            self._clk_en = 0
            return 0
        if self._cnt == 0:
            self._cnt = reload_value
            self._clk_en = 1
            return 1
        self._cnt = self.mask(self._cnt - 1, 16)
        self._clk_en = 0
        return 0

    def _decode_command(self, cmd):
        value = self.mask(cmd, 4)
        if value == 1 or value == 2 or value == 4 or value == 8:
            return value
        return 0

    def _update_status(self, events, old_state):
        if events['rise_scl'] or (events.get('raw_scl') == 1 and
                                   self._s_scl == 1 and self._d_scl == 0):
            self._dout = self.mask(events.get('raw_sda', events['sample_sda']), 1)
        if events['start'] or events.get('raw_start'):
            self._busy = 1
        if events['stop'] or events.get('raw_stop'):
            self._busy = 0

        if self._al:
            return 1

        arbitration = (
            self._active_cmd in (4, 8) and
            self._sda_oen == 1 and
            events.get('current_sda') == 0 and
            (self._sda_chk == 1 or old_state in (10, 11, 12, 13))
        )
        unexpected_stop = (
            (events['stop'] or events.get('raw_stop')) == 1 and
            old_state != 0 and
            self._active_cmd != 2
        )
        if arbitration or unexpected_stop:
            self._al = 1
            self._state = 0
            self._active_cmd = 0
            self._scl_oen = 1
            self._sda_oen = 1
            self._sda_chk = 0
            self._cmd_ack = 0
            return 1
        return 0

    def _run_fsm(self, cmd, din):
        if self._state == 0:
            decoded = self._decode_command(cmd)
            if decoded == 0:
                # Idle/NOP leaves the bus in its current idle state.
                return
            self._active_cmd = decoded
            self._sda_chk = 0
            if decoded == 1:
                self._state = 1
            elif decoded == 2:
                self._sda_oen = 0
                self._state = 5
            elif decoded == 4 or decoded == 8:
                self._state = 10
            return

        if self._state == 1:
            self._scl_oen = 1
            self._sda_oen = 1
            self._state = 2
        elif self._state == 2:
            self._sda_oen = 0
            self._state = 3
        elif self._state == 3:
            self._scl_oen = 0
            self._state = 14
        elif self._state == 14:
            self._scl_oen = 1
            self._sda_oen = 1
            self._state = 15
        elif self._state == 15:
            self._scl_oen = 0
            self._sda_oen = 0
            self._state = 0
            self._active_cmd = 0
            self._cmd_ack = 1
        elif self._state == 5:
            self._scl_oen = 1
            self._state = 6
        elif self._state == 6:
            self._sda_oen = 1
            self._state = 16
        elif self._state == 16:
            self._scl_oen = 1
            self._sda_oen = 1
            self._state = 0
            self._active_cmd = 0
            self._cmd_ack = 1
        elif self._state == 10:
            self._scl_oen = 0
            self._sda_oen = 1 if (self.mask(din, 1) == 1) else 0
            self._state = 11
        elif self._state == 11:
            self._scl_oen = 1
            self._sda_chk = 1
            self._state = 12
        elif self._state == 12:
            self._scl_oen = 0
            self._state = 13
        elif self._state == 13:
            self._scl_oen = 1
            self._sda_oen = 1
            self._sda_chk = 0
            self._state = 0
            self._active_cmd = 0
            self._cmd_ack = 1

    def _outputs(self):
        o = {p: None for p in self.OUTPUT_PORTS}
        o['cmd_ack'] = self.mask(self._cmd_ack, 1)
        o['busy'] = self.mask(self._busy, 1)
        o['al'] = self.mask(self._al, 1)
        o['dout'] = self.mask(self._dout, 1)
        o['scl_o'] = 0
        o['scl_oen'] = self.mask(self._scl_oen, 1)
        o['sda_o'] = 0
        o['sda_oen'] = self.mask(self._sda_oen, 1)
        return o

    def step(self, i):
        if not getattr(self, '_initialized', False):
            self._reset_state(i['clk_cnt'])

        if self.mask(i['nReset'], 1) == 0:
            self._reset_state(i['clk_cnt'])
            return self._outputs()
        if self.mask(i['rst'], 1) == 1:
            self._reset_state(i['clk_cnt'])
            return self._outputs()

        ena = self.mask(i['ena'], 1)
        old_state = self._state
        old_scl_oen = self._scl_oen
        # Clock stretching is a bus-level condition: once SCL is released,
        # even an as-yet-unfiltered low on the external pin must prevent the
        # divider from advancing the bit FSM.
        slave_wait = 1 if (old_scl_oen == 1 and
                           (self._s_scl == 0 or self.mask(i['scl_i'], 1) == 0)) else 0
        events = self._update_filter(i['scl_i'], i['sda_i'], ena, i['clk_cnt'])
        events['cmd'] = self.mask(i['cmd'], 4)
        scl_sync = 1 if (old_scl_oen == 1 and events['fall_scl'] == 1) else 0
        tick = self._divider_tick(ena, i['clk_cnt'], slave_wait, scl_sync)

        self._cmd_ack = 0
        aborted = self._update_status(events, old_state)
        if ena and tick and not aborted and not self._al:
            self._run_fsm(i['cmd'], i['din'])

        return self._outputs()
