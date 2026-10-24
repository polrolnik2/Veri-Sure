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
        self._reset_state()

    def _reset_state(self):
        self.state = 'idle'
        self.command = 0
        self.din_latched = 0
        self.scl_oen = 1
        self.sda_oen = 1
        self.cmd_ack = 0
        self.busy = 0
        self.al = 0
        self.dout = 0
        self.cSCL_meta = 1
        self.cSDA_meta = 1
        self.cSCL = 1
        self.cSDA = 1
        self.fSCL = 0b111
        self.fSDA = 0b111
        self.sSCL = 1
        self.sSDA = 1
        self.dSCL = 1
        self.dSDA = 1
        self.cnt = 0
        self.filter_cnt = 0
        self.clk_en = 1
        self.slave_wait = 0
        self.scl_sync = 0
        self.sda_chk = 0

    def _majority(self, history):
        a = (history >> 2) & 1
        b = (history >> 1) & 1
        c = history & 1
        return 1 if (a + b + c) >= 2 else 0

    def _filter_inputs(self, i):
        ena = self.mask(i['ena'], 1)
        raw_scl = self.mask(i['scl_i'], 1)
        raw_sda = self.mask(i['sda_i'], 1)
        clk_cnt = self.mask(i['clk_cnt'], 16)

        old_scl = self.sSCL
        old_sda = self.sSDA
        old_meta_scl = self.cSCL_meta
        old_meta_sda = self.cSDA_meta

        self.dSCL = old_scl
        self.dSDA = old_sda
        self.cSCL_meta = raw_scl
        self.cSDA_meta = raw_sda
        self.cSCL = old_meta_scl
        self.cSDA = old_meta_sda

        if ena:
            if self.filter_cnt == 0:
                interval = self.mask(clk_cnt >> 2, 16)
                self.filter_cnt = interval
                self.fSCL = ((self.fSCL << 1) & 0b110) | self.cSCL
                self.fSDA = ((self.fSDA << 1) & 0b110) | self.cSDA
            else:
                self.filter_cnt = self.mask(self.filter_cnt - 1, 16)
        else:
            self.filter_cnt = 0

        self.sSCL = self._majority(self.fSCL)
        self.sSDA = self._majority(self.fSDA)
        return old_scl, old_sda, self.sSCL, self.sSDA

    def _update_events(self, old_scl, old_sda, new_scl, new_sda):
        start_event = old_sda == 1 and new_sda == 0 and new_scl == 1
        stop_event = old_sda == 0 and new_sda == 1 and new_scl == 1
        rising_scl = old_scl == 0 and new_scl == 1
        falling_scl = old_scl == 1 and new_scl == 0

        self.slave_wait = 1 if self.scl_oen == 1 and new_scl == 0 else 0
        self.scl_sync = 1 if self.scl_oen == 1 and falling_scl else 0

        if rising_scl:
            self.dout = new_sda

        if start_event:
            self.busy = 1
        if stop_event:
            self.busy = 0

        abort = 0
        if stop_event and self.state != 'idle' and self.command != 0x2:
            self.al = 1
            abort = 1

        if (self.sda_chk == 1 and self.sda_oen == 1 and
                new_scl == 1 and new_sda == 0):
            self.al = 1
            abort = 1

        return abort

    def _divider(self, i):
        ena = self.mask(i['ena'], 1)
        clk_cnt = self.mask(i['clk_cnt'], 16)

        if not ena:
            self.cnt = clk_cnt
            self.clk_en = 1
            return

        if self.scl_sync:
            self.cnt = clk_cnt
            self.clk_en = 1
        elif self.slave_wait:
            self.clk_en = 0
        elif self.cnt == 0:
            self.cnt = clk_cnt
            self.clk_en = 1
        else:
            self.cnt = self.mask(self.cnt - 1, 16)
            self.clk_en = 0

    def _command_fsm(self, i, abort):
        ena = self.mask(i['ena'], 1)

        if abort:
            self.state = 'idle'
            self.scl_oen = 1
            self.sda_oen = 1
            self.sda_chk = 0
            return

        if not (ena and self.clk_en and not self.slave_wait):
            return

        if self.state == 'idle':
            command = self.mask(i['cmd'], 4)
            if command in (0x1, 0x2, 0x4, 0x8):
                self.command = command
                self.din_latched = self.mask(i['din'], 1)
                self.sda_chk = 0
                if command == 0x1:
                    self.state = 'start_a'
                elif command == 0x2:
                    self.state = 'stop_a'
                elif command == 0x4:
                    self.state = 'write_a'
                else:
                    self.state = 'read_a'
            return

        if self.state == 'start_a':
            self.scl_oen = 1
            self.sda_oen = 1
            self.state = 'start_b'
        elif self.state == 'start_b':
            self.sda_oen = 0
            self.state = 'start_c'
        elif self.state == 'start_c':
            self.scl_oen = 0
            self.state = 'idle'
            self.cmd_ack = 1
        elif self.state == 'stop_a':
            self.sda_oen = 0
            self.state = 'stop_b'
        elif self.state == 'stop_b':
            self.scl_oen = 1
            self.state = 'stop_c'
        elif self.state == 'stop_c':
            self.sda_oen = 1
            self.state = 'idle'
            self.cmd_ack = 1
        elif self.state == 'read_a':
            self.sda_oen = 1
            self.state = 'read_b'
        elif self.state == 'read_b':
            self.scl_oen = 1
            self.state = 'read_c'
        elif self.state == 'read_c':
            self.scl_oen = 0
            self.state = 'idle'
            self.cmd_ack = 1
        elif self.state == 'write_a':
            self.sda_oen = 0 if self.din_latched == 0 else 1
            self.state = 'write_b'
        elif self.state == 'write_b':
            self.scl_oen = 1
            self.sda_chk = 1 if self.din_latched == 1 else 0
            self.state = 'write_c'
        elif self.state == 'write_c':
            self.scl_oen = 0
            self.sda_chk = 0
            self.state = 'idle'
            self.cmd_ack = 1
        else:
            self.state = 'idle'
            self.sda_chk = 0

    def _outputs(self, o):
        o['cmd_ack'] = self.mask(self.cmd_ack, 1)
        o['busy'] = self.mask(self.busy, 1)
        o['al'] = self.mask(self.al, 1)
        o['dout'] = self.mask(self.dout, 1)
        o['scl_o'] = 0
        o['scl_oen'] = self.mask(self.scl_oen, 1)
        o['sda_o'] = 0
        o['sda_oen'] = self.mask(self.sda_oen, 1)
        return o

    def step(self, i):
        o = {p: None for p in self.OUTPUT_PORTS}

        if self.mask(i['nReset'], 1) == 0:
            self._reset_state()
            return self._outputs(o)

        if self.mask(i['rst'], 1) == 1:
            self._reset_state()
            return self._outputs(o)

        self.cmd_ack = 0
        old_scl, old_sda, new_scl, new_sda = self._filter_inputs(i)
        abort = self._update_events(old_scl, old_sda, new_scl, new_sda)
        self._divider(i)
        self._command_fsm(i, abort)
        return self._outputs(o)
