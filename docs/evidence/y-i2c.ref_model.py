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
        self.reset()


    def reset(self):
        self._state = 'IDLE'
        self._active_cmd = None
        self._active_din = 0
        self._cmd_ack = 0
        self._busy = 0
        self._al = 0
        self._dout = 0
        self._scl_oen = 1
        self._sda_oen = 1
        self._cnt = 0
        self._clk_en = 1
        self._filter_cnt = 0
        self._cSCL1 = 1
        self._cSCL2 = 1
        self._cSDA1 = 1
        self._cSDA2 = 1
        self._fSCL = [1, 1, 1]
        self._fSDA = [1, 1, 1]
        self._sSCL = 1
        self._sSDA = 1
        self._dSCL = 1
        self._dSDA = 1
        self._slave_wait = 0
        self._scl_sync = 0
        self._sda_chk = 0


    def _majority(self, history):
        return 1 if (history[0] + history[1] + history[2]) >= 2 else 0


    def _set_lines(self, scl_oen, sda_oen):
        self._scl_oen = 1 if scl_oen else 0
        self._sda_oen = 1 if sda_oen else 0


    def _filter_step(self, i, enabled):
        old_scl = self._sSCL
        old_sda = self._sSDA
        old_cSCL1 = self._cSCL1
        old_cSCL2 = self._cSCL2
        old_cSDA1 = self._cSDA1
        old_cSDA2 = self._cSDA2

        self._dSCL = old_scl
        self._dSDA = old_sda

        if enabled:
            self._cSCL1 = i['scl_i'] & 1
            self._cSCL2 = old_cSCL1
            self._cSDA1 = i['sda_i'] & 1
            self._cSDA2 = old_cSDA1

            if self._filter_cnt == 0:
                self._fSCL = [self._fSCL[1], self._fSCL[2], old_cSCL2]
                self._fSDA = [self._fSDA[1], self._fSDA[2], old_cSDA2]
                self._sSCL = self._majority(self._fSCL)
                self._sSDA = self._majority(self._fSDA)
                self._filter_cnt = ((i['clk_cnt'] & 0xffff) >> 2) & 0xffff
            else:
                self._filter_cnt = (self._filter_cnt - 1) & 0xffff
        else:
            self._filter_cnt = 0

        events = {
            'scl_level': self._sSCL & 1,
            'sda_level': self._sSDA & 1,
            'rise_scl': int(self._sSCL == 1 and self._dSCL == 0),
            'fall_scl': int(self._sSCL == 0 and self._dSCL == 1),
            'start': int(self._sSDA == 0 and self._dSDA == 1 and self._sSCL == 1),
            'stop': int(self._sSDA == 1 and self._dSDA == 0 and self._sSCL == 1),
        }
        return events


    def _bus_event_step(self, events):
        if events['start']:
            self._busy = 1
            self._al = 0
        if events['stop']:
            self._busy = 0
        if events['rise_scl']:
            self._dout = events['sda_level'] & 1


    def _timing_step(self, clk_cnt, enabled, falling_scl):
        prescale = clk_cnt & 0xffff
        self._slave_wait = int(self._scl_oen == 1 and self._sSCL == 0)
        self._scl_sync = int(falling_scl and self._scl_oen == 1)

        if not enabled:
            self._cnt = prescale
            self._clk_en = 1
        elif self._scl_sync:
            self._cnt = prescale
            self._clk_en = 1
        elif self._slave_wait:
            self._clk_en = 0
        elif self._cnt == 0:
            self._cnt = prescale
            self._clk_en = 1
        else:
            self._cnt = (self._cnt - 1) & 0xffff
            self._clk_en = 0

        return int(bool(enabled) and bool(self._clk_en) and not bool(self._slave_wait))


    def _arbitration_step(self, events):
        self._sda_chk = int(
            self._state == 'WRITE_B'
            and self._active_cmd == 'WRITE'
            and self._sda_oen == 1
        )
        released_sda_lost = bool(self._sda_chk and events['sda_level'] == 0)
        unexpected_stop = bool(
            events['stop']
            and self._state != 'IDLE'
            and self._active_cmd != 'STOP'
        )
        lost = released_sda_lost or unexpected_stop

        if lost:
            self._al = 1
            self._state = 'IDLE'
            self._active_cmd = None
            self._active_din = 0
            self._sda_chk = 0
            self._set_lines(1, 1)
        return int(lost)


    def _finish_command(self, scl_oen, sda_oen):
        self._state = 'IDLE'
        self._active_cmd = None
        self._active_din = 0
        self._set_lines(scl_oen, sda_oen)
        self._sda_chk = 0
        self._cmd_ack = 1


    def _fsm_step(self, cmd, din, fsm_tick):
        if self._state == 'IDLE':
            if not fsm_tick:
                return
            self._set_lines(1, 1)
            if cmd == 1:
                self._active_cmd = 'START'
                self._active_din = din & 1
                self._state = 'START_A'
                self._set_lines(1, 1)
            elif cmd == 2:
                self._active_cmd = 'STOP'
                self._active_din = din & 1
                self._state = 'STOP_A'
                self._set_lines(0, 0)
            elif cmd == 4:
                self._active_cmd = 'WRITE'
                self._active_din = din & 1
                self._state = 'WRITE_A'
                self._set_lines(0, 0 if self._active_din == 0 else 1)
            elif cmd == 8:
                self._active_cmd = 'READ'
                self._active_din = din & 1
                self._state = 'READ_A'
                self._set_lines(0, 1)
            return

        if self._state == 'START_A':
            if fsm_tick:
                self._state = 'START_B'
                self._set_lines(1, 0)
            return

        if self._state == 'START_B':
            if fsm_tick:
                self._finish_command(0, 0)
            return

        if self._state == 'STOP_A':
            if fsm_tick:
                self._state = 'STOP_B'
                self._set_lines(1, 0)
            return

        if self._state == 'STOP_B':
            if fsm_tick and self._sSCL == 1:
                self._finish_command(1, 1)
            return

        if self._state == 'READ_A':
            if fsm_tick:
                self._state = 'READ_B'
                self._set_lines(1, 1)
            return

        if self._state == 'READ_B':
            if fsm_tick and self._sSCL == 1:
                self._finish_command(0, 1)
            return

        if self._state == 'WRITE_A':
            if fsm_tick:
                self._state = 'WRITE_B'
                self._set_lines(1, 0 if self._active_din == 0 else 1)
            return

        if self._state == 'WRITE_B':
            if fsm_tick and self._sSCL == 1:
                self._finish_command(0, 0 if self._active_din == 0 else 1)
            return

        self._state = 'IDLE'
        self._active_cmd = None
        self._active_din = 0
        self._set_lines(1, 1)


    def _outputs(self):
        o = {p: None for p in self.OUTPUT_PORTS}
        o['cmd_ack'] = self._cmd_ack & 1
        o['busy'] = self._busy & 1
        o['al'] = self._al & 1
        o['dout'] = self._dout & 1
        o['scl_o'] = 0
        o['scl_oen'] = self._scl_oen & 1
        o['sda_o'] = 0
        o['sda_oen'] = self._sda_oen & 1
        return o


    def step(self, i):
        if (i['nReset'] & 1) == 0:
            self.reset()
            return self._outputs()
        if (i['rst'] & 1) != 0:
            self.reset()
            return self._outputs()

        self._cmd_ack = 0
        enabled = (i['ena'] & 1) != 0
        events = self._filter_step(i, enabled)
        self._bus_event_step(events)
        arbitration_lost = self._arbitration_step(events)
        fsm_tick = self._timing_step(i['clk_cnt'], enabled, events['fall_scl'])

        if enabled and not arbitration_lost:
            self._fsm_step(i['cmd'] & 0xf, i['din'] & 1, fsm_tick)

        return self._outputs()
