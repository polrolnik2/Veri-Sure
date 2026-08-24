"""An instrument that reads the same for every input is not an instrument.

`test_adequacy.py` asks whether an oracle would notice a different MODEL, and
needs the mutation operator to produce one it can see -- on `n-i2c` 44 of 70
oracles never got three. These pins are for the question asked directly on the
trace, where the difference is constructed rather than hoped for.
"""

from __future__ import annotations

from specflow.refmodel import liveness
from specflow.refmodel.oracles import RequirementOracle

CONTRACT = {"io": [
    {"name": "clk", "dir": "input", "width": 1},
    {"name": "a", "dir": "input", "width": 4},
    {"name": "y", "dir": "output", "width": 8},
    {"name": "hit", "dir": "output", "width": 1},
    {"name": "pin", "dir": "output", "width": 1},
]}

#: `y` accumulates, `hit` pulses, `pin` never moves -- the three cases the
#: verdict has to tell apart.
MODEL = """\
from specflow.refmodel.base import RefModel


class Model(RefModel):
    OUTPUT_PORTS = ['y', 'hit', 'pin']
    LATENCY_CYCLES = 0

    def reset(self):
        self.n = 0
        self.k = 0

    def step(self, i):
        if not hasattr(self, 'n'):
            self.reset()
        self.k = self.k + 1
        self.n = self.mask(self.n + i['a'], 8)
        return {'y': self.n, 'hit': 1 if self.k == 3 else 0, 'pin': 0}
"""

STIM = {"TP-0000": [{"a": 3}, {"a": 5}, {"a": 7}, {"a": 1}, {"a": 2}, {"a": 6}]}

#: Reproduces the design's rule, so any change to `y` fails it. Live NEAR.
SHARP = """\
def decide(trace):
    total = 0
    for row in trace:
        total = (total + row['inputs']['a']) % 256
        if row['outputs']['y'] != total:
            return False, row['edge'], 'y does not follow the rule'
    return True, 0, 'y followed the rule'
"""

#: Can fail -- but only above 200, and `y` never exceeds 24 here. The check is
#: sound and this stimulus cannot decide it: a testplan finding, not the
#: author's, and the distinction only exists because FAR is tried separately.
FAR_THRESHOLD = """\
def decide(trace):
    for row in trace:
        if row['outputs']['y'] > 200:
            return False, row['edge'], 'y too large'
    return True, 0, 'y stayed small'
"""

#: Reads `y`, decides on nothing. The shape 11 CONFORMS verdicts had.
VACUOUS = """\
def decide(trace):
    for row in trace:
        _ = row['outputs']['y']
    return True, 0, 'looked at y and concluded nothing'
"""

#: Asserts only on a port the design holds constant. Route: the stimulus.
ON_A_CONSTANT = """\
def decide(trace):
    for row in trace:
        if row['outputs']['pin'] != 0:
            return False, row['edge'], 'pin moved'
    return True, 0, 'pin held'
"""

#: TRIGGERS on `hit`, ASSERTS on `y`. `ports_read` cannot tell these apart and
#: reports both; this must report only `y`.
TRIGGER_AND_ASSERT = """\
def decide(trace):
    total = 0
    for row in trace:
        total = (total + row['inputs']['a']) % 256
        if row['outputs']['hit'] == 1 and row['outputs']['y'] != total:
            return False, row['edge'], 'y wrong when hit'
    return True, 0, 'ok'
"""


def _oracle(source: str, uid: str = "REQ-0001", tps=("TP-0000",)):
    return RequirementOracle(req_uid=uid, tp_uids=list(tps),
                             clause="y accumulates a", source=source)


def _assess(source: str, uid: str = "REQ-0001", tps=("TP-0000",)) -> dict:
    report = liveness.assess([_oracle(source, uid, tps)], MODEL, CONTRACT,
                             STIM, base="step")
    return report[uid]


def test_an_oracle_that_can_fail_is_live():
    record = _assess(SHARP)
    assert record["verdict"] == liveness.LIVE, record["detail"]
    assert "y" in record["asserts_on"]


def test_an_oracle_that_decides_nothing_is_dead():
    """The measured shape: reads a port, returns True whatever it holds."""
    record = _assess(VACUOUS)
    assert record["verdict"] == liveness.DEAD_ORACLE, record["detail"]


def test_a_check_the_stimulus_never_approaches_accuses_the_testplan():
    """Two causes, two owners, and the split is measured rather than guessed.

    This oracle CAN fail -- driving `y` to the top of its range does it -- and
    the stimulus never takes `y` above 24. Telling the author to strengthen a
    sound check is the misrouting `verdict.ROUTE` exists to stop, one level
    down, and only trying FAR separately can tell this from a check that
    cannot fail at all.
    """
    record = _assess(FAR_THRESHOLD)
    assert record["verdict"] == liveness.DEAD_STIMULUS, record["detail"]
    assert record["asserts_on"] == [] and record["asserts_on_far"] == ["y"]


def test_near_and_far_differ_on_a_one_bit_port_that_moves():
    """The split survives a design whose observable ports are all one bit.

    Worth pinning because the obvious reading is wrong. A one-bit port has only
    one other value, so on a SINGLE row near and far are the same edit -- but
    near flips each row against whatever it holds, preserving the pattern
    inverted, while a far target flattens every row to one value. On a port
    that moves those are different traces, and i2c, whose every observable is
    one bit, still produced three `DEAD_STIMULUS` verdicts.
    """
    assert liveness._targets(1) == [0, 1]
    flat = [{"edge": 0, "inputs": {}, "outputs": {"pin": 0}}]
    assert (liveness._perturb(flat, "pin", 1, None, liveness.NEAR)[0]["outputs"]
            == liveness._perturb(flat, "pin", 1, None, 1)[0]["outputs"])

    moving = [{"edge": i, "inputs": {}, "outputs": {"pin": i % 2}}
              for i in range(4)]
    near = liveness._perturb(moving, "pin", 1, None, liveness.NEAR)
    far = liveness._perturb(moving, "pin", 1, None, 1)
    assert [r["outputs"]["pin"] for r in near] == [1, 0, 1, 0]
    assert [r["outputs"]["pin"] for r in far] == [1, 1, 1, 1]


