"""Generated reference model. Do not edit.

Derived from the specification via specflow S1 + refmodel. Frozen once
gate G4 passes: after the RTL exists, a wrong-RTL hypothesis and a
wrong-model hypothesis compete for every failing check, and the model is
the cheaper one to 'fix' -- which is how a reference model gets
retrofitted to match broken RTL.
"""

from specflow.refmodel.base import RefModel


class Model(RefModel):
    OUTPUT_PORTS = ['cmd_ack', 'busy', 'al', 'dout', 'scl_o', 'scl_oen', 'sda_o', 'sda_oen']
    PROBE_PORTS = []
    LATENCY_CYCLES = 0

    def _bit(self, value):
        return 1 if value else 0

    def _reset_outputs(self, o):
        o['cmd_ack'] = 0
        o['busy'] = 0
        o['al'] = 0
        o['dout'] = 1
        o['scl_o'] = 0
        o['scl_oen'] = 1
        o['sda_o'] = 0
        o['sda_oen'] = 1
        return o

    def _open_drain_outputs(self, o, scl_release, sda_release):
        o['scl_o'] = 0
        o['sda_o'] = 0
        o['scl_oen'] = 1 if scl_release else 0
        o['sda_oen'] = 1 if sda_release else 0
        return o

    def _filtered_inputs(self, i):
        # With no persistent state available to evaluate(), the best stateless
        # approximation to the filtered bus values is the current synchronized
        # input sample.
        return self._bit(i['scl_i']), self._bit(i['sda_i'])

    def _decode_command(self, i, o):
        # OpenCores command encodings: START=1, STOP=2, WRITE=4, READ=8.
        cmd = self.mask(i['cmd'], 4)
        din = self._bit(i['din'])
        if cmd == 1:                 # START: first establish released bus,
            self._open_drain_outputs(o, 1, 0)  # then pull SDA low.
        elif cmd == 2:               # STOP: SDA low, SCL released high.
            self._open_drain_outputs(o, 1, 0)
        elif cmd == 4:               # WRITE: transmit din, SCL released.
            self._open_drain_outputs(o, 1, din)
        elif cmd == 8:               # READ: release SDA and raise SCL.
            self._open_drain_outputs(o, 1, 1)
        else:
            self._open_drain_outputs(o, 1, 1)
        return o

    def evaluate(self, i):
        o = {p: None for p in self.OUTPUT_PORTS}
        self._reset_outputs(o)
        if not self._bit(i['nReset']) or self._bit(i['rst']):
            return o

        scl, sda = self._filtered_inputs(i)
        # In a stateless combinational evaluation, expose the current sampled SDA.
        o['dout'] = sda
        self._decode_command(i, o)
        # Acknowledge, busy, and arbitration status require sequential event
        # history and consequently remain at their reset/default values here.
        o['cmd_ack'] = 0
        o['busy'] = 0
        o['al'] = 0
        # These are fixed open-drain low-drive values regardless of enable state.
        o['scl_o'] = 0
        o['sda_o'] = 0
        return o
