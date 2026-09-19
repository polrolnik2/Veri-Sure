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
        self.state = 'IDLE'
        self.phase = 0
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
        self.filter_counter = 0
        self.cnt = 0
        self.cmd_ack_r = 0
        self.busy_r = 0
        self.al_r = 0
        self.dout_r = 0
        self.scl_oen_r = 1
        self.sda_oen_r = 1
        self._set_probes(False, False, False, False)


    def _reset_state(self, clk_cnt):
        self.state = 'IDLE'
        self.phase = 0
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
        self.filter_counter = 0
        self.cnt = self._width16(clk_cnt)
        self.cmd_ack_r = 0
        self.busy_r = 0
        self.al_r = 0
        self.dout_r = 0
        self.scl_oen_r = 1
        self.sda_oen_r = 1


    def _width16(self, value):
        return self.mask(value, 16)


    def _set_probes(self, clk_en, cnt_zero, filter_expired, scl_sync):
        self.cscl = int(bool(self.cSCL))
        self.csda = int(bool(self.cSDA))
        self.sscl = int(bool(self.sSCL))
        self.ssda = int(bool(self.sSDA))
        self.dscl = int(bool(self.dSCL))
        self.dsda = int(bool(self.dSDA))
        self.fscl = int(bool(self.fSCL[0]))
        self.fsda = int(bool(self.fSDA[0]))
        self.filter_cnt = int(bool(filter_expired))
        self.cnt_zero = int(bool(cnt_zero))
        self.clk_en = int(bool(clk_en))
        self.slave_wait = int(bool(self.scl_oen_r and not self.sSCL))
        self.scl_sync = int(bool(scl_sync))
        self.sta_condition = int(bool((not self.sSDA) and self.dSDA and self.sSCL))
        self.sto_condition = int(bool(self.sSDA and (not self.dSDA) and self.sSCL))
        self.sda_chk = int(bool(self.state == 'WRITE' and self.phase == 1 and self.sda_oen_r))
        self.idle = int(self.state == 'IDLE')
        self.fsm_active = int(self.state != 'IDLE')
        self.start_sequence = int(self.state == 'START')
        self.stop_sequence = int(self.state == 'STOP')
        self.read_sequence = int(self.state == 'READ')
        self.write_sequence = int(self.state == 'WRITE')
        self.filtered_scl_rising = int(bool(self.sSCL and not self.dSCL))
        self.filtered_scl_falling = int(bool((not self.sSCL) and self.dSCL))
        self.i2c_master_bit_ctrl = 1


    def _filter_inputs(self, i):
        old_scl = self.sSCL
        old_sda = self.sSDA
        self.cSCL1 = int(bool(i['scl_i']))
        self.cSCL = self.cSCL1
        self.cSDA1 = int(bool(i['sda_i']))
        self.cSDA = self.cSDA1
        interval = self._width16(i['clk_cnt']) >> 2
        if interval <= 0:
            interval = 1
        expired = False
        if not i['ena']:
            self.filter_counter = 0
        elif self.filter_counter <= 0:
            expired = True
            self.filter_counter = interval - 1
        else:
            self.filter_counter -= 1
        if expired:
            self.fSCL = [self.cSCL, self.fSCL[0], self.fSCL[1]]
            self.fSDA = [self.cSDA, self.fSDA[0], self.fSDA[1]]
            self.dSCL = self.sSCL
            self.dSDA = self.sSDA
            self.sSCL = int(sum(self.fSCL) >= 2)
            self.sSDA = int(sum(self.fSDA) >= 2)
        else:
            self.dSCL = old_scl
            self.dSDA = old_sda
        rising = int(self.sSCL and not self.dSCL)
        falling = int((not self.sSCL) and self.dSCL)
        return expired, rising, falling


    def _line_outputs_for_state(self):
        scl = 1
        sda = 1
        if self.state == 'START':
            if self.phase >= 1:
                sda = 0
            if self.phase >= 2:
                scl = 0
        elif self.state == 'STOP':
            if self.phase == 0:
                sda = 0
            elif self.phase == 1:
                sda = 0
            else:
                sda = 1
        elif self.state == 'READ':
            scl = 0 if self.phase != 1 else 1
            sda = 1
        elif self.state == 'WRITE':
            scl = 0 if self.phase != 1 else 1
            sda = 1 if self.din_latched else 0
        return scl, sda


    def _advance_fsm(self, i, clk_en, sto_condition):
        if self.al_r:
            self.state = 'IDLE'
            self.phase = 0
            self.scl_oen_r = 1
            self.sda_oen_r = 1
            return
        if not i['ena']:
            if self.state == 'IDLE':
                self.scl_oen_r = 1
                self.sda_oen_r = 1
            return
        if self.state == 'IDLE':
            if not clk_en:
                return
            cmd = self.mask(i['cmd'], 4)
            if cmd in (1, 2, 4, 8):
                self.cmd_latched = cmd
                self.din_latched = int(bool(i['din']))
                self.phase = 0
                if cmd == 1:
                    self.state = 'START'
                elif cmd == 2:
                    self.state = 'STOP'
                elif cmd == 4:
                    self.state = 'WRITE'
                else:
                    self.state = 'READ'
            return
        if sto_condition and self.state != 'STOP':
            self.al_r = 1
            self.state = 'IDLE'
            self.phase = 0
            self.scl_oen_r = 1
            self.sda_oen_r = 1
            return
        scl_release = self.state in ('START', 'STOP', 'READ', 'WRITE') and self.phase in (0, 1)
        if scl_release and not self.sSCL:
            return
        if not clk_en:
            return
        if self.state == 'WRITE' and self.phase == 1 and self.din_latched and not self.sSDA:
            self.al_r = 1
            self.state = 'IDLE'
            self.phase = 0
            self.scl_oen_r = 1
            self.sda_oen_r = 1
            return
        if self.phase < 2:
            self.phase += 1
        else:
            self.state = 'IDLE'
            self.phase = 0
            self.cmd_ack_r = 1


    def step(self, i):
        o = {p: None for p in self.OUTPUT_PORTS}
        if not i['nReset']:
            self._reset_state(i['clk_cnt'])
            self._set_probes(False, False, False, False)
        elif i['rst']:
            self._reset_state(i['clk_cnt'])
            self._set_probes(False, False, False, False)
        else:
            self.cmd_ack_r = 0
            expired, rising, falling = self._filter_inputs(i)
            released_scl = bool(self.scl_oen_r)
            slave_wait = bool(released_scl and not self.sSCL)
            scl_sync = bool(released_scl and falling)
            cnt_zero = self.cnt <= 0
            clk_en = False
            if not i['ena']:
                self.cnt = self._width16(i['clk_cnt'])
            elif slave_wait:
                clk_en = False
            elif scl_sync or cnt_zero:
                self.cnt = self._width16(i['clk_cnt'])
                clk_en = True
            else:
                self.cnt = self._width16(self.cnt - 1)
            if self.sSDA and not self.dSDA and self.sSCL:
                self.busy_r = 0
            if not self.sSDA and self.dSDA and self.sSCL:
                self.busy_r = 1
            if rising:
                self.dout_r = int(bool(self.sSDA))
            self._advance_fsm(i, clk_en, bool(self.sSDA and not self.dSDA and self.sSCL))
            scl_release, sda_release = self._line_outputs_for_state()
            self.scl_oen_r = int(bool(scl_release))
            self.sda_oen_r = int(bool(sda_release))
            self._set_probes(clk_en, self.cnt <= 0, expired, scl_sync)
        o['cmd_ack'] = int(bool(self.cmd_ack_r))
        o['busy'] = int(bool(self.busy_r))
        o['al'] = int(bool(self.al_r))
        o['dout'] = int(bool(self.dout_r))
        o['scl_o'] = 0
        o['scl_oen'] = int(bool(self.scl_oen_r))
        o['sda_o'] = 0
        o['sda_oen'] = int(bool(self.sda_oen_r))
        return o
