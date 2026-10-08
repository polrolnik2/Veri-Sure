# ruff: noqa: E702
"""CONTROL ONLY -- a line-by-line transliteration of the golden i2c RTL.

Not part of the pipeline and never generated. Its single purpose is to answer a
question no other artifact can: if the reference model were PERFECT, what would
the generated suite score? If a faithful oracle does not score ~168/168, then
model quality is not the only variable and every comparison between models is
confounded by whatever else is wrong.

Each block below mirrors one `always` block of the golden source, updated in the
non-blocking style: read the OLD state everywhere, then commit. Order of
assignment inside `step` therefore does not matter, exactly as in RTL.

Written one Python line per Verilog statement group, semicolons and all, so it
can be read side by side against `i2c_master_bit_ctrl.v` and checked line for
line. That legibility is the whole value of a control -- reformatting it to
one-statement-per-line would make the correspondence harder to audit, which is
why E702 is silenced for this file only.
"""

from specflow.refmodel.base import RefModel

IDLE = 0
(START_A, START_B, START_C, START_D, START_E,
 STOP_A, STOP_B, STOP_C, STOP_D,
 RD_A, RD_B, RD_C, RD_D,
 WR_A, WR_B, WR_C, WR_D) = range(1, 18)

CMD_NOP, CMD_START, CMD_STOP, CMD_WRITE, CMD_READ = 0, 1, 2, 4, 8


