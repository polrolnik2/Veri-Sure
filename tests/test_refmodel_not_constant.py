"""A reference model whose outputs never move cannot discriminate anything.

Every other behavioural check in G4 is satisfied by a model that returns the
same constant forever: it imports, it instantiates, it is reproducible, and it
writes every declared port. It is also useless as an oracle -- it agrees with
whichever DUT is quietest.

Not hypothetical. The `i2c_master_bit_ctrl` reference model was regenerated five
times under per-requirement judging. Round 4 emitted ONE distinct output state
over 60 edges of varied stimulus where round 0 emitted five; scored against
golden RTL it fell 34/181 to 18/181, and its separation from a known-WRONG
design inverted to -9 -- the vacuous model matched the wrong design better than
the right one. No gate said anything.

This is the model-side counterpart of a rule already applied to the DUT side:
every harness conformance fixture must also REJECT a tied-off DUT.
"""

from __future__ import annotations

from specflow.refmodel.validate import _behavioural_checks

CONTRACT = {
    "io": [
        {"name": "clk", "dir": "input", "width": 1},
        {"name": "d", "dir": "input", "width": 8},
        {"name": "q", "dir": "output", "width": 8},
    ]
}

_CONSTANT = '''
class Model:
    OUTPUT_PORTS = ["q"]
    LATENCY_CYCLES = 0

    def step(self, i):
        return {"q": 0}
'''

_MOVES = '''
class Model:
    OUTPUT_PORTS = ["q"]
    LATENCY_CYCLES = 0

    def step(self, i):
        return {"q": i["d"]}
'''


def _warnings(source: str, tmp_path) -> list[str]:
    issues = _behavioural_checks(source, CONTRACT, "step", tmp_path)
    return [i.message for i in issues if i.severity == "warning"]


def _errors(source: str, tmp_path) -> list[str]:
    issues = _behavioural_checks(source, CONTRACT, "step", tmp_path)
    return [i.message for i in issues if i.severity == "error"]


def test_a_constant_model_is_reported(tmp_path):
    warned = _warnings(_CONSTANT, tmp_path)
    assert any("never move" in w for w in warned), warned


def test_a_constant_model_passes_every_other_check(tmp_path):
    """The point of the new check: nothing else objects to this model. If this
    ever starts failing for another reason, the new check is no longer the thing
    standing between a vacuous oracle and the rest of the pipeline."""
    assert _errors(_CONSTANT, tmp_path) == []


def test_a_model_whose_outputs_move_is_not_reported(tmp_path):
    assert _warnings(_MOVES, tmp_path) == []
    assert _errors(_MOVES, tmp_path) == []


def test_the_check_needs_a_corner_first_sweep_not_random_vectors(tmp_path):
    """The eight vectors G4 uses elsewhere randomise every functional input
    across its full width. For a prescaled design that makes `clk_cnt` a random
    16-bit number, the divider never ticks, and nothing moves in eight steps --
    so the check would fire on a good model.

    Measured on the real artifacts: the i2c round-0 model, which is wrong but
    active and discriminating (+23 separation against a known-wrong DUT), is
    constant across those eight random vectors and emits five distinct states
    under the corner-first sweep. Round 0 must not be flagged; rounds 1-4, which
    are genuinely inert, must be.
    """
    prescaled = {
        "io": [
            {"name": "clk", "dir": "input", "width": 1},
            {"name": "div", "dir": "input", "width": 16},
            {"name": "q", "dir": "output", "width": 8},
        ]
    }
    # Moves only for small `div` -- exactly the shape a full-width random draw
    # never reaches.
    source = """
class Model:
    OUTPUT_PORTS = ["q"]
    LATENCY_CYCLES = 0

    def __init__(self):
        self.n = 0

    def step(self, i):
        if i["div"] < 4:
            self.n = (self.n + 1) % 251
        return {"q": self.n}
"""
    issues = _behavioural_checks(source, prescaled, "step", tmp_path)
    assert not [i for i in issues if "never move" in i.message], [i.message for i in issues]


def test_it_is_a_warning_not_an_error(tmp_path):
    """A design can be legitimately quiet under this vector set -- the
    null-oracle sweep across all 64 ChipVerilog designs found exactly one,
    `instruction_mem`, whose outputs never move under the liveness probe either.
    One false positive in 64 is not worth blocking a correct generation."""
    issues = _behavioural_checks(_CONSTANT, CONTRACT, "step", tmp_path)
    moving = [i for i in issues if "never move" in i.message]
    assert moving and all(i.severity == "warning" for i in moving)
