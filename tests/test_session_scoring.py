"""The debug session must not reward making a requirement unverifiable.

`failing()` counts `ok is False` and not `ok is None` (`oracles.py:80-89`), so
scoring a turn on the failing count alone means an edit that stops the design
ever reaching a scenario converts a VIOLATES into a NOT_EXERCISED, lowers the
count, and is recorded as a new best. That is the model-edit half of the
coverage ratchet, and it is live in code that ships today.
"""

from __future__ import annotations

from specflow.refmodel.oracles import OracleResult
from specflow.refmodel.session import DebugSession

CONTRACT = {
    "io": [
        {"name": "clk", "dir": "input", "width": 1},
        {"name": "a", "dir": "input", "width": 1},
        {"name": "y", "dir": "output", "width": 1},
    ]
}

SOURCE = '''
from specflow.refmodel.base import RefModel


class Model(RefModel):
    OUTPUT_PORTS = ['y']
    LATENCY_CYCLES = 0

    def step(self, i):
        return {'y': i['a']}
'''


def _session(**kw) -> DebugSession:
    return DebugSession(SOURCE, CONTRACT, {"TP-0000": [{"a": 1}]}, [],
                        base="step", **kw)


def _results(session, *states):
    """Force a decided state without needing real oracles."""
    session._results = [
        OracleResult(f"REQ-{i:04d}", ok=ok) for i, ok in enumerate(states)
    ]


def test_distance_counts_unexercised_alongside_failing():
    s = _session()
    _results(s, False, None, True)
    assert len(s.failing()) == 1
    assert len(s.undecided()) == 1
    assert s.distance() == 2


def test_turning_a_violation_into_an_unreachable_scenario_is_not_progress():
    """The regression this exists for. Before the fix, the second state scored
    BETTER than the first because its failing count was lower."""
    s = _session()
    _results(s, False, False)          # two real violations
    s.best_failing = None
    assert s.note_best("before") is True
    assert s.best_failing == 2

    _results(s, None, None)            # both scenarios now unreachable
    assert s.note_best("after") is False, (
        "an edit that made both scenarios unreachable was recorded as a new best"
    )
    assert s.best() == "before"


def test_genuinely_satisfying_a_clause_still_improves_the_score():
    """The fix must not make the session inert -- a real repair still wins."""
    s = _session()
    _results(s, False, False)
    s.best_failing = None
    s.note_best("before")

    _results(s, True, False)
    assert s.note_best("after") is True
    assert s.best() == "after" and s.best_failing == 1


def test_a_broken_oracle_counts_neither_way():
    """It decides nothing, so chasing it means editing the model to fix a defect
    in the check -- the confusion the whole design exists to prevent."""
    s = _session()
    s._results = [OracleResult("REQ-0000", ok=False, broken="decide() raised")]
    assert s.failing() == []
    assert s.undecided() == []
    assert s.distance() == 0


def test_ties_do_not_overwrite():
    """Unchanged from `rtl_editor._EditSession.note_best`, whose rule is pinned
    by `tests/test_rollback_guard.py`: the earliest source at a given score wins."""
    s = _session()
    _results(s, False)
    s.best_failing = None
    s.note_best("first")
    assert s.note_best("second") is False
    assert s.best() == "first"