class Model(RefModel):
    OUTPUT_PORTS = ['cmd_ack', 'busy', 'al', 'dout', 'scl_o', 'scl_oen', 'sda_o', 'sda_oen']
    LATENCY_CYCLES = 3

    def reset(self):
        self.cSCL = 0; self.cSDA = 0
        self.sta_condition = 0; self.sto_condition = 0
        self.fSCL = 7; self.fSDA = 7
        self.sSCL = 1; self.sSDA = 1
        self.dSCL = 1; self.dSDA = 1
        self.dscl_oen = 0
        self.sda_chk = 0
        self.clk_en = 1
        self.slave_wait = 0
        self.cnt = 0
        self.filter_cnt = 0
        self.c_state = IDLE
        self.cmd_ack = 0
        self.scl_oen = 1
        self.sda_oen = 1
        self.busy = 0
        self.al = 0
        self.cmd_stop = 0
        self.dout = 0

    def _outputs(self):
        return {'cmd_ack': self.cmd_ack, 'busy': self.busy, 'al': self.al,
                'dout': self.dout, 'scl_o': 0, 'scl_oen': self.scl_oen,
                'sda_o': 0, 'sda_oen': self.sda_oen}

    def step(self, i):
        if not hasattr(self, 'c_state'):
            self.reset()
        nreset = i.get('nReset', 1)
        rst = i.get('rst', 0)
        if not nreset:
            self.reset()
            return self._outputs()

        ena = i.get('ena', 0)
        clk_cnt = i.get('clk_cnt', 0)
        cmd = i.get('cmd', 0)
        din = i.get('din', 0)
        scl_i = i.get('scl_i', 1)
        sda_i = i.get('sda_i', 1)

        # every read below is of the PRE-edge state, as non-blocking assignment
        o_scl_oen, o_sda_oen = self.scl_oen, self.sda_oen
        o_sSCL, o_sSDA, o_dSCL, o_dSDA = self.sSCL, self.sSDA, self.dSCL, self.dSDA
        o_cnt, o_state, o_sda_chk = self.cnt, self.c_state, self.sda_chk
        o_busy, o_cmd_stop, o_al = self.busy, self.cmd_stop, self.al
        o_filter_cnt, o_fSCL, o_fSDA = self.filter_cnt, self.fSCL, self.fSDA
        o_cSCL, o_cSDA = self.cSCL, self.cSDA
        o_slave_wait, o_dscl_oen = self.slave_wait, self.dscl_oen
        # The FSM and cmd_stop gate on the REGISTERED clk_en -- golden's
        # `if (clk_en) case (c_state)` sits in an always @(posedge clk)
        # block, so it reads the value latched on the PREVIOUS edge. Reading
        # `self.clk_en` after the divider below has overwritten it advances
        # the machine one edge early, which is invisible while ena=0 (clk_en
        # is 1 every cycle then) and puts the model exactly one edge ahead
        # the moment the prescaler starts toggling.
        o_clk_en = self.clk_en

        scl_sync = o_dSCL and not o_sSCL and o_scl_oen

        self.dscl_oen = o_scl_oen
        self.slave_wait = ((o_scl_oen and not o_dscl_oen and not o_sSCL)
                           or (o_slave_wait and not o_sSCL))

        # clk_en / divider
        if rst or o_cnt == 0 or not ena or scl_sync:
            self.cnt = clk_cnt; self.clk_en = 1
        elif o_slave_wait:
            self.cnt = o_cnt; self.clk_en = 0
        else:
            self.cnt = o_cnt - 1; self.clk_en = 0

        # synchroniser
        self.cSCL = ((o_cSCL << 1) | (1 if scl_i else 0)) & 3 if not rst else 0
        self.cSDA = ((o_cSDA << 1) | (1 if sda_i else 0)) & 3 if not rst else 0

        # filter divider
        if rst or not ena:
            self.filter_cnt = 0
        elif o_filter_cnt == 0:
            self.filter_cnt = clk_cnt >> 2
        else:
            self.filter_cnt = o_filter_cnt - 1

        if rst:
            self.fSCL = 7; self.fSDA = 7
        elif o_filter_cnt == 0:
            self.fSCL = ((o_fSCL << 1) | ((o_cSCL >> 1) & 1)) & 7
            self.fSDA = ((o_fSDA << 1) | ((o_cSDA >> 1) & 1)) & 7

        def maj(f):
            b2, b1, b0 = (f >> 2) & 1, (f >> 1) & 1, f & 1
            return int((b2 and b1) or (b1 and b0) or (b2 and b0))

        if rst:
            self.sSCL = self.sSDA = self.dSCL = self.dSDA = 1
        else:
            self.sSCL = maj(o_fSCL); self.sSDA = maj(o_fSDA)
            self.dSCL = o_sSCL;      self.dSDA = o_sSDA

        # sta_condition/sto_condition are REGISTERS in golden (`sta_condition <=
        # #1 ~sSDA & dSDA & sSCL;`), and busy/al read the REGISTERED value. This
        # used to compute them combinationally in the same step, collapsing one
        # pipeline stage -- so `al` fired one edge early, aborted the command the
        # DUT was completing, and the model fell a whole command period behind.
        o_sta, o_sto = self.sta_condition, self.sto_condition
        self.sta_condition = 0 if rst else int(
            (not o_sSDA) and o_dSDA and o_sSCL)
        self.sto_condition = 0 if rst else int(
            o_sSDA and (not o_dSDA) and o_sSCL)
        self.busy = 0 if rst else int((o_sta or o_busy) and not o_sto)
        self.al = 0 if rst else int((o_sda_chk and (not o_sSDA) and o_sda_oen)
                                    or (o_state != IDLE and o_sto and not o_cmd_stop))
        if rst:
            self.cmd_stop = 0
        elif o_clk_en:
            self.cmd_stop = int(cmd == CMD_STOP)

        if o_sSCL and not o_dSCL:
            self.dout = o_sSDA

        # ---- the state machine: ONE phase per clk_en tick ----
        if rst or o_al:
            self.c_state = IDLE; self.cmd_ack = 0
            self.scl_oen = 1; self.sda_oen = 1; self.sda_chk = 0
            return self._outputs()

        self.cmd_ack = 0
        if not o_clk_en:
            return self._outputs()

        s = o_state
        if s == IDLE:
            self.c_state = {CMD_START: START_A, CMD_STOP: STOP_A,
                            CMD_WRITE: WR_A, CMD_READ: RD_A}.get(cmd, IDLE)
            self.sda_chk = 0
        elif s == START_A:
            self.c_state = START_B; self.sda_oen = 1; self.sda_chk = 0
        elif s == START_B:
            self.c_state = START_C; self.scl_oen = 1; self.sda_oen = 1; self.sda_chk = 0
        elif s == START_C:
            self.c_state = START_D; self.scl_oen = 1; self.sda_oen = 0; self.sda_chk = 0
        elif s == START_D:
            self.c_state = START_E; self.scl_oen = 1; self.sda_oen = 0; self.sda_chk = 0
        elif s == START_E:
            self.c_state = IDLE; self.cmd_ack = 1
            self.scl_oen = 0; self.sda_oen = 0; self.sda_chk = 0
        elif s == STOP_A:
            self.c_state = STOP_B; self.scl_oen = 0; self.sda_oen = 0; self.sda_chk = 0
        elif s == STOP_B:
            self.c_state = STOP_C; self.scl_oen = 1; self.sda_oen = 0; self.sda_chk = 0
        elif s == STOP_C:
            self.c_state = STOP_D; self.scl_oen = 1; self.sda_oen = 0; self.sda_chk = 0
        elif s == STOP_D:
            self.c_state = IDLE; self.cmd_ack = 1
            self.scl_oen = 1; self.sda_oen = 1; self.sda_chk = 0
        elif s == RD_A:
            self.c_state = RD_B; self.scl_oen = 0; self.sda_oen = 1; self.sda_chk = 0
        elif s == RD_B:
            self.c_state = RD_C; self.scl_oen = 1; self.sda_oen = 1; self.sda_chk = 0
        elif s == RD_C:
            self.c_state = RD_D; self.scl_oen = 1; self.sda_oen = 1; self.sda_chk = 0
        elif s == RD_D:
            self.c_state = IDLE; self.cmd_ack = 1
            self.scl_oen = 0; self.sda_oen = 1; self.sda_chk = 0
        elif s == WR_A:
            self.c_state = WR_B; self.scl_oen = 0; self.sda_oen = din; self.sda_chk = 0
        elif s == WR_B:
            self.c_state = WR_C; self.scl_oen = 1; self.sda_oen = din; self.sda_chk = 0
        elif s == WR_C:
            self.c_state = WR_D; self.scl_oen = 1; self.sda_oen = din; self.sda_chk = 1
        elif s == WR_D:
            self.c_state = IDLE; self.cmd_ack = 1
            self.scl_oen = 0; self.sda_oen = din; self.sda_chk = 0
        return self._outputs()
