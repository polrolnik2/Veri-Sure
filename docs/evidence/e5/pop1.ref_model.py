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
        return int(value) & 1


    def _cmd(self, value):
        return int(value) & 0xf


    def _majority(self, a, b, c):
        return (self._bit(a) + self._bit(b) + self._bit(c)) >= 2


    def _reset_outputs(self):
        return {
            'cmd_ack': 0,
            'busy': 0,
            'al': 0,
            'dout': 1,
            'scl_o': 0,
            'scl_oen': 1,
            'sda_o': 0,
            'sda_oen': 1,
        }


    def _open_drain_outputs(self, scl_oen, sda_oen):
        return {
            'scl_o': 0,
            'scl_oen': self._bit(scl_oen),
            'sda_o': 0,
            'sda_oen': self._bit(sda_oen),
        }


    def _start_phase(self):
        return self._open_drain_outputs(1, 1)


    def _stop_phase(self):
        return self._open_drain_outputs(0, 0)


    def _read_phase(self):
        return self._open_drain_outputs(1, 1)


    def _write_phase(self, din):
        return self._open_drain_outputs(0, 1 if self._bit(din) else 0)


    def _command_phase(self, cmd, din):
        command = self._cmd(cmd)
        if command == 1:
            return self._start_phase()
        if command == 2:
            return self._stop_phase()
        if command == 4:
            return self._read_phase()
        if command == 8:
            return self._write_phase(din)
        return self._open_drain_outputs(1, 1)


    def evaluate(self, i):
        o = {p: 0 for p in self.OUTPUT_PORTS}
        if self._bit(i.get('nReset', 1)) == 0 or self._bit(i.get('rst', 0)):
            o.update(self._reset_outputs())
            return o

        phase = self._command_phase(i.get('cmd', 0), i.get('din', 0))
        o.update(phase)
        o['cmd_ack'] = 0
        o['busy'] = 0
        o['al'] = 0
        o['dout'] = self._bit(i.get('sda_i', 1))
        o['scl_o'] = 0
        o['sda_o'] = 0
        return o
