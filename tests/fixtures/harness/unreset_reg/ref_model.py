from specflow.refmodel.base import RefModel


class Model(RefModel):
    """Mirrors the DUT, including that `latched` has no reset.

    A fresh `Model()` per testpoint starts it at 0, exactly as a freshly
    elaborated DUT does. The two only disagree if the DUT was NOT freshly
    elaborated -- which is the whole point of the fixture.
    """

    OUTPUT_PORTS = ["q", "latched"]
    LATENCY_CYCLES = 1

    def reset(self):
        self.q = 0
        self.latched = 0

    def step(self, i):
        if not hasattr(self, "q"):
            self.reset()
        if not i.get("rst_n", 1):
            self.q = 0
        else:
            self.q = i["d"] & 1
            if i.get("load"):
                self.latched = i["d"] & 1
        return {"q": self.q, "latched": self.latched}
