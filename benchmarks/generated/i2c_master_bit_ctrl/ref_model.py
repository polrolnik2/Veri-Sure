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
        self._prev_clk = 0
        self._reset_state(0)


    def _reset_state(self, clk_cnt=0):
        self.state = 'IDLE'
        self.active_cmd = 0
        self.din_latched = 0
        self.cnt = self.mask(clk_cnt, 16)
        self.clk_en = 1
        self.filter_cnt = 0
        self.cSCL = [1, 1]
        self.cSDA = [1, 1]
        self.fSCL = [1, 1, 1]
        self.fSDA = [1, 1, 1]
        self.sSCL = 1
        self.sSDA = 1
        self.dSCL = 1
        self.dSDA = 1
        self.busy = 0
        self.al = 0
        self.dout = 0
        self.cmd_ack = 0


    def _majority(self, history):
        return 1 if ((history[0] & history[1]) | (history[1] & history[2]) | (history[0] & history[2])) else 0


    def _update_filter(self, ena, clk_cnt, scl_i, sda_i):
        old_scl = self.sSCL
        old_sda = self.sSDA

        self.cSCL[1] = self.cSCL[0]
        self.cSCL[0] = scl_i
        self.cSDA[1] = self.cSDA[0]
        self.cSDA[0] = sda_i

        if not ena:
            self.filter_cnt = 0
        elif self.filter_cnt == 0:
            self.fSCL = [self.fSCL[1], self.fSCL[2], self.cSCL[1]]
            self.fSDA = [self.fSDA[1], self.fSDA[2], self.cSDA[1]]
            self.sSCL = self._majority(self.fSCL)
            self.sSDA = self._majority(self.fSDA)
            self.filter_cnt = self.mask(clk_cnt >> 2, 16)
        else:
            self.filter_cnt = self.mask(self.filter_cnt - 1, 16)

        self.dSCL = old_scl
        self.dSDA = old_sda

        return {
            'scl': self.sSCL,
            'sda': self.sSDA,
            'scl_rising': old_scl == 0 and self.sSCL == 1,
            'scl_falling': old_scl == 1 and self.sSCL == 0,
            'start': old_sda == 1 and self.sSDA == 0 and self.sSCL == 1,
            'stop': old_sda == 0 and self.sSDA == 1 and self.sSCL == 1,
        }


    def _state_outputs(self):
        if self.state == 'STA_A':
            return 1, 1
        if self.state == 'STA_B':
            return 1, 0
        if self.state == 'STA_C':
            return 0, 0
        if self.state == 'STO_A':
            return 0, 0
        if self.state == 'STO_B':
            return 1, 0
        if self.state == 'STO_C':
            return 1, 1
        if self.state == 'RD_A':
            return 0, 1
        if self.state == 'RD_B':
            return 1, 1
        if self.state == 'RD_C':
            return 0, 1
        if self.state == 'WR_A':
            return 0, self.din_latched
        if self.state == 'WR_B':
            return 1, self.din_latched
        if self.state == 'WR_C':
            return 0, self.din_latched
        return 1, 1


    def _sda_check_active(self):
        return self.state == 'WR_B' and self.din_latched == 1


    def _divider_tick(self, ena, clk_cnt, slave_wait, scl_sync):
        if not ena:
            self.cnt = self.mask(clk_cnt, 16)
            self.clk_en = 1
            return True

        if scl_sync:
            self.cnt = self.mask(clk_cnt, 16)
            self.clk_en = 1
            return True

        if slave_wait:
            self.clk_en = 0
            return False

        if self.cnt == 0:
            self.cnt = self.mask(clk_cnt, 16)
            self.clk_en = 1
            return True

        self.cnt = self.mask(self.cnt - 1, 16)
        self.clk_en = 0
        return False


    def _bus_events(self, events):
        if events['start']:
            self.busy = 1
        if events['stop']:
            self.busy = 0

        if events['scl_rising']:
            self.dout = self.mask(events['sda'], 1)

        loss = False
        if events['stop'] and self.state != 'IDLE' and self.active_cmd != 2:
            loss = True
        if self._sda_check_active() and self.sSDA == 0:
            loss = True

        if loss:
            self.al = 1
            self.state = 'IDLE'
            self.active_cmd = 0
            return True
        return False


    def _advance_fsm(self, cmd, din, tick, events):
        if not tick or self.al:
            return

        if self.state == 'IDLE':
            if cmd == 1:
                self.active_cmd = 1
                self.state = 'STA_A'
            elif cmd == 2:
                self.active_cmd = 2
                self.state = 'STO_A'
            elif cmd == 4:
                self.active_cmd = 4
                self.din_latched = din
                self.state = 'WR_A'
            elif cmd == 8:
                self.active_cmd = 8
                self.state = 'RD_A'
            return

        if self.state == 'STA_A':
            self.state = 'STA_B'
        elif self.state == 'STA_B':
            self.state = 'STA_C'
        elif self.state == 'STA_C':
            self.state = 'IDLE'
            self.active_cmd = 0
            self.cmd_ack = 1
        elif self.state == 'STO_A':
            self.state = 'STO_B'
        elif self.state == 'STO_B':
            if events['scl'] == 1:
                self.state = 'STO_C'
        elif self.state == 'STO_C':
            self.state = 'IDLE'
            self.active_cmd = 0
            self.cmd_ack = 1
        elif self.state == 'RD_A':
            self.state = 'RD_B'
        elif self.state == 'RD_B':
            self.state = 'RD_C'
        elif self.state == 'RD_C':
            self.state = 'IDLE'
            self.active_cmd = 0
            self.cmd_ack = 1
        elif self.state == 'WR_A':
            self.state = 'WR_B'
        elif self.state == 'WR_B':
            self.state = 'WR_C'
        elif self.state == 'WR_C':
            self.state = 'IDLE'
            self.active_cmd = 0
            self.cmd_ack = 1


    def _write_outputs(self, o):
        scl_oen, sda_oen = self._state_outputs()
        o['cmd_ack'] = self.mask(self.cmd_ack, 1)
        o['busy'] = self.mask(self.busy, 1)
        o['al'] = self.mask(self.al, 1)
        o['dout'] = self.mask(self.dout, 1)
        o['scl_o'] = 0
        o['scl_oen'] = self.mask(scl_oen, 1)
        o['sda_o'] = 0
        o['sda_oen'] = self.mask(sda_oen, 1)


    def step(self, i):
        o = {p: None for p in self.OUTPUT_PORTS}

        clk = self.mask(i['clk'], 1)
        rst = self.mask(i['rst'], 1)
        nReset = self.mask(i['nReset'], 1)
        ena = self.mask(i['ena'], 1)
        clk_cnt = self.mask(i['clk_cnt'], 16)
        cmd = self.mask(i['cmd'], 4)
        din = self.mask(i['din'], 1)
        scl_i = self.mask(i['scl_i'], 1)
        sda_i = self.mask(i['sda_i'], 1)

        posedge = self._prev_clk == 0 and clk == 1
        self._prev_clk = clk

        if nReset == 0:
            self._reset_state(clk_cnt)
            self._write_outputs(o)
            return o

        if not posedge:
            self._write_outputs(o)
            return o

        if rst == 1:
            self._reset_state(clk_cnt)
            self._write_outputs(o)
            return o

        self.cmd_ack = 0

        events = self._update_filter(ena, clk_cnt, scl_i, sda_i)
        scl_oen, _ = self._state_outputs()
        slave_wait = bool(scl_oen and self.sSCL == 0)
        scl_sync = bool(scl_oen and events['scl_falling'])

        tick = self._divider_tick(ena, clk_cnt, slave_wait, scl_sync)
        lost = self._bus_events(events)

        if not lost:
            fsm_tick = bool(tick and ena and not slave_wait)
            self._advance_fsm(cmd, din, fsm_tick, events)

        self._write_outputs(o)
        return o
