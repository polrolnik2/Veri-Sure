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


def test_a_net_declared_WITH_an_initialiser_drives_that_net() -> None:
    """`wire x = expr;` drives `x` exactly as `assign x = expr;` does, and
    neither parser looked for it: the tree-sitter node is `net_declaration`
    holding a `net_decl_assignment`, never `continuous_assign`, and its target
    is a bare `simple_identifier` rather than a `net_lvalue`.

    **THE RTL EDITOR ACTED ON THE GAP.** `find_signal` reports drivers straight
    out of `RtlBlock.writes`, so it answered `driver_count: 0` for a net its own
    declaration drove, with the note "it is a module input, or its driver was
    removed". Measured on one repair turn against a real candidate: the editor
    believed it and added `assign filt_reload = clk_cnt[15:2];` beside the
    declaration already driving `filt_reload`, putting the net in contention --
    and two checks that had been deciding stopped firing.
    """
    from eda_agent.trace_slicer import parse_rtl_blocks

    rtl = """module TopModule(input clk, input [15:0] n, output q);
  wire [13:0] reload = (n[15:2] == 14'd0) ? 14'd0 : (n[15:2] - 14'd1);
  assign q = clk;
endmodule
"""
    blocks = parse_rtl_blocks(rtl)
    drivers = [b for b in blocks if "reload" in set(b.writes)]
    assert drivers, "the declaration that drives `reload` is not a driver"
    assert drivers[0].kind == "assign"
    #: The ordinary continuous assignment still works.
    assert any("q" in set(b.writes) for b in blocks)


def test_a_REG_with_an_initial_value_is_NOT_a_driver() -> None:
    """`reg x = 0;` is an initial value, not a continuous assignment. Counting
    it would invent a second driver for every initialised register -- and a
    spurious second driver is precisely the failure this fix exists to stop,
    so the fix must not create one at the other end."""
    from eda_agent.trace_slicer import parse_rtl_blocks

    rtl = """module TopModule(input clk, output reg q);
  reg [3:0] count = 4'd0;
  always @(posedge clk) count <= count + 1'b1;
  assign q = count[0];
endmodule
"""
    blocks = parse_rtl_blocks(rtl)
    drivers = [b for b in blocks if "count" in set(b.writes)]
    assert len(drivers) == 1, [(b.id, b.kind) for b in drivers]
    assert drivers[0].kind == "always"


def test_a_BARE_net_declaration_declares_without_driving() -> None:
    """`wire w;` parses as a `net_decl_assignment` as well -- one bare
    `simple_identifier` child and no `=` -- and it declares without driving.

    Counting it gave every such net ONE MORE driver than it has, which is the
    same miscount as the bug this file's sibling test covers, pointed the other
    way: it broke the editor's duplicate-driver guard, which refuses a commit
    that would add a second driver, by making the declaration itself look like
    the first one.
    """
    from eda_agent.trace_slicer import parse_rtl_blocks

    rtl = """module TopModule(input a, output b);
  wire w;
  wire v = a;
  assign w = a;
  assign b = w;
endmodule
"""
    blocks = parse_rtl_blocks(rtl)
    #: `w` is declared bare and driven once, by the `assign`.
    assert [b.kind for b in blocks if "w" in set(b.writes)] == ["assign"]
    assert len([b for b in blocks if "w" in set(b.writes)]) == 1
    #: `v` is driven by its own declaration.
    assert len([b for b in blocks if "v" in set(b.writes)]) == 1
