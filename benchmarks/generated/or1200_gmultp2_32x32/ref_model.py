"""Generated reference model. Do not edit.

Derived from the specification via specflow S1 + refmodel. Frozen once
gate G4 passes: after the RTL exists, a wrong-RTL hypothesis and a
wrong-model hypothesis compete for every failing check, and the model is
the cheaper one to 'fix' -- which is how a reference model gets
retrofitted to match broken RTL.
"""

from specflow.refmodel.base import RefModel


class Model(RefModel):
    OUTPUT_PORTS = ['P']
    LATENCY_CYCLES = 2

    def __init__(self):
        self.p0 = 0
        self.p1 = 0


    def _signed32(self, value):
        value = self.mask(value, 32)
        if value & (1 << 31):
            value -= 1 << 32
        return value


    def _product64(self, x, y):
        product = self._signed32(x) * self._signed32(y)
        return self.mask(product, 64)


    def _reset_p1(self):
        self.p1 = 0


    def _advance_pipeline(self, product, reset_active):
        previous_p0 = self.p0
        self.p0 = self.mask(product, 64)
        if not reset_active:
            self.p1 = self.mask(previous_p0, 64)


    def step(self, i):
        o = {p: None for p in self.OUTPUT_PORTS}

        reset_active = self.mask(i['RST'], 1) != 0
        if reset_active:
            self._reset_p1()

        product = self._product64(i['X'], i['Y'])
        self._advance_pipeline(product, reset_active)

        o['P'] = self.mask(self.p1, 64)
        return o
