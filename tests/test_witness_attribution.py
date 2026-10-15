"""Where a turn is unlikely to be repaid, said without giving anything authority.

Measured on r-i2c: the debug loop drove VIOLATES 9 -> 5 and then spent its last
three turns on the 5 that remained. Every one of those 5 was a check a
known-good control also fails, so no edit to the model could have cleared them,
and the run reported "13 oracle(s) short of CONFORMS" as though they were 13
unfixed model defects.

The witness had flagged exactly those five -- REQ-0020, 0060, 0066, 0067, 0070 --
before the reference model existed. The note was in `oracles.json` and nothing
downstream read it. These pin that it now travels, and that travelling does not
turn it into a verdict.
"""

from __future__ import annotations

from eda_agent.refmodel_editor import _opening
from specflow.refmodel.compose import _conforms_by_liveness  # noqa: F401
from specflow.refmodel.oracles import RequirementOracle
from specflow.refmodel.session import DebugSession

CONTRACT = {"io": [
    {"name": "clk", "dir": "input", "width": 1},
    {"name": "a", "dir": "input", "width": 1},
    {"name": "y", "dir": "output", "width": 1},
]}

MODEL = """\
from specflow.refmodel.base import RefModel


class Model(RefModel):
    OUTPUT_PORTS = ['y']
    LATENCY_CYCLES = 0

    def step(self, i):
        return {'y': i['a']}
"""

#: Fails the model above, whatever it does.
IMPOSSIBLE = (
    "def decide(trace):\n"
    "    return (False, 0, 'no design satisfies this')\n"
)

STIM = {"TP-0000": [{"a": 0}, {"a": 1}]}


def _session(notes=None) -> DebugSession:
    return DebugSession(
        MODEL, CONTRACT, STIM,
        [RequirementOracle(req_uid="REQ-0001", tp_uids=["TP-0000"],
                           clause="y follows a", source=IMPOSSIBLE),
         RequirementOracle(req_uid="REQ-0002", tp_uids=["TP-0000"],
                           clause="y is stable", source=IMPOSSIBLE)],
        base="step", requirements=[], witness_notes=notes,
        covers={}, verdicts={})


def test_the_witness_DOES_NOT_reach_the_agent():
    """It used to, as a per-oracle flag saying a second implementation fails
    this check too. That is one implementation's behaviour shaping the
    construction of another, which is the leak the [O]-before-[R] ordering
    exists to close and cannot -- the witness IS built before [R].

    The repo already draws this line one boundary over: a control "may reject an
    oracle but never repair one", because quoting a design's trace to the oracle
    author tunes the oracle against it and the model is then tuned against the
    oracle. Same shape, one stage later.
    """
    rows = _session({"REQ-0001": "could not satisfy it either"}).list_oracles()
    for r in rows:
        assert "a_second_implementation_also_fails_this" not in r


def test_a_noted_oracle_is_still_failing_and_still_listed():
    """Attribution, not suppression. Withholding the note must not withhold the
    FINDING: the requirement still fails, still blocks, and is still named."""
    session = _session({"REQ-0001": "could not satisfy it either"})
    failing = {r.req_uid for r in session.failing()}
    assert failing == {"REQ-0001", "REQ-0002"}

    brief = _opening(session)
    assert "REQ-0001" in brief and "REQ-0002" in brief
    assert "second implementation" not in brief


def test_the_note_survives_where_a_READER_can_weigh_it():
    """Removed from the agent, kept in the artifact. The signal is real -- it is
    what the stop reason uses to attribute a residue -- and the objection is to
    who acts on it, not to recording it.

    And the two sources it conflated have different authority: a known-good
    CONTROL failing a check is strong evidence the check is over-strict, while a
    WITNESS failing one is a second reading by the same author from the same
    text, never debugged. Only the weak one was ever shown to the agent.
    """
    session = _session({"REQ-0001": "could not satisfy it either"})
    assert session.witness_notes == {"REQ-0001": "could not satisfy it either"}


def test_an_unmarked_run_says_nothing_extra():
    brief = _opening(_session(None))
    assert "second implementation" not in brief
