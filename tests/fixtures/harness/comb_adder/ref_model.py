from specflow.refmodel.base import RefModel


class Model(RefModel):
    OUTPUT_PORTS = ["sum", "cout"]
    LATENCY_CYCLES = 0

    def evaluate(self, i):
        return {"sum": (i["a"] ^ i["b"]) & 1, "cout": (i["a"] & i["b"]) & 1}
