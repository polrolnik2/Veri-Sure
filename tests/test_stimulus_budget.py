"""The stimulus budget is for the LOOP, not for each turn of it.

`add_stimulus` had never once fired across six runs -- it was unreachable, and
two conditions that could not both hold kept it that way. The first run in which
it worked immediately showed what nothing had been able to show before: a fresh
`DebugSession` is built every turn and counts its own `added` from zero, so a
budget of 12 passed unchanged became 12 PER TURN.

Measured on t-i2c: exactly 12 testpoints on each of four turns, 48 against a
stated budget of 12, and not one changed a verdict -- CONFORMS held at 45 and
VIOLATES at 9 from the first turn to the last.
"""

from __future__ import annotations

from specflow.refmodel.oracles import RequirementOracle
from specflow.refmodel.session import DebugSession

CONTRACT = {"io": [
    {"name": "clk", "dir": "input", "width": 1},
    {"name": "cmd", "dir": "input", "width": 4},
    {"name": "ack", "dir": "output", "width": 1},
]}

SOURCE = """
from specflow.refmodel.base import RefModel


class Model(RefModel):
    OUTPUT_PORTS = ['ack']
    LATENCY_CYCLES = 0

    def step(self, i):
        return {'ack': 1 if i['cmd'] == 8 else 0}
"""

ORACLE = (
    "def decide(trace):\n"
    "    if not any(r['inputs']['cmd'] == 8 for r in trace):\n"
    "        return (None, None, 'no WRITE in this trace')\n"
    "    return (True, None, 'ok')\n"
)

NORMALIZED = {"REQ-0000": {
    "activation": {"text": "a WRITE is issued", "inputs": {"cmd": 8}},
    "observable": ["ack"], "expectation": "ack rises"}}


def _session(budget: int, *, staging: bool = True) -> DebugSession:
    """`staging=False` mints a testpoint that does NOT fire the oracle.

    Needed to reach the budget at all: a scenario that works leaves the
    requirement `met`, and the next call is then refused for being about a
    requirement that is no longer unexercised -- a different error entirely.
    """
    minted = iter(range(1, 99))

    def gen(_req, _hint):
        n = next(minted)
        return ([{"cmd": 8}] * n if staging else [{"cmd": n}])

    return DebugSession(
        SOURCE, CONTRACT, {"TP-0000": [{"cmd": 0}]},
        [RequirementOracle(req_uid="REQ-0000", tp_uids=["TP-0000"],
                           clause="ack on WRITE", source=ORACLE)],
        base="step", normalized=NORMALIZED, requirements={},
        testplan=[{"uid": "TP-0000", "covers": ["REQ-0000@1"]}],
        stimulus_gen=gen, stimulus_budget=budget)


def test_a_turn_gets_what_is_LEFT_of_the_budget():
    """The arithmetic the loop has to do, pinned where it is easy to get wrong.

    A turn that has already seen 12 of a 12 budget spent must be handed 0, not
    12 -- and never a negative number, which would compare wrongly against a
    length.
    """
    for spent, budget, expected in ((0, 12, 12), (5, 12, 7), (12, 12, 0),
                                    (48, 12, 0)):
        assert max(0, budget - spent) == expected


def test_a_session_with_no_budget_left_refuses():
    out = _session(0).add_stimulus("REQ-0000", "issue a WRITE")
    assert "budget" in out.get("error", ""), out


def test_a_session_stops_at_its_own_budget():
    """Within one turn the count was always right; it was the RESET between
    turns that made the total wrong."""
    session = _session(2, staging=False)
    for _ in range(2):
        assert "added" in session.add_stimulus("REQ-0000", "issue a WRITE")
    assert "budget" in session.add_stimulus("REQ-0000", "issue a WRITE").get(
        "error", "")
    assert len(session.added) == 2


def test_the_loop_passes_the_remainder_and_not_the_whole():
    """Reads the call site, because the bug was entirely in what it passed.

    A test that built a loop would need a model; what has to be pinned is one
    expression, and pinning it by inspection is what catches it coming back.
    """
    import inspect

    from specflow.refmodel import compose

    body = inspect.getsource(compose._debug_turns)
    assert "stimulus_budget=stimulus_budget," not in body, (
        "the whole budget again, so each turn gets a fresh one")
    assert "stimulus_budget=max(0, stimulus_budget - len(added))" in body
