"""A model that crashes is a finding about the MODEL, and it is not progress.

Measured on h-i2c r3. One debug edit raised
`AttributeError("'Model' object has no attribute 'COMPLETE'")` and 54 of 77
oracles stopped deciding in a single step. Two things went wrong at once, and
they are opposite errors:

* every one of those 54 was reported ORACLE_INVALID, which routes to "regenerate
  the oracle" -- sending the loop at 54 checks that were fine while the design
  was what fell over;
* `distance()` counted failing plus unexercised, and a `broken` result is
  neither, so the score COLLAPSED and the crashing model was recorded as the
  best one seen. Crashing scored as fixing.
"""

from __future__ import annotations

from specflow.refmodel import verdict as V
from specflow.refmodel.oracles import RequirementOracle, decide_all
from specflow.refmodel.session import DebugSession

CONTRACT = {"io": [
    {"name": "clk", "dir": "input", "width": 1},
    {"name": "a", "dir": "input", "width": 1},
    {"name": "y", "dir": "output", "width": 1},
]}

WORKS = """\
from specflow.refmodel.base import RefModel


class Model(RefModel):
    OUTPUT_PORTS = ['y']
    LATENCY_CYCLES = 0

    def step(self, i):
        return {'y': i['a']}
"""

#: Imports, instantiates, and raises on the first step -- exactly h-i2c r3's
#: shape: an attribute the edit forgot to define.
CRASHES = WORKS.replace("return {'y': i['a']}", "return {'y': self.COMPLETE}")

STIM = {"TP-0000": [{"a": 0}, {"a": 1}]}
TESTPLAN = [{"uid": "TP-0000", "covers": ["REQ-0001@1"]}]

ORACLE = RequirementOracle(
    req_uid="REQ-0001", tp_uids=["TP-0000"], clause="y follows a",
    source="def decide(trace):\n"
           "    for row in trace:\n"
           "        if row['outputs']['y'] != row['inputs']['a']:\n"
           "            return False, row['edge'], 'y did not follow a'\n"
           "    return True, 0, 'ok'\n")


def _results(source):
    return decide_all([ORACLE], source, CONTRACT, STIM, base="step")


def test_a_model_crash_is_marked_as_the_model_s(  ):
    r = _results(CRASHES)[0]
    assert r.broken and r.model_broke
    assert r.model_defect(), "a crash is a finding about the model"


def test_an_oracle_defect_is_not_marked_as_the_model_s():
    bad = ORACLE.model_copy(update={
        "source": "def decide(trace):\n    return trace['y']\n"})
    r = decide_all([bad], WORKS, CONTRACT, STIM, base="step")[0]
    assert r.broken and not r.model_broke
    assert not r.model_defect(), "chasing this by editing the model is the bug"


def test_a_crash_is_routed_to_the_model_not_the_oracle_author():
    r = _results(CRASHES)[0]
    assert V.of_result(r) == "VIOLATES"
    assert V.ROUTE["VIOLATES"] == "fix the implementation"


def test_a_verified_oracle_that_breaks_anyway_decides_nothing():
    """Not the model's to answer: the oracle passed verification against a
    witness, so a break here is neither party's known fault."""
    bad = ORACLE.model_copy(update={
        "source": "def decide(trace):\n    return trace['y']\n"})
    r = decide_all([bad], WORKS, CONTRACT, STIM, base="step")[0]
    assert V.of_result(r) == "UNDECIDED"


def _session(source):
    return DebugSession(source, CONTRACT, STIM, [ORACLE], base="step",
                        testplan=TESTPLAN)


def test_crashing_the_model_does_not_score_as_fixing_it():
    """The whole reason r3 looked like closure."""
    ok = _session(WORKS)
    assert ok.distance() == 0

    s = _session(CRASHES)
    assert s.distance() >= 1, (
        "a model that raises on every oracle must not score as satisfying them")


#: Runs, and gets one of the two oracles wrong. A session starting here has a
#: model route open (I8) and a distance of 1.
WRONG = WORKS.replace("return {'y': i['a']}", "return {'y': 0}")

#: A second oracle the WRONG model satisfies, so crashing loses something the
#: wrong-but-running model had. Without it the two score the same and the tie
#: rule would carry the test rather than the fix.
LOW_FIRST = RequirementOracle(
    req_uid="REQ-0002", tp_uids=["TP-0000"], clause="y is low at the start",
    source="def decide(trace):\n"
           "    if trace[0]['outputs']['y'] != 0:\n"
           "        return False, 0, 'y started high'\n"
           "    return True, 0, 'y started low'\n")

LONG = {"TP-0000": [{"a": 1}] * 40}

#: The h-i2c r3 shape, reproduced: a crash the mechanical checks DO NOT catch,
#: because it needs internal state deeper than their sweep drives. The real one
#: was `COMPLETE = 16` bound as a local in one method and read as `self.COMPLETE`
#: in another, so it raised at edge 25 of a real testpoint and nowhere earlier.
DEEP_CRASH = ("def step(self, i):\n"
              "    self._n = getattr(self, '_n', 0) + 1\n"
              "    return {'y': self.COMPLETE if self._n > 12 else 0}")


def test_the_mechanical_checks_do_not_catch_a_state_deep_crash():
    """Which is why `distance()` has to. If validation caught every crash this
    would be belt and braces; it does not, and h-i2c r3 shipped one."""
    s = DebugSession(WRONG, CONTRACT, LONG, [ORACLE], base="step",
                     testplan=TESTPLAN)
    assert s.replace_method("step", DEEP_CRASH)["accepted"] is True


def test_a_crashing_edit_is_never_returned_as_the_best():
    s = DebugSession(WRONG, CONTRACT, LONG, [ORACLE, LOW_FIRST], base="step",
                     testplan=TESTPLAN)
    assert len(s.failing()) == 1 and s.distance() == 1

    assert s.replace_method("step", DEEP_CRASH)["accepted"] is True
    assert s.distance() == 2, "crashing lost the oracle the wrong model satisfied"
    assert s.best() == WRONG, "best() must not hand back a model that crashes"
