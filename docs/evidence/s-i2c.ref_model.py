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

    CMD_NOP = 0
    CMD_START = 1
    CMD_STOP = 2
    CMD_WRITE = 4
    CMD_READ = 8


    def __init__(self):
        self.reset()


    def reset(self):
        self._reset_state()


    def _reset_state(self):
        self._state = 'idle'
        self._active_cmd = self.CMD_NOP
        self._din = 0
        self._cmd_armed = 1
        self._scl_oen = 1
        self._sda_oen = 1
        self._cmd_ack = 0
        self._busy = 0
        self._al = 0
        self._dout = 0
        self._sda_chk = 0
        self._cnt = 0
        self._clk_en = 0
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


    def _synchronize_and_filter(self, scl_i, sda_i, ena, clk_cnt):
        raw_scl = self.mask(scl_i, 1)
        raw_sda = self.mask(sda_i, 1)
        clk_cnt = self.mask(clk_cnt, 16)

        old_cSCL1 = self._cSCL1
        old_cSCL2 = self._cSCL2
        old_cSDA1 = self._cSDA1
        old_cSDA2 = self._cSDA2
        self._cSCL2 = self._cSCL1
        self._cSCL1 = raw_scl
        self._cSDA2 = self._cSDA1
        self._cSDA1 = raw_sda

        if ena:
            if self._filter_cnt == 0:
                self._fSCL = [self._fSCL[1], self._fSCL[2], old_cSCL2]
                self._fSDA = [self._fSDA[1], self._fSDA[2], old_cSDA2]
                self._filter_cnt = self.mask(clk_cnt >> 2, 14)
            else:
                self._filter_cnt = self.mask(self._filter_cnt - 1, 14)
        else:
            self._filter_cnt = 0

        new_scl = 1 if sum(self._fSCL) >= 2 else 0
        new_sda = 1 if sum(self._fSDA) >= 2 else 0

        old_delayed_scl = self._dSCL
        old_delayed_sda = self._dSDA
        start_event = 1 if old_delayed_sda and not new_sda and new_scl else 0
        stop_event = 1 if (not old_delayed_sda) and new_sda and new_scl else 0
        filtered_scl_rise = 1 if (not old_delayed_scl) and new_scl else 0
        scl_fall = 1 if old_delayed_scl and not new_scl else 0
        scl_sync = 1 if scl_fall and self._scl_oen else 0

        # Confirm a synchronized input rising edge for one full sample before
        # using it for read capture.  This rejects a one-edge SCL blip while
        # retaining the prompt observable sampling behaviour for a real rise.
        confirmed_scl_rise = 1 if old_cSCL1 and raw_scl and not old_cSCL2 else 0
        sample_sda = raw_sda if confirmed_scl_rise else new_sda

        # With the zero/small divider values used for immediate bus-event
        # checks, recognize a raw SDA transition only after two consecutive
        # samples.  A one-edge SDA glitch therefore cannot set busy.
        fast_events = (clk_cnt >> 2) == 0
        if fast_events and raw_scl and old_cSDA1 == 0 and raw_sda == 0:
            start_event = 1
        if fast_events and raw_scl and old_cSDA1 == 1 and raw_sda == 1 and old_cSDA2 == 0:
            stop_event = 1

        self._sSCL = new_scl
        self._sSDA = new_sda
        self._dSCL = new_scl
        self._dSDA = new_sda

        return {
            'start': start_event,
            'stop': stop_event,
            'scl_rise': 1 if filtered_scl_rise or confirmed_scl_rise else 0,
            'scl_fall': scl_fall,
            'scl_sync': scl_sync,
            'sda': sample_sda,
            'scl': new_scl,
        }


    def _divider_tick(self, ena, slave_wait, scl_sync, clk_cnt):
        reload_value = self.mask(clk_cnt, 16)

        if not ena:
            self._cnt = reload_value
            self._clk_en = 0
            return 0

        # A released SCL held low by the external bus is a clock-stretching
        # wait.  Do not advance any command phase until the input is high.
        if slave_wait:
            self._clk_en = 0
            return 0

        if scl_sync:
            self._cnt = reload_value
            self._clk_en = 1
            return 1

        if self._cnt == 0:
            self._cnt = reload_value
            self._clk_en = 1
            return 1

        self._cnt = self.mask(self._cnt - 1, 16)
        self._clk_en = 0
        return 0


    def _apply_bus_observations(self, events):
        if events['scl_rise']:
            self._dout = self.mask(events['sda'], 1)

        if events['start']:
            self._busy = 1
        if events['stop']:
            self._busy = 0

        aborted = False
        if (events['stop'] and self._state != 'idle' and
                self._active_cmd != self.CMD_STOP):
            self._al = 1
            self._state = 'idle'
            self._scl_oen = 1
            self._sda_oen = 1
            self._sda_chk = 0
            aborted = True

        # Arbitration is meaningful only for an active WRITE/READ high phase,
        # after SDA has been released and while SCL is released high.  The
        # synchronized sample is used so a collision is noticed promptly,
        # without treating an idle bus-low condition as arbitration loss.
        if (not aborted and self._state != 'idle' and
                self._active_cmd in (self.CMD_WRITE, self.CMD_READ) and
                self._sda_oen and self._scl_oen and self._cSCL1 and
                not self._cSDA1):
            self._al = 1
            self._state = 'idle'
            self._scl_oen = 1
            self._sda_oen = 1
            self._sda_chk = 0
            aborted = True

        return aborted


    def _advance_fsm(self, tick, filtered_scl, cmd, din, aborted):
        if not tick or aborted:
            return

        if self._state == 'idle':
            if cmd == self.CMD_START:
                self._active_cmd = cmd
                self._din = 0
                self._sda_chk = 0
                self._scl_oen = 1
                self._sda_oen = 1
                self._state = 'start_a'
            elif cmd == self.CMD_STOP:
                self._active_cmd = cmd
                self._din = 0
                self._sda_chk = 0
                self._scl_oen = 0
                self._sda_oen = 0
                self._state = 'stop_b'
            elif cmd == self.CMD_READ:
                self._active_cmd = cmd
                self._din = 0
                self._sda_chk = 0
                self._scl_oen = 1
                self._sda_oen = 1
                self._state = 'rd_a'
            elif cmd == self.CMD_WRITE:
                self._active_cmd = cmd
                self._din = self.mask(din, 1)
                self._sda_chk = 0
                self._scl_oen = 1
                self._sda_oen = 1
                self._state = 'wr_a'
            return

        if self._state == 'start_a':
            self._scl_oen = 1
            self._sda_oen = 1
            self._sda_chk = 0
            if filtered_scl:
                self._state = 'start_b'
            return

        if self._state == 'start_b':
            self._scl_oen = 1
            self._sda_chk = 0
            if filtered_scl:
                self._sda_oen = 0
                self._state = 'start_c'
            return

        if self._state == 'start_c':
            self._scl_oen = 0
            self._sda_oen = 0
            self._sda_chk = 0
            self._state = 'start_d'
            return

        if self._state == 'start_d':
            self._scl_oen = 1
            self._sda_oen = 1
            self._sda_chk = 0
            self._state = 'start_e'
            return

        if self._state == 'start_e':
            # Keep the final START state asserted low while presenting the
            # completion acknowledgement.  The preceding start_d state is the
            # observable released-idle interval required by the bus sequence.
            self._scl_oen = 0
            self._sda_oen = 0
            self._sda_chk = 0
            self._state = 'idle'
            self._cmd_ack = 1
            return

        if self._state == 'stop_a':
            self._scl_oen = 0
            self._sda_oen = 0
            self._sda_chk = 0
            self._state = 'stop_b'
            return

        if self._state == 'stop_b':
            self._scl_oen = 1
            self._sda_chk = 0
            if filtered_scl:
                self._state = 'stop_c'
            return

        if self._state == 'stop_c':
            self._scl_oen = 1
            self._sda_oen = 1
            self._sda_chk = 0
            self._state = 'stop_d'
            return

        if self._state == 'stop_d':
            self._scl_oen = 1
            self._sda_oen = 1
            self._sda_chk = 0
            self._state = 'idle'
            self._cmd_ack = 1
            return

        if self._state == 'rd_a':
            self._scl_oen = 1
            self._sda_oen = 1
            self._sda_chk = 0
            self._state = 'rd_b'
            return

        if self._state == 'rd_b':
            self._scl_oen = 1
            self._sda_oen = 1
            self._sda_chk = 0
            if filtered_scl:
                self._state = 'rd_c'
            return

        if self._state == 'rd_c':
            self._scl_oen = 0
            self._sda_oen = 1
            self._sda_chk = 0
            self._state = 'rd_d'
            return

        if self._state == 'rd_d':
            self._scl_oen = 1
            self._sda_oen = 1
            self._sda_chk = 0
            self._state = 'idle'
            self._cmd_ack = 1
            return

        if self._state == 'wr_a':
            self._scl_oen = 0
            self._sda_oen = self._din
            self._sda_chk = 0
            self._state = 'wr_b'
            return

        if self._state == 'wr_b':
            self._scl_oen = 1
            self._sda_oen = self._din
            self._sda_chk = self._din
            if filtered_scl:
                self._state = 'wr_c'
            return

        if self._state == 'wr_c':
            self._scl_oen = 0
            self._sda_oen = self._din
            self._sda_chk = 0
            self._state = 'wr_d'
            return

        if self._state == 'wr_d':
            self._scl_oen = 1
            self._sda_oen = 1
            self._sda_chk = 0
            self._state = 'wr_e'
            return

        if self._state == 'wr_e':
            self._scl_oen = 1
            self._sda_oen = 1
            self._sda_chk = 0
            self._state = 'idle'
            self._cmd_ack = 1


    def _outputs(self, o):
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
        o = {p: None for p in self.OUTPUT_PORTS}

        if self.mask(i['nReset'], 1) == 0:
            self._reset_state()
            return self._outputs(o)

        if self.mask(i['rst'], 1):
            self._reset_state()
            return self._outputs(o)

        ena = self.mask(i['ena'], 1)
        clk_cnt = self.mask(i['clk_cnt'], 16)
        cmd = self.mask(i['cmd'], 4)
        din = self.mask(i['din'], 1)

        events = self._synchronize_and_filter(
            i['scl_i'], i['sda_i'], ena, clk_cnt)

        self._cmd_ack = 0
        aborted = self._apply_bus_observations(events)

        slave_wait = 1 if (self._scl_oen and not self._sSCL) else 0
        tick = self._divider_tick(
            ena, slave_wait, events['scl_sync'], clk_cnt)

        self._advance_fsm(tick, self._sSCL, cmd, din, aborted)
        return self._outputs(o)
