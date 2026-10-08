from specflow.refmodel.base import RefModel


class Model(RefModel):
    OUTPUT_PORTS = ["q"]
    LATENCY_CYCLES = 3

    def reset(self):
        self.s = [0, 0, 0]

    def step(self, i):
        if not hasattr(self, "s"):
            self.reset()
        if not i.get("rst_n", 1):
            self.s = [0, 0, 0]
        else:
            self.s = [self.mask(i["d"] + 1, 8), self.s[0], self.s[1]]
        return {"q": self.s[2]}
