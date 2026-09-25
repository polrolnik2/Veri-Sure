from specflow.refmodel.base import RefModel


class Model(RefModel):
    OUTPUT_PORTS = ["oen", "seen"]
    LATENCY_CYCLES = 1

    def reset(self):
        self.oen = 1
        self.seen = 0

    def step(self, i):
        if not hasattr(self, "oen"):
            self.reset()
        if not i.get("rst_n", 1):
            self.reset()
            return {"oen": self.oen, "seen": self.seen}
        req_n = i.get("req_n", 1)
        self.oen = req_n & 1
        self.seen = (0 if req_n else 1) & i.get("bus_i", 1) & 1
        return {"oen": self.oen, "seen": self.seen}
