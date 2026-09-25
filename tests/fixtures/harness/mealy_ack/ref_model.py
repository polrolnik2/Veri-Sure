from specflow.refmodel.base import RefModel


class Model(RefModel):
    OUTPUT_PORTS = ["busy", "ack", "count"]
    PROBE_PORTS = ["in_busy", "done_count"]
    PROBE_WIDTHS = {"in_busy": 1, "done_count": 2}
    LATENCY_CYCLES = 0

    def reset(self):
        self.state = 0
        self.count = 0

    def outputs(self, i):
        if not hasattr(self, "state"):
            self.reset()
        self.in_busy = self.state
        self.done_count = self.count
        return {"busy": self.state,
                "ack": int(bool(self.state and i.get("done_i", 0))),
                "count": self.count}

    def advance(self, i):
        if not i.get("rst_n", 1):
            self.reset()
        elif not self.state:
            if i.get("go", 0):
                self.state = 1
        elif i.get("done_i", 0):
            self.state = 0
            self.count = self.mask(self.count + 1, 2)
