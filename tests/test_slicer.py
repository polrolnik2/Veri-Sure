"""The backward slice, and why it is computed rather than read off `covers`.

`eda_agent/trace_slicer.py` does this for Verilog and the RTL debugger's whole
readable surface is its output. These pin the Python counterpart.
"""

from __future__ import annotations

from specflow.refmodel.slicer import backward_slice, build_driver_map, parse_methods

PORTS = {"q", "ack"}

MODEL = '''
class Model:
    def reset(self):
        self.n = 0
        self.k = 0
        self.noise = 0

    def _tick_q(self, i):
        self.n = self.n + i["a"]

    def _tick_ack(self):
        self.k = self.k + 1

    def _unrelated(self):
        self.noise = self.noise + 1

    def step(self, i):
        self._tick_q(i)
        self._tick_ack()
        self._unrelated()
        return {"q": self.n, "ack": self.k}
'''

#: Ports written by subscript into an outputs mapping, one of them through a
#: LOCAL bound from a call -- the shape the generated i2c model actually uses,
#: and the one a returned-dict-only reader finds nothing in.
SUBSCRIPT = '''
class Model:
    def _oen(self):
        return self.gate

    def _tick(self):
        self.gate = 1
        self.other = 2

    def _write(self, o):
        oen = self._oen()
        o["q"] = self.n
        o["ack"] = oen

    def step(self, i):
        self.n = i["a"]
        o = {}
        self._write(o)
        return o
'''


def _names(source, fail, ports=PORTS):
    return [b.name for b in backward_slice(
        fail_ports=fail, blocks=parse_methods(source, ports))]


def test_the_slice_excludes_a_method_that_feeds_neither_port():
    """`_unrelated` writes only an attribute no port reads."""
    assert "_unrelated" not in _names(MODEL, {"q"})
    assert "_unrelated" not in _names(MODEL, {"ack"})


def test_the_slice_separates_two_ports():
    """The whole point: a failure on `q` must not hand back `ack`'s driver."""
    assert "_tick_q" in _names(MODEL, {"q"})
    assert "_tick_ack" not in _names(MODEL, {"q"})
    assert "_tick_ack" in _names(MODEL, {"ack"})
    assert "_tick_q" not in _names(MODEL, {"ack"})


def test_a_port_written_by_subscript_is_found():
    """`o["q"] = ...` is how the generated i2c model supplies every port.

    Reading only `return {...}` literals found zero supplies there, and the
    slice fell open to the whole model on every requirement.
    """
    assert "_write" in _names(SUBSCRIPT, {"q"})
    assert "step" in _names(SUBSCRIPT, {"q"})


def test_a_value_reaching_a_port_through_a_call_is_followed():
    """`o["ack"] = oen`, `oen = self._oen()`.

    Verilog blocks do not invoke one another so `trace_slicer` needs no call
    edge; Python methods do. Without it `_oen` -- and `_tick`, which sets what
    it returns -- are invisible, which under-approximates: the agent is denied
    the method that actually holds the bug.
    """
    reached = _names(SUBSCRIPT, {"ack"})
    assert "_oen" in reached and "_tick" in reached


def test_a_call_is_followed_only_along_the_failing_port_s_path():
    """`_write` supplies both ports and calls `_oen` for one of them.

    Following every callee of a method that supplies all the ports pulls in the
    whole model from any one of them -- measured on the generated i2c model,
    where it took `cmd_ack` from 6 methods to 11 of 11.
    """
    assert "_oen" not in _names(SUBSCRIPT, {"q"})


def test_ports_nothing_supplies_return_everything_rather_than_nothing():
    """A slice that could not be computed must not read as an empty one, or the
    agent is told there is nothing to read."""
    assert len(_names(MODEL, {"not_a_port"})) == len(parse_methods(MODEL, PORTS))
    assert len(_names(MODEL, set())) == len(parse_methods(MODEL, PORTS))


def test_an_unparseable_model_yields_no_blocks_rather_than_raising():
    """The editor's problem, not this module's -- and raising here would take
    out the tool that was about to report it."""
    assert parse_methods("class Model:\n    def step(self", PORTS) == []


def test_the_driver_map_inverts_writes():
    drivers = build_driver_map(parse_methods(MODEL, PORTS))
    assert {b.name for b in drivers["n"]} == {"reset", "_tick_q"}
