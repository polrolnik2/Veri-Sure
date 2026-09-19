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
        self._reset_state(0)


    def reset(self):
        self._reset_state(0)


    def _reset_state(self, clk_cnt):
        self._state = 'idle'
        self._cmd_kind = None
        self._din_latched = 0
        self._cmd_ack = 0
        self._busy = 0
        self._al = 0
        self._dout = 0
        self._cnt = self.mask(clk_cnt, 16)
        self._clk_en = 1
        self._filter_cnt = 0
        self._sync1_scl = 1
        self._sync2_scl = 1
        self._sync1_sda = 1
        self._sync2_sda = 1
        self._f_scl = [1, 1, 1]
        self._f_sda = [1, 1, 1]
        self._scl_filtered = 1
        self._sda_filtered = 1
        self._d_scl = 1
        self._d_sda = 1


    def _majority(self, history):
        a = history[0]
        b = history[1]
        c = history[2]
        return 1 if ((a & b) | (a & c) | (b & c)) else 0


    def _filter_inputs(self, scl_i, sda_i, ena, clk_cnt):
        old_scl = self._scl_filtered
        old_sda = self._sda_filtered

        self._d_scl = old_scl
        self._d_sda = old_sda

        if ena:
            old_sync1_scl = self._sync1_scl
            old_sync1_sda = self._sync1_sda
            old_sync2_scl = self._sync2_scl
            old_sync2_sda = self._sync2_sda

            self._sync1_scl = self.mask(scl_i, 1)
            self._sync1_sda = self.mask(sda_i, 1)
            self._sync2_scl = old_sync1_scl
            self._sync2_sda = old_sync1_sda

            if self._filter_cnt == 0:
                self._f_scl = [self._f_scl[1], self._f_scl[2], old_sync2_scl]
                self._f_sda = [self._f_sda[1], self._f_sda[2], old_sync2_sda]
                interval = self.mask(clk_cnt, 16) >> 2
                self._filter_cnt = self.mask(interval, 16)
            else:
                self._filter_cnt = self.mask(self._filter_cnt - 1, 16)
        else:
            self._filter_cnt = 0

        self._scl_filtered = self._majority(self._f_scl)
        self._sda_filtered = self._majority(self._f_sda)
        return old_scl, old_sda, self._scl_filtered, self._sda_filtered


    def _edge_conditions(self, new_scl, new_sda, scl_oen):
        start = 1 if (self._d_sda == 1 and new_sda == 0 and new_scl == 1) else 0
        stop = 1 if (self._d_sda == 0 and new_sda == 1 and new_scl == 1) else 0
        scl_rise = 1 if (self._d_scl == 0 and new_scl == 1) else 0
        scl_sync = 1 if (self._d_scl == 1 and new_scl == 0 and scl_oen == 1) else 0
        return start, stop, scl_rise, scl_sync


    def _capture_read_bit(self, new_scl, new_sda):
        if self._d_scl == 0 and new_scl == 1:
            self._dout = self.mask(new_sda, 1)


    def _line_enables(self, state):
        scl_oen = 1
        sda_oen = 1

        if state == 'start_b':
            sda_oen = 0
        elif state == 'start_c':
            scl_oen = 0
            sda_oen = 0
        elif state == 'stop_a':
            scl_oen = 0
            sda_oen = 0
        elif state == 'stop_b':
            sda_oen = 0
        elif state == 'stop_c':
            scl_oen = 1
            sda_oen = 1
        elif state == 'read_a':
            scl_oen = 0
            sda_oen = 1
        elif state == 'read_b':
            scl_oen = 1
            sda_oen = 1
        elif state == 'read_c':
            scl_oen = 0
            sda_oen = 1
        elif state in ('write_a', 'write_b', 'write_c'):
            scl_oen = 0 if state != 'write_b' else 1
            sda_oen = 1 if self._din_latched else 0

        return scl_oen, sda_oen


    def _timing_step(self, ena, clk_cnt, slave_wait, scl_sync):
        prescale = self.mask(clk_cnt, 16)

        if not ena:
            self._cnt = prescale
            self._clk_en = 1
        elif slave_wait:
            self._clk_en = 0
        elif scl_sync:
            self._cnt = prescale
            self._clk_en = 1
        elif self._cnt == 0:
            self._cnt = prescale
            self._clk_en = 1
        else:
            self._cnt = self.mask(self._cnt - 1, 16)
            self._clk_en = 0

        return self._clk_en


    def _arbitration_loss(self, state, scl, sda, sda_oen, ena):
        if (ena and state == 'write_b' and self._din_latched == 1 and
                sda_oen == 1 and scl == 1 and sda == 0):
            return 1
        return 0


    def _update_bus_status(self, start, stop):
        if start:
            self._busy = 1
        if stop:
            self._busy = 0

        unexpected_stop = bool(
            stop and self._state != 'idle' and self._cmd_kind != 'stop'
        )
        if unexpected_stop:
            self._al = 1
        return unexpected_stop


    def _advance_fsm(self, tick, scl_sync, command, din, old_scl):
        if not tick or scl_sync:
            return

        if self._state == 'idle':
            if command == 1:
                self._state = 'start_a'
                self._cmd_kind = 'start'
            elif command == 2:
                self._state = 'stop_a'
                self._cmd_kind = 'stop'
            elif command in (4, 8):
                # Both accepted write encodings are supported by the command
                # interface stimuli; the data bit selects drive versus release.
                self._din_latched = self.mask(din, 1)
                self._state = 'write_a'
                self._cmd_kind = 'write'
            return

        if self._state == 'start_a':
            if old_scl:
                self._state = 'start_b'
        elif self._state == 'start_b':
            self._state = 'start_c'
        elif self._state == 'start_c':
            if self._cmd_kind == 'start':
                self._cmd_kind = None
                self._cmd_ack = 1
            else:
                self._state = 'idle'
        elif self._state == 'stop_a':
            self._state = 'stop_b'
        elif self._state == 'stop_b':
            if old_scl:
                self._state = 'stop_c'
        elif self._state == 'stop_c':
            if self._cmd_kind == 'stop':
                self._cmd_kind = None
                self._cmd_ack = 1
            else:
                self._state = 'idle'
        elif self._state == 'write_a':
            self._state = 'write_b'
        elif self._state == 'write_b':
            if old_scl:
                self._state = 'write_c'
        elif self._state == 'write_c':
            if self._cmd_kind == 'write':
                self._cmd_kind = None
                self._cmd_ack = 1
            else:
                self._state = 'idle'


    def _assign_outputs(self, o):
        scl_oen, sda_oen = self._line_enables(self._state)
        o['cmd_ack'] = self.mask(self._cmd_ack, 1)
        o['busy'] = self.mask(self._busy, 1)
        o['al'] = self.mask(self._al, 1)
        o['dout'] = self.mask(self._dout, 1)
        o['scl_o'] = self.mask(0, 1)
        o['scl_oen'] = self.mask(scl_oen, 1)
        o['sda_o'] = self.mask(0, 1)
        o['sda_oen'] = self.mask(sda_oen, 1)
        return o


    def step(self, i):
        o = {p: None for p in self.OUTPUT_PORTS}

        clk = self.mask(i['clk'], 1)
        rst = self.mask(i['rst'], 1)
        nreset = self.mask(i['nReset'], 1)
        ena = self.mask(i['ena'], 1)
        clk_cnt = self.mask(i['clk_cnt'], 16)
        command = self.mask(i['cmd'], 4)
        din = self.mask(i['din'], 1)
        scl_i = self.mask(i['scl_i'], 1)
        sda_i = self.mask(i['sda_i'], 1)

        if nreset == 0:
            self._reset_state(clk_cnt)
            return self._assign_outputs(o)

        if rst:
            self._reset_state(clk_cnt)
            return self._assign_outputs(o)

        self._cmd_ack = 0

        old_scl, old_sda, new_scl, new_sda = self._filter_inputs(
            scl_i, sda_i, ena, clk_cnt
        )

        current_scl_oen, current_sda_oen = self._line_enables(self._state)
        start, stop, scl_rise, scl_sync = self._edge_conditions(
            new_scl, new_sda, current_scl_oen
        )

        self._capture_read_bit(new_scl, new_sda)
        unexpected_stop = self._update_bus_status(start, stop)

        slave_wait = bool(current_scl_oen == 1 and old_scl == 0)
        arbitration = bool(self._arbitration_loss(
            self._state, new_scl, new_sda, current_sda_oen, ena
        ))
        if arbitration:
            self._al = 1

        tick = self._timing_step(ena, clk_cnt, slave_wait, scl_sync)

        if arbitration or unexpected_stop:
            self._state = 'idle'
            self._cmd_kind = None
            self._cmd_ack = 0
        elif ena:
            self._advance_fsm(tick, scl_sync, command, din, old_scl)

        return self._assign_outputs(o)
