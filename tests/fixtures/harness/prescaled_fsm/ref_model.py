"""One `step` is one clock edge; the FSM advances one phase per clk_en tick."""

from specflow.refmodel.base import RefModel


class Model(RefModel):
    OUTPUT_PORTS = ["busy", "done"]
    LATENCY_CYCLES = 5

    def reset(self):
        self.cnt = 0
        self.clk_en = 1
        self.state = 0
        self.busy = 0
        self.done = 0

    def step(self, i):
        if not hasattr(self, "state"):
            self.reset()
        if not i.get("rst_n", 1):
            self.reset()
            return {"busy": self.busy, "done": self.done}

        ena = i.get("ena", 0)
        # read pre-edge state, as a non-blocking assignment would
        o_cnt, o_clk_en, o_state = self.cnt, self.clk_en, self.state

        if o_cnt == 0 or not ena:
            self.cnt, self.clk_en = self.mask(i.get("prescale", 0), 4), 1
        else:
            self.cnt, self.clk_en = o_cnt - 1, 0

        self.done = 0
        if o_clk_en and ena:
            if o_state == 0:
                if i.get("go", 0):
                    self.state, self.busy = 1, 1
            elif o_state in (1, 2, 3):
                self.state = o_state + 1
            elif o_state == 4:
                self.state, self.busy, self.done = 0, 0, 1
        return {"busy": self.busy, "done": self.done}
