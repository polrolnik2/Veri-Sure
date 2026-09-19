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
    LATENCY_CYCLES = 1

    def _req_0000(self, i, o):
        o['scl_o'] = 0

    def _req_0001(self, i, o):
        o['sda_o'] = 0

    def _req_0002(self, i, o):
        value = o.get('scl_oen')
        o['scl_oen'] = 1 if value is None else (value & 1)

    def _req_0003(self, i, o):
        value = o.get('sda_oen')
        o['sda_oen'] = 1 if value is None else (value & 1)

    def _req_0004(self, i, o):
        pass

    def _req_0005(self, i, o):
        if not getattr(self, '_ib_init', False):
            self._ib_init = True
            self._cnt = 0
            self._filter_cnt = 0
            self._c_scl_1 = 1
            self._c_scl_2 = 1
            self._c_sda_1 = 1
            self._c_sda_2 = 1
            self._fh_scl = [1, 1, 1]
            self._fh_sda = [1, 1, 1]
            self._scl_f = 1
            self._sda_f = 1
            self._d_scl = 1
            self._d_sda = 1
            self._phase = 'idle'
            self._active_cmd = 0
            self._din = 0
            self._scl_oen = 1
            self._sda_oen = 1
            self._cmd_ack = 0
            self._busy = 0
            self._al = 0
            self._dout = 0

        if (i['nReset'] & 1) == 0 or (i.get('rst', 0) & 1):
            self._cnt = 0
            self._filter_cnt = 0
            self._c_scl_1 = 1
            self._c_scl_2 = 1
            self._c_sda_1 = 1
            self._c_sda_2 = 1
            self._fh_scl = [1, 1, 1]
            self._fh_sda = [1, 1, 1]
            self._scl_f = 1
            self._sda_f = 1
            self._d_scl = 1
            self._d_sda = 1
            self._phase = 'idle'
            self._active_cmd = 0
            self._din = 0
            self._scl_oen = 1
            self._sda_oen = 1
            self._cmd_ack = 0
            self._busy = 0
            self._al = 0
            self._dout = 0
            o['cmd_ack'] = 0
            o['busy'] = 0
            o['al'] = 0
            o['dout'] = 0
            o['scl_o'] = 0
            o['scl_oen'] = 1
            o['sda_o'] = 0
            o['sda_oen'] = 1
            return

        clk_cnt = self.mask(i['clk_cnt'], 16)
        old_scl_f = self._scl_f
        old_sda_f = self._sda_f
        old_d_scl = self._d_scl
        old_d_sda = self._d_sda

        self._c_scl_1 = i['scl_i'] & 1
        self._c_scl_2 = self._c_scl_1
        self._c_sda_1 = i['sda_i'] & 1
        self._c_sda_2 = self._c_sda_1
        self._cmd_ack = 0

        if (i['ena'] & 1) == 0:
            self._cnt = clk_cnt
            self._filter_cnt = 0
        else:
            start_condition = old_sda_f == 0 and old_d_sda == 1 and old_scl_f == 1
            stop_condition = old_sda_f == 1 and old_d_sda == 0 and old_scl_f == 1
            rising_scl = old_scl_f == 1 and old_d_scl == 0

            if start_condition:
                self._busy = 1
            if stop_condition:
                self._busy = 0
            if rising_scl:
                self._dout = old_sda_f & 1

            if self._filter_cnt == 0:
                self._filter_cnt = (clk_cnt >> 2) & 0x3fff
                self._fh_scl = [self._fh_scl[1], self._fh_scl[2], self._c_scl_2]
                self._fh_sda = [self._fh_sda[1], self._fh_sda[2], self._c_sda_2]
                self._scl_f = 1 if sum(self._fh_scl) >= 2 else 0
                self._sda_f = 1 if sum(self._fh_sda) >= 2 else 0
            else:
                self._filter_cnt = (self._filter_cnt - 1) & 0x3fff

            self._d_scl = old_scl_f
            self._d_sda = old_sda_f

            scl_sync = self._scl_oen == 1 and old_scl_f == 0 and old_d_scl == 1
            slave_wait = self._scl_oen == 1 and old_scl_f == 0

            if scl_sync:
                self._cnt = clk_cnt
                clk_en = 1
            elif slave_wait:
                clk_en = 0
            elif self._cnt == 0:
                self._cnt = clk_cnt
                clk_en = 1
            else:
                self._cnt = (self._cnt - 1) & 0xffff
                clk_en = 0

            arbitration_loss = False
            if stop_condition and self._phase != 'idle' and self._active_cmd != 2:
                arbitration_loss = True
            if (self._phase == 'write_b' and self._din == 1 and
                    self._sda_oen == 1 and old_scl_f == 1 and old_sda_f == 0):
                arbitration_loss = True

            if arbitration_loss:
                self._al = 1
                self._phase = 'idle'
                self._active_cmd = 0
                self._scl_oen = 1
                self._sda_oen = 1
                self._cmd_ack = 0
            elif self._al:
                self._phase = 'idle'
                self._active_cmd = 0
                self._scl_oen = 1
                self._sda_oen = 1
                self._cmd_ack = 0
            elif clk_en:
                cmd = self.mask(i['cmd'], 4)
                if self._phase == 'idle':
                    if cmd in (1, 2, 4, 8):
                        self._active_cmd = cmd
                        self._din = i['din'] & 1
                        if cmd == 1:
                            self._phase = 'start_a'
                        elif cmd == 2:
                            self._phase = 'stop_a'
                        elif cmd == 4:
                            self._phase = 'read_a'
                        else:
                            self._phase = 'write_a'
                elif self._phase == 'start_a':
                    self._scl_oen = 1
                    self._sda_oen = 1
                    self._phase = 'start_b'
                elif self._phase == 'start_b':
                    self._scl_oen = 1
                    self._sda_oen = 0
                    self._phase = 'start_c'
                elif self._phase == 'start_c':
                    self._scl_oen = 0
                    self._sda_oen = 0
                    self._phase = 'idle'
                    self._active_cmd = 0
                    self._cmd_ack = 1
                elif self._phase == 'stop_a':
                    self._scl_oen = 0
                    self._sda_oen = 0
                    self._phase = 'stop_b'
                elif self._phase == 'stop_b':
                    self._scl_oen = 1
                    self._sda_oen = 0
                    if old_scl_f == 1:
                        self._phase = 'stop_c'
                elif self._phase == 'stop_c':
                    self._scl_oen = 1
                    self._sda_oen = 1
                    self._phase = 'idle'
                    self._active_cmd = 0
                    self._cmd_ack = 1
                elif self._phase == 'read_a':
                    self._scl_oen = 0
                    self._sda_oen = 1
                    self._phase = 'read_b'
                elif self._phase == 'read_b':
                    self._scl_oen = 1
                    self._sda_oen = 1
                    if old_scl_f == 1:
                        self._phase = 'read_c'
                elif self._phase == 'read_c':
                    self._scl_oen = 0
                    self._sda_oen = 1
                    self._phase = 'idle'
                    self._active_cmd = 0
                    self._cmd_ack = 1
                elif self._phase == 'write_a':
                    self._scl_oen = 0
                    self._sda_oen = 0 if self._din == 0 else 1
                    self._phase = 'write_b'
                elif self._phase == 'write_b':
                    self._scl_oen = 1
                    self._sda_oen = 0 if self._din == 0 else 1
                    if old_scl_f == 1:
                        self._phase = 'write_c'
                elif self._phase == 'write_c':
                    self._scl_oen = 0
                    self._sda_oen = 0 if self._din == 0 else 1
                    self._phase = 'idle'
                    self._active_cmd = 0
                    self._cmd_ack = 1

        o['cmd_ack'] = self._cmd_ack & 1
        o['busy'] = self._busy & 1
        o['al'] = self._al & 1
        o['dout'] = self._dout & 1
        o['scl_o'] = 0
        o['scl_oen'] = self._scl_oen & 1
        o['sda_o'] = 0
        o['sda_oen'] = self._sda_oen & 1

    def _req_0006(self, i, o):
        if (i['nReset'] & 1) == 0:
            o['cmd_ack'] = 0
            o['busy'] = 0
            o['al'] = 0
            o['dout'] = 0
            o['scl_oen'] = 1
            o['sda_oen'] = 1

    def _req_0007(self, i, o):
        pass

    def _req_0008(self, i, o):
        pass

    def _req_0009(self, i, o):
        pass

    def _req_0010(self, i, o):
        pass

    def _req_0011(self, i, o):
        pass

    def _req_0012(self, i, o):
        pass

    def _req_0013(self, i, o):
        o['busy'] = self._busy & 1

    def _req_0014(self, i, o):
        pass

    def _req_0015(self, i, o):
        pass

    def _req_0016(self, i, o):
        o['al'] = self._al & 1

    def _req_0017(self, i, o):
        o['al'] = self._al & 1

    def _req_0018(self, i, o):
        o['scl_oen'] = self._scl_oen & 1
        o['sda_oen'] = self._sda_oen & 1
        o['cmd_ack'] = self._cmd_ack & 1

    def _req_0019(self, i, o):
        o['al'] = self._al & 1

    def _req_0020(self, i, o):
        o['dout'] = self._dout & 1

    def _req_0021(self, i, o):
        pass

    def _req_0022(self, i, o):
        pass

    def _req_0023(self, i, o):
        o['cmd_ack'] = self._cmd_ack & 1

    def _req_0024(self, i, o):
        pass

    def _req_0025(self, i, o):
        pass

    def _req_0026(self, i, o):
        pass

    def _req_0027(self, i, o):
        pass

    def _req_0028(self, i, o):
        o['cmd_ack'] = self._cmd_ack & 1

    def _req_0029(self, i, o):
        o['sda_o'] = 0

    def _req_0030(self, i, o):
        if (i['nReset'] & 1) == 0 or (i.get('rst', 0) & 1):
            o['cmd_ack'] = 0
            o['busy'] = 0
            o['al'] = 0
            o['dout'] = 0
            o['scl_oen'] = 1
            o['sda_oen'] = 1

    def step(self, i):
        o = {p: None for p in self.OUTPUT_PORTS}
        self._req_0000(i, o)
        self._req_0001(i, o)
        self._req_0002(i, o)
        self._req_0003(i, o)
        self._req_0004(i, o)
        self._req_0005(i, o)
        self._req_0006(i, o)
        self._req_0007(i, o)
        self._req_0008(i, o)
        self._req_0009(i, o)
        self._req_0010(i, o)
        self._req_0011(i, o)
        self._req_0012(i, o)
        self._req_0013(i, o)
        self._req_0014(i, o)
        self._req_0015(i, o)
        self._req_0016(i, o)
        self._req_0017(i, o)
        self._req_0018(i, o)
        self._req_0019(i, o)
        self._req_0020(i, o)
        self._req_0021(i, o)
        self._req_0022(i, o)
        self._req_0023(i, o)
        self._req_0024(i, o)
        self._req_0025(i, o)
        self._req_0026(i, o)
        self._req_0027(i, o)
        self._req_0028(i, o)
        self._req_0029(i, o)
        self._req_0030(i, o)
        return o
