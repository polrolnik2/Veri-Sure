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
    PROBE_PORTS = ['cscl', 'csda', 'sscl', 'ssda', 'dscl', 'dsda', 'fscl', 'fsda', 'filter_cnt', 'cnt_zero', 'clk_en', 'slave_wait', 'scl_sync', 'sta_condition', 'sto_condition', 'sda_chk', 'idle', 'fsm_active', 'start_sequence', 'stop_sequence', 'read_sequence', 'write_sequence', 'filtered_scl_rising', 'filtered_scl_falling', 'i2c_master_bit_ctrl']
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
        self._set_probes(False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False)


    def _set_probes(self, clk_en, slave_wait, scl_sync, sta, sto, sda_chk,
                    filtered_rise, filtered_fall, filter_tick, cnt_zero,
                    fsm_active, start, stop, read, write, unused):
        self.cscl = bool(self.cSCL)
        self.csda = bool(self.cSDA)
        self.sscl = bool(self.sSCL)
        self.ssda = bool(self.sSDA)
        self.dscl = bool(self.dSCL)
        self.dsda = bool(self.dSDA)
        self.fscl = bool(self.fSCL[-1])
        self.fsda = bool(self.fSDA[-1])
        self.filter_cnt = bool(filter_tick)
        self.cnt_zero = bool(cnt_zero)
        self.clk_en = bool(clk_en)
        self.slave_wait = bool(slave_wait)
        self.scl_sync = bool(scl_sync)
        self.sta_condition = bool(sta)
        self.sto_condition = bool(sto)
        self.sda_chk = bool(sda_chk)
        self.idle = self.state == 'IDLE'
        self.fsm_active = self.state != 'IDLE'
        self.start_sequence = self.state.startswith('START')
        self.stop_sequence = self.state.startswith('STOP')
        self.read_sequence = self.state.startswith('READ')
        self.write_sequence = self.state.startswith('WRITE')
        self.filtered_scl_rising = bool(filtered_rise)
        self.filtered_scl_falling = bool(filtered_fall)
        self.i2c_master_bit_ctrl = True


    def _outputs(self):
        scl_oen = 1
        sda_oen = 1
        if self.state == 'START_SDA':
            sda_oen = 0
        elif self.state == 'START_LOW':
            scl_oen = 0
            sda_oen = 0
        elif self.state == 'STOP_LOW':
            scl_oen = 0
            sda_oen = 0
        elif self.state == 'STOP_HIGH':
            sda_oen = 0
        elif self.state == 'READ_HIGH':
            sda_oen = 1
        elif self.state == 'READ_LOW':
            scl_oen = 0
            sda_oen = 1
        elif self.state == 'WRITE_LOW':
            scl_oen = 0
            sda_oen = 0 if self.din_latched == 0 else 1
        elif self.state == 'WRITE_HIGH':
            sda_oen = 0 if self.din_latched == 0 else 1
        return scl_oen, sda_oen


    def step(self, i):
        o = {p: None for p in self.OUTPUT_PORTS}
        nreset = int(i.get('nReset', 1)) & 1
        rst = int(i.get('rst', 0)) & 1
        ena = int(i.get('ena', 0)) & 1
        clk_cnt = self.mask(int(i.get('clk_cnt', 0)), 16)
        cmd = self.mask(int(i.get('cmd', 0)), 4)
        din = int(i.get('din', 0)) & 1
        scl_i = int(i.get('scl_i', 1)) & 1
        sda_i = int(i.get('sda_i', 1)) & 1

        if not nreset or rst:
            self.reset()
        else:
            self.cmd_ack_r = 0

            old_scl = self.sSCL
            old_sda = self.sSDA
            self.cSCL1 = scl_i
            self.cSCL = self.cSCL1
            self.cSDA1 = sda_i
            self.cSDA = self.cSDA1

            interval = clk_cnt >> 2
            if interval < 1:
                interval = 1
            filter_tick = False
            if not ena:
                self.filter_counter = 0
            elif self.filter_counter <= 0:
                filter_tick = True
                self.filter_counter = interval - 1
                self.fSCL = [self.fSCL[1], self.fSCL[2], self.cSCL]
                self.fSDA = [self.fSDA[1], self.fSDA[2], self.cSDA]
                self.sSCL = 1 if sum(self.fSCL) >= 2 else 0
                self.sSDA = 1 if sum(self.fSDA) >= 2 else 0
            else:
                self.filter_counter -= 1

            self.dSCL = old_scl
            self.dSDA = old_sda
            filtered_rise = (not old_scl) and bool(self.sSCL)
            filtered_fall = bool(old_scl) and (not self.sSCL)
            sta = bool((not self.sSDA) and self.dSDA and self.sSCL)
            sto = bool(self.sSDA and (not self.dSDA) and self.sSCL)

            if sta:
                self.busy_r = 1
            if sto:
                self.busy_r = 0
            if filtered_rise:
                self.dout_r = self.sSDA

            scl_oen, sda_oen = self._outputs()
            slave_wait = bool(scl_oen and not self.sSCL)
            scl_sync = bool(scl_oen and filtered_fall)
            sda_chk = bool(self.state == 'WRITE_HIGH' and self.din_latched)

            if sda_chk and not self.sSDA:
                self.al_r = 1
            if sto and self.state != 'IDLE' and not self.state.startswith('STOP'):
                self.al_r = 1
            if self.al_r:
                self.state = 'IDLE'
                self.cmd_ack_r = 0
            else:
                tick = False
                if not ena:
                    self.cnt = clk_cnt
                elif slave_wait:
                    tick = False
                elif scl_sync:
                    self.cnt = clk_cnt
                    tick = True
                elif self.cnt <= 0:
                    self.cnt = clk_cnt
                    tick = True
                else:
                    self.cnt -= 1

                if ena and tick and self.state == 'IDLE':
                    if cmd in (1, 2, 4, 8):
                        self.cmd_latched = cmd
                        self.din_latched = din
                        if cmd == 1:
                            self.state = 'START_SDA'
                        elif cmd == 2:
                            self.state = 'STOP_LOW'
                        elif cmd == 4:
                            self.state = 'WRITE_LOW'
                        else:
                            self.state = 'READ_LOW'
                elif ena and tick and not slave_wait:
                    if self.state == 'START_SDA':
                        self.state = 'START_LOW'
                    elif self.state == 'START_LOW':
                        self.state = 'IDLE'
                        self.cmd_ack_r = 1
                    elif self.state == 'STOP_LOW':
                        self.state = 'STOP_HIGH'
                    elif self.state == 'STOP_HIGH':
                        if self.sSCL:
                            self.state = 'IDLE'
                            self.cmd_ack_r = 1
                    elif self.state == 'READ_LOW':
                        self.state = 'READ_HIGH'
                    elif self.state == 'READ_HIGH':
                        if self.sSCL:
                            self.state = 'READ_DONE'
                    elif self.state == 'READ_DONE':
                        self.state = 'IDLE'
                        self.cmd_ack_r = 1
                    elif self.state == 'WRITE_LOW':
                        self.state = 'WRITE_HIGH'
                    elif self.state == 'WRITE_HIGH':
                        if self.sSCL:
                            self.state = 'WRITE_DONE'
                    elif self.state == 'WRITE_DONE':
                        self.state = 'IDLE'
                        self.cmd_ack_r = 1

            self._set_probes(
                bool(ena and self.cnt <= 0 and not slave_wait),
                slave_wait, scl_sync, sta, sto, sda_chk,
                filtered_rise, filtered_fall, filter_tick,
                self.cnt <= 0, self.state != 'IDLE',
                self.state.startswith('START'), self.state.startswith('STOP'),
                self.state.startswith('READ'), self.state.startswith('WRITE'), False)

        scl_oen, sda_oen = self._outputs()
        o['cmd_ack'] = self.cmd_ack_r & 1
        o['busy'] = self.busy_r & 1
        o['al'] = self.al_r & 1
        o['dout'] = self.dout_r & 1
        o['scl_o'] = 0
        o['scl_oen'] = scl_oen & 1
        o['sda_o'] = 0
        o['sda_oen'] = sda_oen & 1
        return o
