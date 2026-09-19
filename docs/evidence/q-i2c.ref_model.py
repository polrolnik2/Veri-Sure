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
        self._cmd_latched = 0
        self._din_latched = 0
        self._cmd_ack = 0
        self._busy = 0
        self._al = 0
        self._dout = 0
        self._cnt = self.mask(clk_cnt, 16)
        self._clk_en = 0
        self._filter_cnt = 0
        self._sync_scl1 = 1
        self._sync_scl2 = 1
        self._sync_sda1 = 1
        self._sync_sda2 = 1
        self._f_scl = [1, 1, 1]
        self._f_sda = [1, 1, 1]
        self._scl_filtered = 1
        self._sda_filtered = 1
        self._d_scl = 1
        self._d_sda = 1


    def _majority(self, values):
        return 1 if (values[0] + values[1] + values[2]) >= 2 else 0


    def _filter_inputs(self, scl_i, sda_i, ena, clk_cnt):
        previous_scl = self._d_scl
        previous_sda = self._d_sda

        old_sync_scl1 = self._sync_scl1
        old_sync_sda1 = self._sync_sda1
        self._sync_scl1 = self.mask(scl_i, 1)
        self._sync_sda1 = self.mask(sda_i, 1)
        self._sync_scl2 = old_sync_scl1
        self._sync_sda2 = old_sync_sda1

        if ena:
            if self._filter_cnt == 0:
                self._f_scl = [self._f_scl[1], self._f_scl[2], self._sync_scl2]
                self._f_sda = [self._f_sda[1], self._f_sda[2], self._sync_sda2]
                self._scl_filtered = self._majority(self._f_scl)
                self._sda_filtered = self._majority(self._f_sda)
                self._filter_cnt = self.mask(clk_cnt >> 2, 14)
            else:
                self._filter_cnt = self.mask(self._filter_cnt - 1, 14)
        else:
            self._filter_cnt = 0

        self._d_scl = self._scl_filtered
        self._d_sda = self._sda_filtered

        start_event = previous_sda == 1 and self._sda_filtered == 0 and self._scl_filtered == 1
        stop_event = previous_sda == 0 and self._sda_filtered == 1 and self._scl_filtered == 1
        scl_rise = previous_scl == 0 and self._scl_filtered == 1
        scl_fall = previous_scl == 1 and self._scl_filtered == 0
        return start_event, stop_event, scl_rise, scl_fall


    def _state_lines(self):
        if self._state in ('idle', 'start_a'):
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
        if self._state in ('write_a', 'write_b', 'write_c'):
            return (1 if self._state == 'write_b' else 0), self._din_latched
        return 1, 1


    def _timing_tick(self, ena, clk_cnt, slave_wait, scl_sync):
        clk_cnt = self.mask(clk_cnt, 16)
        if not ena:
            self._cnt = clk_cnt
            self._clk_en = 0
            return False

        if scl_sync:
            self._cnt = clk_cnt

        if slave_wait:
            self._clk_en = 0
            return False

        if scl_sync:
            self._clk_en = 1
            return True

        if self._cnt == 0:
            self._cnt = clk_cnt
            self._clk_en = 1
            return True

        self._cnt = self.mask(self._cnt - 1, 16)
        self._clk_en = 0
        return False


    def _advance_fsm(self, tick, filtered_scl, cmd, din, abort):
        self._cmd_ack = 0

        if abort:
            self._state = 'idle'
            self._cmd_latched = 0
            return

        if not tick:
            return

        command = self.mask(cmd, 4)
        data = self.mask(din, 1)

        if self._state == 'idle':
            if command == 1:
                self._cmd_latched = command
                self._din_latched = data
                self._state = 'start_a'
            elif command == 2:
                self._cmd_latched = command
                self._din_latched = data
                self._state = 'stop_a'
            elif command == 4:
                self._cmd_latched = command
                self._din_latched = data
                self._state = 'write_a'
            elif command == 8:
                self._cmd_latched = command
                self._din_latched = data
                self._state = 'read_a'
            return

        if self._state == 'start_a':
            if filtered_scl:
                self._state = 'start_b'
        elif self._state == 'start_b':
            self._state = 'start_c'
        elif self._state == 'start_c':
            # Keep the completed START phase visible for the acknowledge
            # cycle.  The following tick returns to the released idle state.
            if self._cmd_latched == 1:
                self._cmd_latched = 0
                self._cmd_ack = 1
            else:
                self._state = 'idle'
        elif self._state == 'stop_a':
            self._state = 'stop_b'
        elif self._state == 'stop_b':
            if filtered_scl:
                self._state = 'stop_c'
        elif self._state == 'stop_c':
            self._state = 'idle'
            self._cmd_latched = 0
            self._cmd_ack = 1
        elif self._state == 'read_a':
            self._state = 'read_b'
        elif self._state == 'read_b':
            if filtered_scl:
                self._state = 'read_c'
        elif self._state == 'read_c':
            self._state = 'idle'
            self._cmd_latched = 0
            self._cmd_ack = 1
        elif self._state == 'write_a':
            self._state = 'write_b'
        elif self._state == 'write_b':
            if filtered_scl:
                self._state = 'write_c'
        elif self._state == 'write_c':
            self._state = 'idle'
            self._cmd_latched = 0
            self._cmd_ack = 1


    def step(self, i):
        o = {p: None for p in self.OUTPUT_PORTS}

        clk_cnt = self.mask(i['clk_cnt'], 16)
        ena = self.mask(i['ena'], 1)
        scl_i = self.mask(i['scl_i'], 1)
        sda_i = self.mask(i['sda_i'], 1)
        cmd = self.mask(i['cmd'], 4)
        din = self.mask(i['din'], 1)

        if self.mask(i['nReset'], 1) == 0 or self.mask(i['rst'], 1) != 0:
            self._reset_state(clk_cnt)
        else:
            start_event, stop_event, scl_rise, scl_fall = self._filter_inputs(
                scl_i, sda_i, ena, clk_cnt
            )

            if scl_rise:
                self._dout = self._sda_filtered

            if start_event:
                self._busy = 1
            if stop_event:
                self._busy = 0

            current_scl_oen, current_sda_oen = self._state_lines()
            slave_wait = current_scl_oen == 1 and self._scl_filtered == 0
            scl_sync = current_scl_oen == 1 and scl_fall

            arbitration_loss = (
                self._state == 'write_b'
                and current_sda_oen == 1
                and self._scl_filtered == 1
                and self._sda_filtered == 0
            )
            unexpected_stop = (
                stop_event
                and self._state != 'idle'
                and self._cmd_latched != 2
            )
            abort = arbitration_loss or unexpected_stop
            if abort:
                self._al = 1

            tick = self._timing_tick(ena, clk_cnt, slave_wait, scl_sync)
            self._advance_fsm(tick, self._scl_filtered, cmd, din, abort)

        scl_oen, sda_oen = self._state_lines()
        o['cmd_ack'] = self.mask(self._cmd_ack, 1)
        o['busy'] = self.mask(self._busy, 1)
        o['al'] = self.mask(self._al, 1)
        o['dout'] = self.mask(self._dout, 1)
        o['scl_o'] = 0
        o['scl_oen'] = self.mask(scl_oen, 1)
        o['sda_o'] = 0
        o['sda_oen'] = self.mask(sda_oen, 1)
        return o