def test_only_the_authors_dead_oracles_are_handed_back():
    report = liveness.assess(
        [_oracle(VACUOUS, "REQ-0001"), _oracle(FAR_THRESHOLD, "REQ-0002"),
         _oracle(SHARP, "REQ-0003")],
        MODEL, CONTRACT, STIM, base="step")
    assert set(liveness.dead(report)) == {"REQ-0001"}


def test_a_trigger_port_is_not_reported_as_an_assertion():
    """`adequacy` scopes its mutants on `ports_read`, which counts both.

    Measured on the frozen set: 45% of the ports it scopes on carry no
    assertion, so the mutants that count include ones the oracle was never
    able to catch.
    """
    record = _assess(TRIGGER_AND_ASSERT)
    assert record["verdict"] == liveness.LIVE
    assert "hit" in record["reads"], "the trigger port is still READ"
    moved = set(record["asserts_on"]) | set(record["asserts_on_far"])
    assert moved == {"y"}, moved


def test_perturbation_stays_inside_the_declared_width():
    """The illegal-mutant lesson, avoided by construction rather than filtered.

    A one-bit port that receives a literal 2 convicts every oracle that wrote
    `== 1` instead of treating it as a boolean, which is a style difference.
    Here the perturbation is chosen modulo the width, so the value is one an
    implementation could have produced.
    """
    rows = [{"edge": 0, "inputs": {}, "outputs": {"hit": 0, "y": 250}}]
    for port, width, ceiling in (("hit", 1, 2), ("y", 8, 256)):
        for target in [liveness.NEAR, *liveness._targets(width)]:
            moved = liveness._perturb(rows, port, width, None, target)
            if moved is None:
                continue          # already carries that target
            assert 0 <= moved[0]["outputs"][port] < ceiling
            assert moved[0]["outputs"][port] != rows[0]["outputs"][port]


def test_inputs_are_never_perturbed():
    """Changing an input asks a DIFFERENT question of the design.

    An oracle that failed to notice would be right not to, so crediting it with
    liveness for reacting would credit the wrong thing.
    """
    assert "a" not in liveness._widths(CONTRACT)
    record = _assess("""\
def decide(trace):
    for row in trace:
        if row['inputs']['a'] > 99:
            return False, row['edge'], 'a too large'
    return True, 0, 'ok'
""")
    assert record["verdict"] != liveness.LIVE


def test_every_oracle_appears_including_the_ones_nothing_decided():
    """A report that omits what it could not judge reads as a clean result."""
    report = liveness.assess(
        [_oracle(SHARP, "REQ-0001"), _oracle(SHARP, "REQ-0002", ("TP-NONE",)),
         _oracle("def decide(trace):\n    return True, 0, 'ok'\n", "REQ-0003")],
        MODEL, CONTRACT, STIM, base="step")
    assert set(report) == {"REQ-0001", "REQ-0002", "REQ-0003"}
    assert report["REQ-0002"]["verdict"] == liveness.UNKNOWN
    assert "no testpoint" in report["REQ-0002"]["detail"]
    assert report["REQ-0003"]["verdict"] == liveness.UNKNOWN
    assert "no declared output port" in report["REQ-0003"]["detail"]


def test_counts_keep_their_zeroes():
    report = liveness.assess([_oracle(SHARP)], MODEL, CONTRACT, STIM,
                             base="step")
    assert liveness.counts(report) == {
        liveness.LIVE: 1, liveness.DEAD_ORACLE: 0,
        liveness.DEAD_STIMULUS: 0, liveness.UNKNOWN: 0}


def test_a_model_that_will_not_run_is_unknown_not_dead():
    """A broken model is not evidence against a check."""
    report = liveness.assess([_oracle(SHARP)], "def nope(:\n", CONTRACT, STIM,
                             base="step")
    assert report["REQ-0001"]["verdict"] == liveness.UNKNOWN


def test_the_verdict_does_not_depend_on_which_design_it_ran_against():
    """What makes the witness a sufficient stand-in for [O].

    Measured on the frozen 70: identical counts against a generated model
    scoring 30/168 and against the known-good control at 168/168 -- live 44,
    dead-oracle 20, dead-stimulus 3, unknown 3 -- while five oracles reach
    different base verdicts on those two designs and four have different
    assertion port sets. Pinned here on a pair that differ the same way: one
    model satisfies the check and one violates it, and neither can make a
    vacuous oracle able to fail or a sharp one unable to.
    """
    violating = MODEL.replace("'y': self.n", "'y': self.mask(self.n + 1, 8)")
    assert violating != MODEL

    for source in (MODEL, violating):
        report = liveness.assess(
            [_oracle(SHARP, "REQ-0001"), _oracle(VACUOUS, "REQ-0002")],
            source, CONTRACT, STIM, base="step")
        assert report["REQ-0001"]["verdict"] == liveness.LIVE
        assert report["REQ-0002"]["verdict"] == liveness.DEAD_ORACLE

    # and the premise: the two designs really are decided differently
    base = liveness.assess([_oracle(SHARP)], MODEL, CONTRACT, STIM,
                           base="step")["REQ-0001"]["base"]
    other = liveness.assess([_oracle(SHARP)], violating, CONTRACT, STIM,
                            base="step")["REQ-0001"]["base"]
    assert base != other, "otherwise this pins nothing"
