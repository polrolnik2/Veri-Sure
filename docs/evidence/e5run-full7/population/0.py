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
    PROBE_PORTS = ['idle', 'clk_en', 'cnt_zero', 'slave_wait', 'scl_sync', 'cscl', 'csda', 'filter_cnt', 'fscl', 'fsda', 'sscl', 'ssda', 'dscl', 'dsda', 'sta_condition', 'sto_condition', 'active_command', 'sda_chk', 'start_sequence', 'stop_sequence', 'read_sequence', 'write_sequence', 'write_stable_high_phase', 'read_sample_window']
    LATENCY_CYCLES = 1

    def __init__(self):
        self.state = 'idle'
        self.cmd_l = 0
        self.din_l = 0
        self.cSCL1 = 1
        self.cSCL2 = 1
        self.cSDA1 = 1
        self.cSDA2 = 1
        self.fSCL = [1, 1, 1]
        self.fSDA = [1, 1, 1]
        self.sSCL = 1
        self.sSDA = 1
        self.dSCL = 1
        self.dSDA = 1
        self.cnt = 0
        self.filter_counter = 0
        self.busy_l = 0
        self.al_l = 0
        self.dout_l = 0
        self.cmd_ack_l = 0
        self._set_probes()


    def _reset_state(self, clk_cnt):
        self.state = 'idle'
        self.cmd_l = 0
        self.din_l = 0
        self.cSCL1 = 1
        self.cSCL2 = 1
        self.cSDA1 = 1
        self.cSDA2 = 1
        self.fSCL = [1, 1, 1]
        self.fSDA = [1, 1, 1]
        self.sSCL = 1
        self.sSDA = 1
        self.dSCL = 1
        self.dSDA = 1
        self.cnt = self.mask(clk_cnt, 16)
        self.filter_counter = 0
        self.busy_l = 0
        self.al_l = 0
        self.dout_l = 0
        self.cmd_ack_l = 0


    def _outputs_for_state(self):
        scl_oen = 1
        sda_oen = 1
        if self.state == 'start1':
            sda_oen = 0
        elif self.state == 'start2':
            scl_oen, sda_oen = 0, 0
        elif self.state == 'stop0':
            scl_oen, sda_oen = 0, 0
        elif self.state == 'stop1':
            sda_oen = 0
        elif self.state == 'read0':
            scl_oen, sda_oen = 0, 1
        elif self.state == 'read1':
            scl_oen, sda_oen = 1, 1
        elif self.state == 'read2':
            scl_oen, sda_oen = 0, 1
        elif self.state == 'write0':
            scl_oen = 0
            sda_oen = 1 if self.din_l else 0
        elif self.state == 'write1':
            scl_oen = 1
            sda_oen = 1 if self.din_l else 0
        elif self.state == 'write2':
            scl_oen = 0
            sda_oen = 1 if self.din_l else 0
        return scl_oen, sda_oen


    def _set_probes(self, clk_en=0, cnt_zero=0, filter_tick=0,
                    fscl=0, fsda=0, scl_sync=0, sta=0, sto=0):
        self.idle = bool(self.state == 'idle')
        self.clk_en = bool(clk_en)
        self.cnt_zero = bool(cnt_zero)
        self.filter_cnt = bool(filter_tick)
        self.fscl = bool(fscl)
        self.fsda = bool(fsda)
        self.cscl = bool(self.cSCL2)
        self.csda = bool(self.cSDA2)
        self.sscl = bool(self.sSCL)
        self.ssda = bool(self.sSDA)
        self.dscl = bool(self.dSCL)
        self.dsda = bool(self.dSDA)
        self.scl_sync = bool(scl_sync)
        self.sta_condition = bool(sta)
        self.sto_condition = bool(sto)
        self.active_command = bool(self.state != 'idle')
        self.sda_chk = bool(self.state == 'write1' and self.din_l)
        self.start_sequence = bool(self.state.startswith('start'))
        self.stop_sequence = bool(self.state.startswith('stop'))
        self.read_sequence = bool(self.state.startswith('read'))
        self.write_sequence = bool(self.state.startswith('write'))
        self.write_stable_high_phase = bool(self.state == 'write1')
        self.read_sample_window = bool(self.state == 'read1')
        scl_oen, _ = self._outputs_for_state()
        self.slave_wait = bool(scl_oen and not self.sSCL)


    def step(self, i):
        o = {p: None for p in self.OUTPUT_PORTS}
        clk_cnt = self.mask(i.get('clk_cnt', 0), 16)
        nreset = int(bool(i.get('nReset', 0)))
        rst = int(bool(i.get('rst', 0)))
        ena = int(bool(i.get('ena', 0)))

        if not nreset or rst:
            self._reset_state(clk_cnt)
            self._set_probes()
            ack = 0
        else:
            old_scl = self.sSCL
            old_sda = self.sSDA
            old_dsda = self.dSDA

            self.cSCL1 = int(bool(i.get('scl_i', 0)))
            self.cSCL2 = self.cSCL1
            self.cSDA1 = int(bool(i.get('sda_i', 0)))
            self.cSDA2 = self.cSDA1

            filter_tick = 0
            fscl = 0
            fsda = 0
            if ena:
                interval = clk_cnt >> 2
                if interval == 0 or self.filter_counter == 0:
                    filter_tick = 1
                    fscl = 1
                    fsda = 1
                    self.fSCL = [self.fSCL[1], self.fSCL[2], self.cSCL2]
                    self.fSDA = [self.fSDA[1], self.fSDA[2], self.cSDA2]
                    self.filter_counter = interval
                else:
                    self.filter_counter -= 1
            else:
                self.filter_counter = 0

            if filter_tick:
                self.sSCL = int(sum(self.fSCL) >= 2)
                self.sSDA = int(sum(self.fSDA) >= 2)
            self.dSCL = old_scl
            self.dSDA = old_sda

            sta = int((not self.sSDA) and old_dsda and self.sSCL)
            sto = int(self.sSDA and (not old_dsda) and self.sSCL)
            scl_oen, _ = self._outputs_for_state()
            slave_wait = int(scl_oen and not self.sSCL)
            scl_sync = int(scl_oen and old_scl and not self.sSCL)

            if sta:
                self.busy_l = 1
            if sto:
                self.busy_l = 0

            cnt_zero = int(self.cnt == 0)
            clk_en = 0
            if not ena:
                self.cnt = clk_cnt
            elif slave_wait:
                self.cnt = self.mask(self.cnt, 16)
            elif cnt_zero or scl_sync:
                clk_en = 1
                self.cnt = clk_cnt
            else:
                self.cnt = self.mask(self.cnt - 1, 16)

            unexpected_stop = bool(sto and self.state not in ('idle', 'stop0', 'stop1', 'stop2'))
            arbitration = bool(self.state == 'write1' and self.din_l and not self.sSDA)
            lost = bool(arbitration or unexpected_stop)
            if lost:
                self.al_l = 1
                self.state = 'idle'

            if not lost and clk_en:
                if self.state == 'idle':
                    cmd = self.mask(i.get('cmd', 0), 4)
                    if cmd in (1, 2, 4, 8):
                        self.cmd_l = cmd
                        self.din_l = int(bool(i.get('din', 0)))
                        self.state = {1: 'start0', 2: 'stop0', 4: 'write0', 8: 'read0'}[cmd]
                elif self.state == 'start0':
                    self.state = 'start1'
                elif self.state == 'start1':
                    self.state = 'start2'
                elif self.state == 'start2':
                    self.state = 'idle'
                    self.cmd_ack_l = 1
                elif self.state == 'stop0':
                    self.state = 'stop1'
                elif self.state == 'stop1':
                    self.state = 'stop2'
                elif self.state == 'stop2':
                    self.state = 'idle'
                    self.cmd_ack_l = 1
                elif self.state == 'read0':
                    self.state = 'read1'
                elif self.state == 'read1':
                    self.state = 'read2'
                elif self.state == 'read2':
                    self.state = 'idle'
                    self.cmd_ack_l = 1
                elif self.state == 'write0':
                    self.state = 'write1'
                elif self.state == 'write1':
                    self.state = 'write2'
                elif self.state == 'write2':
                    self.state = 'idle'
                    self.cmd_ack_l = 1

            if self.sSCL and not old_scl:
                self.dout_l = int(self.sSDA)

            ack = int(self.cmd_ack_l and not lost)
            self.cmd_ack_l = 0
            self._set_probes(clk_en, cnt_zero, filter_tick, fscl, fsda,
                             scl_sync, sta, sto)

        scl_oen, sda_oen = self._outputs_for_state()
        o['cmd_ack'] = int(ack)
        o['busy'] = int(self.busy_l)
        o['al'] = int(self.al_l)
        o['dout'] = int(self.dout_l)
        o['scl_o'] = 0
        o['scl_oen'] = int(scl_oen)
        o['sda_o'] = 0
        o['sda_oen'] = int(sda_oen)
        return o
