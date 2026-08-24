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


def test_the_note_reaches_the_agent_marked_per_oracle():
    rows = _session({"REQ-0001": "could not satisfy it either"}).list_oracles()
    by_uid = {r["req_uid"]: r for r in rows}
    assert by_uid["REQ-0001"]["a_second_implementation_also_fails_this"] is True
    assert by_uid["REQ-0002"]["a_second_implementation_also_fails_this"] is False


def test_a_marked_oracle_is_still_failing_and_still_listed():
    """Attribution, not suppression. A note that removed the finding would let
    the witness overrule the requirement, which is the authority it does not
    have -- and would hand the model agent a way to make a VIOLATES vanish."""
    session = _session({"REQ-0001": "could not satisfy it either"})
    failing = {r.req_uid for r in session.failing()}
    assert failing == {"REQ-0001", "REQ-0002"}, (
        "a marked oracle still fails and still blocks")

    brief = _opening(session)
    assert "REQ-0001" in brief and "REQ-0002" in brief
    assert "[a second implementation fails this too]" in brief


def test_the_brief_says_it_is_not_a_verdict():
    """The measured failure mode of the opposite phrasing: when the witness
    could REJECT, over-strictness fell 27 -> 15 and convictions rose 2 -> 16 --
    oracles relaxed until they stopped disagreeing, because compliance was the
    only way to survive. The wording has to leave declining open."""
    brief = _opening(_session({"REQ-0001": "could not satisfy it either"}))
    assert "not a verdict" in brief
    assert "no better authority than yours" in brief
    assert "genuinely the model's fault" in brief


def test_an_unmarked_run_says_nothing_extra():
    brief = _opening(_session(None))
    assert "second implementation" not in brief
