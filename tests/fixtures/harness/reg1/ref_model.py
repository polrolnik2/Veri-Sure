from specflow.refmodel.base import RefModel


class Model(RefModel):
    OUTPUT_PORTS = ["q"]
    LATENCY_CYCLES = 1

    def reset(self):
        self.q = 0

    def step(self, i):
        if not hasattr(self, "q"):
            self.reset()
        self.q = 0 if not i.get("rst_n", 1) else self.mask(i["d"], 4)
        return {"q": self.q}
