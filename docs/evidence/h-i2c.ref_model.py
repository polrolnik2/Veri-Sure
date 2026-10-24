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

    IDLE = 0
    START_A = 1
    START_B = 2
    START_C = 3
    STOP_A = 4
    STOP_B = 5
    STOP_C = 6
    STOP_D = 7
    READ_A = 8
    READ_B = 9
    READ_C = 10
    READ_D = 11
    WRITE_A = 12
    WRITE_B = 13
    WRITE_C = 14
    WRITE_D = 15

    def __init__(self):
        self._reset_state()

    def reset(self):
        self._reset_state()

    def _reset_state(self):
        self.state = self.IDLE
        self.active_cmd = self.CMD_NOP
        self.din_latched = 0

        self.cmd_ack = 0
        self.busy = 0
        self.al = 0
        self.dout = 0

        self.scl_oen = 1
        self.sda_oen = 1
        self.sda_chk = 0

        self.cnt = self.mask(0, 16)
        self.clk_en = 1
        self.filter_cnt = self.mask(0, 16)

        # The I2C bus is released/high at reset.  Seed both synchronizer
        # stages and the majority histories to that idle level so reset
        # release does not manufacture spurious filtered bus edges.
        self.cSCL1 = 1
        self.cSCL2 = 1
        self.cSDA1 = 1
        self.cSDA2 = 1
        self.fSCL = self.mask(7, 3)
        self.fSDA = self.mask(7, 3)
        self.scl_filt = 1
        self.sda_filt = 1
        self.dSCL = 1
        self.dSDA = 1

    def _filter_inputs(self, scl_i, sda_i, ena, clk_cnt):
        if not ena:
            self.filter_cnt = self.mask(0, 16)
            return

        old_cSCL1 = self.cSCL1
        old_cSCL2 = self.cSCL2
        old_cSDA1 = self.cSDA1
        old_cSDA2 = self.cSDA2

        self.cSCL1 = self.mask(scl_i, 1)
        self.cSCL2 = old_cSCL1
        self.cSDA1 = self.mask(sda_i, 1)
        self.cSDA2 = old_cSDA1

        if self.filter_cnt == 0:
            self.filter_cnt = self.mask(clk_cnt >> 2, 16)
            self.fSCL = self.mask((self.fSCL << 1) | old_cSCL2, 3)
            self.fSDA = self.mask((self.fSDA << 1) | old_cSDA2, 3)

            scl_ones = ((self.fSCL >> 2) & 1) + ((self.fSCL >> 1) & 1) + (self.fSCL & 1)
            sda_ones = ((self.fSDA >> 2) & 1) + ((self.fSDA >> 1) & 1) + (self.fSDA & 1)
            self.scl_filt = 1 if scl_ones >= 2 else 0
            self.sda_filt = 1 if sda_ones >= 2 else 0
        else:
            self.filter_cnt = self.mask(self.filter_cnt - 1, 16)

    def _bus_events(self):
        start = (self.dSDA == 1 and self.sda_filt == 0 and self.scl_filt == 1)
        stop = (self.dSDA == 0 and self.sda_filt == 1 and self.scl_filt == 1)
        scl_rise = (self.dSCL == 0 and self.scl_filt == 1)
        scl_fall = (self.dSCL == 1 and self.scl_filt == 0)
        return start, stop, scl_rise, scl_fall

    def _update_bus_status(self, start, stop):
        if start:
            self.busy = 1
        elif stop:
            self.busy = 0

    def _advance_divider(self, ena, clk_cnt, slave_wait, scl_sync):
        prescale = self.mask(clk_cnt, 16)

        # Disabling the core freezes command timing.  In particular, do not
        # advertise a timing enable while ena is low: doing so would allow a
        # pending FSM phase to execute on the first disabled-to-enabled edge.
        if not ena:
            self.cnt = prescale
            self.clk_en = 0
            return

        if scl_sync:
            self.cnt = prescale
            self.clk_en = 1
        elif slave_wait:
            self.clk_en = 0
        elif self.cnt == 0:
            self.cnt = prescale
            self.clk_en = 1
        else:
            self.cnt = self.mask(self.cnt - 1, 16)
            self.clk_en = 0

    def _check_arbitration(self, stop_event, scl_level, sda_level):
        unexpected_stop = (
            stop_event and
            self.state != self.IDLE and
            self.active_cmd != self.CMD_STOP
        )
        released_sda_lost = (
            self.sda_chk and
            self.sda_oen == 1 and
            scl_level == 1 and
            sda_level == 0
        )

        if unexpected_stop or released_sda_lost:
            self.al = 1
            self.state = self.IDLE
            self.active_cmd = self.CMD_NOP
            self.sda_chk = 0
            self.scl_oen = 1
            self.sda_oen = 1
            self.cmd_ack = 0
            return True
        return False

    def _capture_data(self, scl_rise):
        if scl_rise:
            self.dout = self.mask(self.sda_filt, 1)

    def _advance_fsm(self, enabled, cmd, din, scl_level, sda_level, stop_event):
        if self._check_arbitration(stop_event, scl_level, sda_level):
            return

        if not enabled or not self.clk_en:
            return

        COMPLETE = 16
        supported = (
            self.CMD_START,
            self.CMD_STOP,
            self.CMD_READ,
            self.CMD_WRITE,
        )

        if self.state == self.IDLE:
            # A command is normally held until acknowledgement.  Do not
            # interpret that same held command as a new command immediately
            # after completion; require the interface to return to NOP first.
            blocked = getattr(self, '_blocked_cmd', self.CMD_NOP)
            if cmd not in supported:
                self._blocked_cmd = self.CMD_NOP
            elif cmd == blocked:
                return
            elif cmd == self.CMD_START:
                self._blocked_cmd = cmd
                self.active_cmd = self.CMD_START
                self.din_latched = self.mask(din, 1)
                self.state = self.START_A
            elif cmd == self.CMD_STOP:
                self._blocked_cmd = cmd
                self.active_cmd = self.CMD_STOP
                self.din_latched = self.mask(din, 1)
                self.state = self.STOP_A
            elif cmd == self.CMD_READ:
                self._blocked_cmd = cmd
                self.active_cmd = self.CMD_READ
                self.din_latched = self.mask(din, 1)
                self.state = self.READ_A
            elif cmd == self.CMD_WRITE:
                self._blocked_cmd = cmd
                self.active_cmd = self.CMD_WRITE
                self.din_latched = self.mask(din, 1)
                self.state = self.WRITE_A

        elif self.state == self.START_A:
            self.scl_oen = 1
            self.sda_oen = 1
            self.state = self.START_B

        elif self.state == self.START_B:
            self.sda_oen = 0
            self.state = self.START_C

        elif self.state == self.START_C:
            self.scl_oen = 0
            self.state = COMPLETE
            self.active_cmd = self.CMD_NOP
            self.sda_chk = 0

        elif self.state == self.STOP_A:
            self.sda_oen = 0
            self.scl_oen = 0
            self.state = self.STOP_B

        elif self.state == self.STOP_B:
            self.scl_oen = 1
            self.state = self.STOP_C

        elif self.state == self.STOP_C:
            if scl_level == 1:
                self.state = self.STOP_D

        elif self.state == self.STOP_D:
            self.sda_oen = 1
            self.state = COMPLETE
            self.active_cmd = self.CMD_NOP
            self.sda_chk = 0

        elif self.state == self.READ_A:
            self.sda_oen = 1
            self.sda_chk = 1
            self.state = self.READ_B

        elif self.state == self.READ_B:
            self.scl_oen = 1
            self.state = self.READ_C

        elif self.state == self.READ_C:
            if scl_level == 1:
                self.state = self.READ_D

        elif self.state == self.READ_D:
            self.scl_oen = 0
            self.state = COMPLETE
            self.active_cmd = self.CMD_NOP
            self.sda_chk = 0

        elif self.state == self.WRITE_A:
            self.sda_oen = self.din_latched
            self.state = self.WRITE_B

        elif self.state == self.WRITE_B:
            self.scl_oen = 1
            self.sda_chk = 1 if self.sda_oen == 1 else 0
            self.state = self.WRITE_C

        elif self.state == self.WRITE_C:
            if scl_level == 1:
                self.state = self.WRITE_D

        elif self.state == self.WRITE_D:
            self.scl_oen = 0
            self.sda_chk = 0
            self.state = COMPLETE
            self.active_cmd = self.CMD_NOP

        elif self.state == self.COMPLETE:
            # Completion returns the controller to the released idle bus.
            # The command's final driven phase was visible in the preceding
            # cycle; acknowledgement is issued with both open-drain outputs
            # released.
            self.scl_oen = 1
            self.sda_oen = 1
            self.state = self.IDLE
            self.cmd_ack = 1

    def _write_outputs(self, o):
        o['cmd_ack'] = self.mask(self.cmd_ack, 1)
        o['busy'] = self.mask(self.busy, 1)
        o['al'] = self.mask(self.al, 1)
        o['dout'] = self.mask(self.dout, 1)
        o['scl_o'] = 0
        o['scl_oen'] = self.mask(self.scl_oen, 1)
        o['sda_o'] = 0
        o['sda_oen'] = self.mask(self.sda_oen, 1)

    def step(self, i):
        o = {p: None for p in self.OUTPUT_PORTS}

        nreset = self.mask(i['nReset'], 1)
        if nreset == 0:
            self._reset_state()
            self._write_outputs(o)
            return o

        if self.mask(i['rst'], 1) == 1:
            self._reset_state()
            self._write_outputs(o)
            return o

        ena = self.mask(i['ena'], 1)
        clk_cnt = self.mask(i['clk_cnt'], 16)
        cmd = self.mask(i['cmd'], 4)
        din = self.mask(i['din'], 1)
        scl_i = self.mask(i['scl_i'], 1)
        sda_i = self.mask(i['sda_i'], 1)

        old_scl = self.scl_filt
        old_sda = self.sda_filt
        start, stop, scl_rise, scl_fall = self._bus_events()

        self._update_bus_status(start, stop)
        self._capture_data(scl_rise)

        self.dSCL = old_scl
        self.dSDA = old_sda

        slave_wait = (self.scl_oen == 1 and old_scl == 0)
        scl_sync = (self.scl_oen == 1 and scl_fall)
        self._advance_divider(ena == 1, clk_cnt, slave_wait, scl_sync)

        self.cmd_ack = 0
        self._advance_fsm(
            ena == 1,
            cmd,
            din,
            old_scl,
            old_sda,
            stop
        )

        self._filter_inputs(scl_i, sda_i, ena == 1, clk_cnt)

        self._write_outputs(o)
        return o
