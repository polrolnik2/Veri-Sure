from specflow.refmodel.base import RefModel


class Model(RefModel):
    """reg1, written in the sampled-edge form: the register as it stands at
    the edge, and the edge's load in the next row."""
    OUTPUT_PORTS = ["q"]
    LATENCY_CYCLES = 1

    def reset(self):
        self.q = 0

    def outputs(self, i):
        if not hasattr(self, "q"):
            self.reset()
        return {"q": self.q}

    def advance(self, i):
        self.q = 0 if not i.get("rst_n", 1) else self.mask(i["d"], 4)
