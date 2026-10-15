"""Generated reference model. Do not edit.

Derived from the specification via specflow S1 + refmodel. Frozen once
gate G4 passes: after the RTL exists, a wrong-RTL hypothesis and a
wrong-model hypothesis compete for every failing check, and the model is
the cheaper one to 'fix' -- which is how a reference model gets
retrofitted to match broken RTL.
"""

from specflow.refmodel.base import RefModel


class Model(RefModel):
    OUTPUT_PORTS = ['r']
    LATENCY_CYCLES = 0

    def evaluate(self, i):
        o = {p: None for p in self.OUTPUT_PORTS}

        a = self.mask(i['a'], 16)
        b = self.mask(i['b'], 16)
        raw_cmd = i['cmd']

        # None represents the unspecified 3'bxxx ALU_NC command and result.
        if raw_cmd is None:
            o['r'] = None
            return o

        cmd = self.mask(raw_cmd, 3)

        if cmd == 0:       # ALU_ADD
            o['r'] = self.mask(a + b, 16)
        elif cmd == 1:     # ALU_SUB
            o['r'] = self.mask(a - b, 16)
        elif cmd == 2:     # ALU_AND
            o['r'] = self.mask(a & b, 16)
        elif cmd == 3:     # ALU_OR
            o['r'] = self.mask(a | b, 16)
        elif cmd == 4:     # ALU_XOR
            o['r'] = self.mask(a ^ b, 16)
        elif cmd == 5:     # ALU_SL
            o['r'] = self.mask(a << b, 16) if b < 16 else 0
        elif cmd == 6:     # ALU_SR
            sign_fill = 0xffff if (a & 0x8000) else 0
            wide = (sign_fill << 16) | a
            o['r'] = ((wide >> b) & 0xffff) if b < 32 else 0
        elif cmd == 7:     # ALU_SRU
            wide = a
            o['r'] = ((wide >> b) & 0xffff) if b < 32 else 0
        else:
            o['r'] = 0
            if not getattr(self, 'CODE_FOR_SYNTHESIS', False):
                print('ALU: unknown command {}'.format(raw_cmd))

        return o
