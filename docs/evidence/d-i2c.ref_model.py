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

    def __init__(self):
        self._reset_state()


    def reset(self):
        self._reset_state()


    def _bit(self, value):
        return self.mask(value, 1)


    def _decode_command(self, value):
        command = self.mask(value, 4)
        if command == 1:
            return 'start'
        if command == 2:
            return 'stop'
        if command == 4:
            return 'write'
        if command == 8:
            return 'read'
        return None


    def _majority(self, history):
        return 1 if (history[0] + history[1] + history[2]) >= 2 else 0


    def _reset_state(self):
        self._state = 'idle'
        self._active_cmd = None
        self._din_latched = 0
        self._ack = 0
        self._busy = 0
        self._al = 0
        self._dout = 0

        self._div_cnt = 0
        self._clk_en = 1
        self._filter_cnt = 0

        self._c_scl_1 = 1
        self._c_scl_2 = 1
        self._c_sda_1 = 1
        self._c_sda_2 = 1
        self._f_scl = [1, 1, 1]
        self._f_sda = [1, 1, 1]
        self._scl_f = 1
        self._sda_f = 1
        self._d_scl = 1
        self._d_sda = 1


    def _update_filter(self, scl_i, sda_i, ena, clk_cnt):
        raw_scl = self._bit(scl_i)
        raw_sda = self._bit(sda_i)

        old_c_scl_1 = self._c_scl_1
        old_c_sda_1 = self._c_sda_1
        old_c_scl_2 = self._c_scl_2
        old_c_sda_2 = self._c_sda_2

        self._c_scl_1 = raw_scl
        self._c_scl_2 = old_c_scl_1
        self._c_sda_1 = raw_sda
        self._c_sda_2 = old_c_sda_1

        if ena:
            if self._filter_cnt == 0:
                self._f_scl = [self._f_scl[1], self._f_scl[2], old_c_scl_2]
                self._f_sda = [self._f_sda[1], self._f_sda[2], old_c_sda_2]
                self._scl_f = self._majority(self._f_scl)
                self._sda_f = self._majority(self._f_sda)
                interval = self.mask(clk_cnt, 16) >> 2
                self._filter_cnt = self.mask(interval, 16)
            else:
                self._filter_cnt = self.mask(self._filter_cnt - 1, 16)
        else:
            self._filter_cnt = 0

        return self._scl_f, self._sda_f


    def _bus_events(self, scl_now, sda_now):
        start_event = (
            scl_now == 1 and
            self._d_scl == 1 and
            sda_now == 0 and
            self._d_sda == 1
        )
        stop_event = (
            scl_now == 1 and
            self._d_scl == 1 and
            sda_now == 1 and
            self._d_sda == 0
        )
        scl_rise = scl_now == 1 and self._d_scl == 0
        scl_fall = scl_now == 0 and self._d_scl == 1
        return start_event, stop_event, scl_rise, scl_fall


    def _process_bus_events(self, events, scl_now, sda_now):
        start_event, stop_event, scl_rise, _ = events

        if start_event:
            self._busy = 1
        if stop_event:
            self._busy = 0
        if scl_rise:
            self._dout = self._bit(sda_now)

        aborted = False
        if (
            self._state != 'idle' and
            stop_event and
            self._active_cmd != 'stop'
        ):
            self._al = 1
            aborted = True

        if (
            self._state == 'write_b' and
            self._din_latched == 1 and
            scl_now == 1 and
            sda_now == 0
        ):
            self._al = 1
            aborted = True

        if aborted:
            self._state = 'idle'
            self._active_cmd = None
            self._din_latched = 0

        return aborted


    def _state_outputs(self):
        if self._state == 'idle':
            return 1, 1
        if self._state == 'start_a':
            return 1, 1
        if self._state == 'start_b':
            return 1, 0
        if self._state == 'start_c':
            return 0, 0
        if self._state == 'stop_a':
            return 0, 0
        if self._state == 'stop_b':
            return 1, 0
        if self._state == 'stop_c':
            return 1, 1
        if self._state == 'read_a':
            return 0, 1
        if self._state == 'read_b':
            return 1, 1
        if self._state == 'read_c':
            return 0, 1
        if self._state == 'write_a':
            return 0, self._din_latched
        if self._state == 'write_b':
            return 1, self._din_latched
        if self._state == 'write_c':
            return 0, self._din_latched
        return 1, 1


    def _timing_conditions(self, scl_now, scl_fall):
        scl_oen, _ = self._state_outputs()
        slave_wait = 1 if scl_oen == 1 and scl_now == 0 else 0
        scl_sync = 1 if scl_oen == 1 and scl_fall else 0
        return slave_wait, scl_sync


    def _update_divider(self, clk_cnt, ena, slave_wait, scl_sync):
        reload_value = self.mask(clk_cnt, 16)

        if not ena:
            self._div_cnt = reload_value
            self._clk_en = 1
            return 0

        if scl_sync:
            self._div_cnt = reload_value
            self._clk_en = 1
        elif slave_wait:
            self._div_cnt = self._div_cnt
            self._clk_en = 0
        elif self._div_cnt == 0:
            self._div_cnt = reload_value
            self._clk_en = 1
        else:
            self._div_cnt = self.mask(self._div_cnt - 1, 16)
            self._clk_en = 0

        return 1 if ena and self._clk_en else 0


    def _advance_fsm(self, tick, scl_high, cmd, din):
        if not tick:
            return

        if self._state == 'idle':
            operation = self._decode_command(cmd)
            if operation is None:
                return

            self._active_cmd = operation
            if operation == 'start':
                self._al = 0
                self._state = 'start_a'
            elif operation == 'stop':
                self._state = 'stop_a'
            elif operation == 'read':
                self._state = 'read_a'
            elif operation == 'write':
                self._din_latched = self._bit(din)
                if self._div_cnt != 0:
                    self._dout = self._bit(self._sda_f)
                self._state = 'write_a'
            return

        if self._state == 'start_a':
            self._state = 'start_b'
        elif self._state == 'start_b':
            if scl_high:
                self._state = 'start_c'
        elif self._state == 'start_c':
            self._state = 'idle'
            self._active_cmd = None
            self._ack = 1
        elif self._state == 'stop_a':
            self._state = 'stop_b'
        elif self._state == 'stop_b':
            if scl_high:
                self._state = 'stop_c'
        elif self._state == 'stop_c':
            self._state = 'idle'
            self._active_cmd = None
            self._ack = 1
        elif self._state == 'read_a':
            self._state = 'read_b'
        elif self._state == 'read_b':
            if scl_high:
                self._state = 'read_c'
        elif self._state == 'read_c':
            self._state = 'idle'
            self._active_cmd = None
            self._ack = 1
        elif self._state == 'write_a':
            self._dout = self._bit(self._sda_f)
            self._state = 'write_b'
        elif self._state == 'write_b':
            if scl_high:
                self._state = 'write_c'
        elif self._state == 'write_c':
            self._state = 'idle'
            self._active_cmd = None
            self._ack = 1


    def _write_outputs(self, o):
        scl_oen, sda_oen = self._state_outputs()
        o['cmd_ack'] = self._bit(self._ack)
        o['busy'] = self._bit(self._busy)
        o['al'] = self._bit(self._al)
        o['dout'] = self._bit(self._dout)
        o['scl_o'] = 0
        o['scl_oen'] = self._bit(scl_oen)
        o['sda_o'] = 0
        o['sda_oen'] = self._bit(sda_oen)


    def step(self, i):
        o = {p: None for p in self.OUTPUT_PORTS}

        if self._bit(i['nReset']) == 0 or self._bit(i['rst']) == 1:
            self._reset_state()
            self._write_outputs(o)
            return o

        self._ack = 0
        ena = self._bit(i['ena'])
        clk_cnt = self.mask(i['clk_cnt'], 16)
        cmd = self.mask(i['cmd'], 4)
        din = self._bit(i['din'])

        scl_now, sda_now = self._update_filter(
            i['scl_i'], i['sda_i'], ena, clk_cnt
        )
        events = self._bus_events(scl_now, sda_now)
        aborted = self._process_bus_events(events, scl_now, sda_now)

        self._d_scl = scl_now
        self._d_sda = sda_now

        slave_wait, scl_sync = self._timing_conditions(
            scl_now, events[3]
        )
        tick = self._update_divider(
            clk_cnt, ena, slave_wait, scl_sync
        )

        if not aborted:
            self._advance_fsm(tick, scl_now, cmd, din)

        self._write_outputs(o)
        return o
