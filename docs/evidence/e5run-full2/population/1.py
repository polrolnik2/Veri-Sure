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
    PROBE_PORTS = ['idle', 'cnt_zero', 'clk_en', 'slave_wait', 'scl_sync', 'cscl', 'csda', 'filter_cnt', 'filter_cnt_expired', 'fscl', 'fsda', 'sscl', 'ssda', 'dscl', 'dsda', 'sta_condition', 'sto_condition', 'active_command', 'sda_chk', 'filtered_scl_rise', 'start_sequence', 'stop_sequence', 'read_sequence', 'write_sequence']
    LATENCY_CYCLES = 1

    def __init__(self):
        self.reset()


    def reset(self):
        self.state = 'IDLE'
        self.cmd_latched = 0
        self.din_latched = 0
        self.cSCL1 = 1
        self.cSCL = 1
        self.cSDA1 = 1
        self.cSDA = 1
        self.fSCL = [1, 1, 1]
        self.fSDA = [1, 1, 1]
        self.sSCL = 1
        self.sSDA = 1
        self.dSCL = 1
        self.dSDA = 1
        self.cnt = 0
        self.filter_counter = 0
        self.cmd_ack_r = 0
        self.busy_r = 0
        self.al_r = 0
        self.dout_r = 0
        self._set_probes(0, 0, 0, 0, 0, 0, 0, 0)


    def _set_probes(self, cnt_zero, clk_en, slave_wait, scl_sync,
                    filter_expired, sta, sto, scl_rise):
        self.idle = bool(self.state == 'IDLE')
        self.cnt_zero = bool(cnt_zero)
        self.clk_en = bool(clk_en)
        self.slave_wait = bool(slave_wait)
        self.scl_sync = bool(scl_sync)
        self.cscl = bool(self.cSCL)
        self.csda = bool(self.cSDA)
        self.filter_cnt = bool(self.filter_counter)
        self.filter_cnt_expired = bool(filter_expired)
        self.fscl = bool(self.fSCL[-1])
        self.fsda = bool(self.fSDA[-1])
        self.sscl = bool(self.sSCL)
        self.ssda = bool(self.sSDA)
        self.dscl = bool(self.dSCL)
        self.dsda = bool(self.dSDA)
        self.sta_condition = bool(sta)
        self.sto_condition = bool(sto)
        self.active_command = bool(self.state != 'IDLE')
        self.sda_chk = bool(self.state == 'W1' and self.din_latched == 1)
        self.filtered_scl_rise = bool(scl_rise)
        self.start_sequence = bool(self.state in ('S0', 'S1', 'S2'))
        self.stop_sequence = bool(self.state in ('P0', 'P1', 'P2'))
        self.read_sequence = bool(self.state in ('R0', 'R1', 'R2'))
        self.write_sequence = bool(self.state in ('W0', 'W1', 'W2'))


    def _outputs(self):
        scl_oen = 1
        sda_oen = 1
        if self.state == 'S0':
            scl_oen, sda_oen = 1, 1
        elif self.state == 'S1':
            scl_oen, sda_oen = 1, 0
        elif self.state == 'S2':
            scl_oen, sda_oen = 0, 0
        elif self.state == 'P0':
            scl_oen, sda_oen = 0, 0
        elif self.state == 'P1':
            scl_oen, sda_oen = 1, 0
        elif self.state == 'P2':
            scl_oen, sda_oen = 1, 1
        elif self.state == 'R0':
            scl_oen, sda_oen = 0, 1
        elif self.state == 'R1':
            scl_oen, sda_oen = 1, 1
        elif self.state == 'R2':
            scl_oen, sda_oen = 0, 1
        elif self.state == 'W0':
            scl_oen = 0
            sda_oen = 0 if self.din_latched == 0 else 1
        elif self.state == 'W1':
            scl_oen = 1
            sda_oen = 0 if self.din_latched == 0 else 1
        elif self.state == 'W2':
            scl_oen = 0
            sda_oen = 0 if self.din_latched == 0 else 1
        return scl_oen, sda_oen


    def _filter_inputs(self, i, ena):
        old_scl = self.sSCL
        self.cSCL1 = int(i['scl_i']) & 1
        self.cSCL = self.cSCL1
        self.cSDA1 = int(i['sda_i']) & 1
        self.cSDA = self.cSDA1
        expired = 0
        if ena:
            interval = ((int(i['clk_cnt']) & 0xffff) >> 2)
            if interval == 0 or self.filter_counter == 0:
                expired = 1
                self.filter_counter = interval
                self.fSCL = [self.fSCL[1], self.fSCL[2], self.cSCL]
                self.fSDA = [self.fSDA[1], self.fSDA[2], self.cSDA]
                self.dSCL = self.sSCL
                self.dSDA = self.sSDA
                self.sSCL = int(sum(self.fSCL) >= 2)
                self.sSDA = int(sum(self.fSDA) >= 2)
            else:
                self.filter_counter = (self.filter_counter - 1) & 0xffff
        else:
            self.filter_counter = 0
        rise = int(old_scl == 0 and self.sSCL == 1)
        sta = int(self.sSDA == 0 and self.dSDA == 1 and self.sSCL == 1)
        sto = int(self.sSDA == 1 and self.dSDA == 0 and self.sSCL == 1)
        return expired, rise, sta, sto


    def _timing(self, i, ena, released_scl):
        reload_value = int(i['clk_cnt']) & 0xffff
        if not ena:
            self.cnt = reload_value
            return 0, 0, 0
        wait = int(bool(released_scl and self.sSCL == 0))
        sync = int(bool(released_scl and self.dSCL == 1 and self.sSCL == 0))
        if wait:
            return 0, wait, sync
        if self.cnt == 0 or sync:
            self.cnt = reload_value
            return 1, 0, sync
        self.cnt = (self.cnt - 1) & 0xffff
        return 0, 0, sync


    def _status(self, sta, sto, rise):
        if sta:
            self.busy_r = 1
        if sto:
            self.busy_r = 0
        if rise:
            self.dout_r = int(bool(self.sSDA))


    def _advance_fsm(self, i, tick, sto):
        if self.al_r:
            self.state = 'IDLE'
            return
        if self.state != 'IDLE' and sto and self.cmd_latched != 2:
            self.al_r = 1
            self.state = 'IDLE'
            return
        if self.state == 'W1' and self.din_latched == 1 and self.sSDA == 0:
            self.al_r = 1
            self.state = 'IDLE'
            return
        if not tick:
            return
        if self.state == 'IDLE':
            c = int(i['cmd']) & 0xf
            if c in (1, 2, 4, 8):
                self.cmd_latched = c
                self.din_latched = int(i['din']) & 1
                self.state = {1: 'S0', 2: 'P0', 4: 'W0', 8: 'R0'}[c]
        elif self.state == 'S0':
            self.state = 'S1'
        elif self.state == 'S1':
            self.state = 'S2'
        elif self.state == 'S2':
            self.state = 'IDLE'
            self.cmd_ack_r = 1
        elif self.state == 'P0':
            self.state = 'P1'
        elif self.state == 'P1':
            if self.sSCL:
                self.state = 'P2'
        elif self.state == 'P2':
            self.state = 'IDLE'
            self.cmd_ack_r = 1
        elif self.state == 'R0':
            self.state = 'R1'
        elif self.state == 'R1':
            if self.sSCL:
                self.state = 'R2'
        elif self.state == 'R2':
            self.state = 'IDLE'
            self.cmd_ack_r = 1
        elif self.state == 'W0':
            self.state = 'W1'
        elif self.state == 'W1':
            if self.sSCL:
                self.state = 'W2'
        elif self.state == 'W2':
            self.state = 'IDLE'
            self.cmd_ack_r = 1


    def step(self, i):
        o = {p: None for p in self.OUTPUT_PORTS}
        self.cmd_ack_r = 0
        if int(i['nReset']) == 0:
            self.reset()
        elif int(i['rst']) != 0:
            self.reset()
        else:
            ena = int(i['ena']) & 1
            old_scl_oen, _ = self._outputs()
            released_scl = old_scl_oen == 1
            expired, rise, sta, sto = self._filter_inputs(i, ena)
            tick, wait, sync = self._timing(i, ena, released_scl)
            self._status(sta, sto, rise)
            if ena:
                self._advance_fsm(i, tick, sto)
            self._set_probes(self.cnt == 0, tick, wait, sync,
                             expired, sta, sto, rise)
        scl_oen, sda_oen = self._outputs()
        o['cmd_ack'] = int(self.cmd_ack_r)
        o['busy'] = int(self.busy_r)
        o['al'] = int(self.al_r)
        o['dout'] = int(self.dout_r)
        o['scl_o'] = 0
        o['scl_oen'] = int(scl_oen)
        o['sda_o'] = 0
        o['sda_oen'] = int(sda_oen)
        return o
