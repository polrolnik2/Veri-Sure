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
    PROBE_PORTS = []
    LATENCY_CYCLES = 0

    def _init(self):
        if getattr(self, '_model_initialized', False):
            return
        self._model_initialized = True
        self._state = 'idle'
        self._phase = 0
        self._active_cmd = 0
        self._cnt = 0
        self._filter_cnt = 0
        self._cSCL = 1
        self._cSDA = 1
        self._sSCL_sync = 1
        self._sSDA_sync = 1
        self._fSCL = [1, 1, 1]
        self._fSDA = [1, 1, 1]
        self._sSCL = 1
        self._sSDA = 1
        self._dSCL = 1
        self._dSDA = 1
        self._busy = 0
        self._al = 0
        self._dout = 0
        self._ack = 0


    def _reset(self, clk_cnt):
        self._state = 'idle'
        self._phase = 0
        self._active_cmd = 0
        self._cnt = self.mask(clk_cnt, 16)
        self._filter_cnt = 0
        self._cSCL = 1
        self._cSDA = 1
        self._sSCL_sync = 1
        self._sSDA_sync = 1
        self._fSCL = [1, 1, 1]
        self._fSDA = [1, 1, 1]
        self._sSCL = 1
        self._sSDA = 1
        self._dSCL = 1
        self._dSDA = 1
        self._busy = 0
        self._al = 0
        self._dout = 0
        self._ack = 0


    def _filter_inputs(self, i):
        self._cSCL, self._sSCL_sync = self._sSCL_sync, int(bool(i['scl_i']))
        self._cSDA, self._sSDA_sync = self._sSDA_sync, int(bool(i['sda_i']))
        if not i['ena']:
            self._filter_cnt = 0
            return
        interval = self.mask(i['clk_cnt'], 16) >> 2
        if self._filter_cnt == 0:
            self._filter_cnt = interval
            self._fSCL = [self._fSCL[1], self._fSCL[2], self._cSCL]
            self._fSDA = [self._fSDA[1], self._fSDA[2], self._cSDA]
            self._dSCL = self._sSCL
            self._dSDA = self._sSDA
            self._sSCL = int(sum(self._fSCL) >= 2)
            self._sSDA = int(sum(self._fSDA) >= 2)
        else:
            self._filter_cnt = self.mask(self._filter_cnt - 1, 16)


    def _timing_tick(self, i, slave_wait=False, sync=False):
        if not i['ena'] or slave_wait or sync:
            self._cnt = self.mask(i['clk_cnt'], 16)
            return False
        if self._cnt == 0:
            self._cnt = self.mask(i['clk_cnt'], 16)
            return True
        self._cnt = self.mask(self._cnt - 1, 16)
        return False


    def _line_enables(self):
        scl_oen = 1
        sda_oen = 1
        if self._state == 'start':
            if self._phase >= 2:
                sda_oen = 0
            if self._phase >= 3:
                scl_oen = 0
        elif self._state == 'stop':
            if self._phase >= 1:
                sda_oen = 0
            if self._phase >= 2:
                scl_oen = 1
            if self._phase >= 3:
                sda_oen = 1
        elif self._state == 'read':
            sda_oen = 1
            if self._phase >= 2 and self._phase < 3:
                scl_oen = 1
            elif self._phase >= 3:
                scl_oen = 0
        elif self._state == 'write':
            sda_oen = 0 if not self._active_din else 1
            if self._phase >= 2 and self._phase < 3:
                scl_oen = 1
            elif self._phase >= 3:
                scl_oen = 0
        return scl_oen, sda_oen


    def _bus_events(self, scl_oen, sda_oen):
        sta = int((not self._sSDA) and self._dSDA and self._sSCL)
        sto = int(self._sSDA and (not self._dSDA) and self._sSCL)
        if sta:
            self._busy = 1
        if sto:
            self._busy = 0
        slave_wait = bool(scl_oen and not self._sSCL)
        scl_sync = bool(scl_oen and self._dSCL and not self._sSCL)
        return sta, sto, slave_wait, scl_sync


    def _advance_fsm(self, i, tick, slave_wait, scl_sync):
        self._ack = 0
        if self._state == 'idle':
            if tick:
                cmd = self.mask(i['cmd'], 4)
                if cmd == 4:
                    self._active_cmd = cmd
                    self._active_din = int(bool(i['din']))
                    self._state = 'start'
                    self._phase = 1
                elif cmd == 5:
                    self._active_cmd = cmd
                    self._active_din = int(bool(i['din']))
                    self._state = 'stop'
                    self._phase = 1
                elif cmd == 2:
                    self._active_cmd = cmd
                    self._active_din = int(bool(i['din']))
                    self._state = 'read'
                    self._phase = 1
                elif cmd == 1:
                    self._active_cmd = cmd
                    self._active_din = int(bool(i['din']))
                    self._state = 'write'
                    self._phase = 1
            return
        if slave_wait:
            return
        if tick:
            if self._state == 'write' and self._phase == 2:
                if self._active_din and not self._sSDA:
                    self._al = 1
                    self._state = 'idle'
                    self._phase = 0
                    return
            if self._phase < 3:
                self._phase += 1
            else:
                if self._state == 'start':
                    self._busy = 1
                elif self._state == 'stop':
                    self._busy = 0
                self._state = 'idle'
                self._phase = 0
                self._ack = 1


    def _outputs(self):
        scl_oen, sda_oen = self._line_enables()
        return {
            'cmd_ack': int(bool(self._ack)),
            'busy': int(bool(self._busy)),
            'al': int(bool(self._al)),
            'dout': int(bool(self._dout)),
            'scl_o': 0,
            'scl_oen': int(bool(scl_oen)),
            'sda_o': 0,
            'sda_oen': int(bool(sda_oen))
        }


    def evaluate(self, i):
        o = {p: None for p in self.OUTPUT_PORTS}
        self._init()
        clk_cnt = self.mask(i['clk_cnt'], 16)
        if not i['nReset']:
            self._reset(clk_cnt)
            return self._outputs()
        if i['rst']:
            self._reset(clk_cnt)
            return self._outputs()

        self._ack = 0
        self._filter_inputs(i)
        old_scl_oen, old_sda_oen = self._line_enables()
        sta, sto, slave_wait, scl_sync = self._bus_events(old_scl_oen, old_sda_oen)

        if self._state != 'idle' and sto and self._active_cmd != 5:
            self._al = 1
            self._state = 'idle'
            self._phase = 0
        elif self._state == 'write' and self._phase == 2 and self._active_din and not self._sSDA:
            self._al = 1
            self._state = 'idle'
            self._phase = 0
        else:
            tick = self._timing_tick(i, slave_wait, scl_sync)
            self._advance_fsm(i, tick, slave_wait, scl_sync)

        if self._sSCL and not self._dSCL:
            self._dout = int(bool(self._sSDA))
        return self._outputs()
