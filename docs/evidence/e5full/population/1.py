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
        self.filter_counter = 0
        self.cnt = 0
        self.cmd_ack_reg = 0
        self.busy_reg = 0
        self.al_reg = 0
        self.dout_reg = 0
        self.scl_oen_reg = 1
        self.sda_oen_reg = 1
        self.prev_sSCL = 1
        self.prev_sSDA = 1
        self.clk_en_reg = 0
        self.cnt_zero_reg = 1
        self.slave_wait_reg = 0
        self.scl_sync_reg = 0
        self.sta_condition_reg = 0
        self.sto_condition_reg = 0
        self.sda_chk_reg = 0
        self._update_probes()


    def _majority(self, values):
        return 1 if sum(values) >= 2 else 0


    def _synchronize_and_filter(self, i):
        old_scl = self.sSCL
        old_sda = self.sSDA
        self.cSCL1 = int(i['scl_i']) & 1
        self.cSCL = self.cSCL1
        self.cSDA1 = int(i['sda_i']) & 1
        self.cSDA = self.cSDA1

        interval = ((int(i['clk_cnt']) & 0xffff) >> 2)
        sample = False
        if int(i['ena']) & 1:
            if self.filter_counter == 0:
                sample = True
                self.filter_counter = interval
            else:
                self.filter_counter -= 1
        else:
            self.filter_counter = 0

        if sample:
            self.fSCL = [self.fSCL[1], self.fSCL[2], self.cSCL]
            self.fSDA = [self.fSDA[1], self.fSDA[2], self.cSDA]
            self.sSCL = self._majority(self.fSCL)
            self.sSDA = self._majority(self.fSDA)

        self.dSCL = old_scl
        self.dSDA = old_sda
        self.prev_sSCL = old_scl
        self.prev_sSDA = old_sda
        self.sta_condition_reg = int((not self.sSDA) and self.dSDA and self.sSCL)
        self.sto_condition_reg = int(self.sSDA and (not self.dSDA) and self.sSCL)
        self.scl_sync_reg = int(self.scl_oen_reg and old_scl and not self.sSCL)
        self.slave_wait_reg = int(self.scl_oen_reg and not self.sSCL)

        if self.sta_condition_reg:
            self.busy_reg = 1
        if self.sto_condition_reg:
            self.busy_reg = 0
        if self.sSCL and not old_scl:
            self.dout_reg = self.sSDA


    def _timing(self, i):
        self.clk_en_reg = 0
        self.cnt_zero_reg = int(self.cnt == 0)
        if not (int(i['ena']) & 1):
            self.cnt = int(i['clk_cnt']) & 0xffff
            return
        if self.slave_wait_reg:
            return
        if self.scl_sync_reg or self.cnt == 0:
            self.cnt = int(i['clk_cnt']) & 0xffff
            self.clk_en_reg = 1
        else:
            self.cnt = (self.cnt - 1) & 0xffff


    def _arbitration_lost(self):
        self.al_reg = 1
        self.state = 'IDLE'
        self.scl_oen_reg = 1
        self.sda_oen_reg = 1
        self.sda_chk_reg = 0


    def _command_fsm(self, i):
        if self.al_reg:
            self.state = 'IDLE'
            self.scl_oen_reg = 1
            self.sda_oen_reg = 1
            return
        if not (int(i['ena']) & 1) or not self.clk_en_reg:
            return

        if self.state == 'IDLE':
            cmd = int(i['cmd']) & 0xf
            if cmd in (1, 2, 4, 8):
                self.cmd_latched = cmd
                self.din_latched = int(i['din']) & 1
                if cmd == 1:
                    self.state = 'START_RELEASE'
                    self.scl_oen_reg = 1
                    self.sda_oen_reg = 1
                elif cmd == 2:
                    self.state = 'STOP_LOW'
                    self.scl_oen_reg = 0
                    self.sda_oen_reg = 0
                elif cmd == 8:
                    self.state = 'READ_HIGH'
                    self.scl_oen_reg = 1
                    self.sda_oen_reg = 1
                else:
                    self.state = 'WRITE_HIGH'
                    self.scl_oen_reg = 1
                    self.sda_oen_reg = 0 if self.din_latched == 0 else 1
            return

        if self.sto_condition_reg and self.state != 'STOP_LOW':
            self._arbitration_lost()
            return

        if self.state == 'START_RELEASE':
            self.state = 'START_LOW_SDA'
            self.scl_oen_reg = 1
            self.sda_oen_reg = 0
        elif self.state == 'START_LOW_SDA':
            self.state = 'IDLE'
            self.scl_oen_reg = 0
            self.sda_oen_reg = 0
            self.cmd_ack_reg = 1
        elif self.state == 'STOP_LOW':
            self.state = 'STOP_RELEASE_SCL'
            self.scl_oen_reg = 1
            self.sda_oen_reg = 0
        elif self.state == 'STOP_RELEASE_SCL':
            if self.sSCL:
                self.state = 'STOP_RELEASE_SDA'
                self.scl_oen_reg = 1
                self.sda_oen_reg = 1
        elif self.state == 'STOP_RELEASE_SDA':
            self.state = 'IDLE'
            self.scl_oen_reg = 1
            self.sda_oen_reg = 1
            self.cmd_ack_reg = 1
        elif self.state == 'READ_HIGH':
            if self.sSCL:
                self.state = 'READ_LOW'
                self.scl_oen_reg = 0
                self.sda_oen_reg = 1
        elif self.state == 'READ_LOW':
            self.state = 'IDLE'
            self.scl_oen_reg = 0
            self.sda_oen_reg = 1
            self.cmd_ack_reg = 1
        elif self.state == 'WRITE_HIGH':
            self.sda_chk_reg = int(self.din_latched == 1)
            if self.sda_chk_reg and not self.sSDA:
                self._arbitration_lost()
            else:
                self.state = 'WRITE_LOW'
                self.scl_oen_reg = 0
                self.sda_oen_reg = 0 if self.din_latched == 0 else 1
                self.sda_chk_reg = 0
        elif self.state == 'WRITE_LOW':
            self.state = 'IDLE'
            self.scl_oen_reg = 0
            self.sda_oen_reg = 0 if self.din_latched == 0 else 1
            self.cmd_ack_reg = 1


    def _update_probes(self):
        self.cscl = bool(self.cSCL)
        self.csda = bool(self.cSDA)
        self.sscl = bool(self.sSCL)
        self.ssda = bool(self.sSDA)
        self.dscl = bool(self.dSCL)
        self.dsda = bool(self.dSDA)
        self.fscl = bool(self.fSCL[-1])
        self.fsda = bool(self.fSDA[-1])
        self.filter_cnt = bool(self.filter_counter == 0)
        self.cnt_zero = bool(self.cnt_zero_reg)
        self.clk_en = bool(self.clk_en_reg)
        self.slave_wait = bool(self.slave_wait_reg)
        self.scl_sync = bool(self.scl_sync_reg)
        self.sta_condition = bool(self.sta_condition_reg)
        self.sto_condition = bool(self.sto_condition_reg)
        self.sda_chk = bool(self.sda_chk_reg)
        self.idle = self.state == 'IDLE'
        self.fsm_active = not self.idle
        self.start_sequence = self.state.startswith('START_')
        self.stop_sequence = self.state.startswith('STOP_')
        self.read_sequence = self.state.startswith('READ_')
        self.write_sequence = self.state.startswith('WRITE_')
        self.filtered_scl_rising = bool(self.sSCL and not self.prev_sSCL)
        self.filtered_scl_falling = bool(self.prev_sSCL and not self.sSCL)
        self.i2c_master_bit_ctrl = True


    def step(self, i):
        o = {p: None for p in self.OUTPUT_PORTS}
        if not (int(i['nReset']) & 1):
            self.reset()
        elif int(i['rst']) & 1:
            self.reset()
        else:
            self.cmd_ack_reg = 0
            self._synchronize_and_filter(i)
            self._timing(i)
            self._command_fsm(i)
            self._update_probes()

        o['cmd_ack'] = int(self.cmd_ack_reg) & 1
        o['busy'] = int(self.busy_reg) & 1
        o['al'] = int(self.al_reg) & 1
        o['dout'] = int(self.dout_reg) & 1
        o['scl_o'] = 0
        o['scl_oen'] = int(self.scl_oen_reg) & 1
        o['sda_o'] = 0
        o['sda_oen'] = int(self.sda_oen_reg) & 1
        return o
