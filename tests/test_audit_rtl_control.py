"""`score` must take the audit column from an RTL control, not only a replay.

**A ZERO OVER A DENOMINATOR OF FOURTEEN IS NOT A ZERO.** The Python control in
this tree exposes NONE of the 24 declared probes, so most of the accepted set
abstains on it by construction; four recorded runs report `audit = 0.0` over
14, 15, 17 and 17 checks of 111, 117, 113 and 103. Measured on the same module,
an RTL control is judged on 41 checks where the transliteration manages 14.

`score` cannot run a simulator, so the RTL verdicts arrive already computed.
What is pinned here is that it USES them, counts them the same way, and still
reports the conformance gap.
"""
import pytest

from specflow.scorecard import score

CONTRACT = {"io": [
    {"name": "clk", "dir": "input", "width": 1},
    {"name": "q", "dir": "output", "width": 1},
    {"name": "idle", "dir": "probe", "width": 1},
    {"name": "busyish", "dir": "probe", "width": 1},
], "probes": ["idle", "busyish"]}

REQS = [{"uid": f"REQ-{i:04d}", "unit_kind": "behavioural"} for i in range(1, 4)]
NORM = [{"req_uid": r["uid"], "observable": ["q"]} for r in REQS]
ORACLES = [{"req_uid": r["uid"], "source": "def decide(trace):\n    return True",
            "tp_uids": ["TP-0000"], "clause": ""} for r in REQS]


def _score(**kw):
    return score(oracles=ORACLES, normalized=NORM, stimulus_by_tp={},
                 contract=CONTRACT, population=[], requirements=REQS, **kw)


def test_rtl_verdicts_supply_the_audit_column():
    card = _score(audit_verdicts={
        "REQ-0001": {"TP-0000": True},
        "REQ-0002": {"TP-0000": False},     # convicts the control
        "REQ-0003": {"TP-0000": True},
    })
    assert card.control_judges == 3, (
        "every check with a non-empty verdict map is one the control can be "
        "judged on")
    assert card.control_convicted_by == 1
    assert card.audit == pytest.approx(1 / 3)


def test_an_abstaining_check_is_not_in_the_denominator():
    """An empty verdict map is an abstention, not a pass."""
    card = _score(audit_verdicts={
        "REQ-0001": {"TP-0000": True},
        "REQ-0002": {},                      # abstained on the control
        "REQ-0003": {"TP-0000": False},
    })
    assert card.control_judges == 2, (
        "an abstention must SHRINK the denominator, never count as a check "
        "the control survived")
    assert card.control_convicted_by == 1
    assert card.audit == pytest.approx(0.5)


def test_a_wider_denominator_reports_a_worse_rate_and_that_is_the_point():
    narrow = _score(audit_verdicts={"REQ-0002": {"TP-0000": False}})
    wide = _score(audit_verdicts={
        "REQ-0001": {"TP-0000": True}, "REQ-0002": {"TP-0000": False},
        "REQ-0003": {"TP-0000": True}})
    assert narrow.control_judges == 1 and narrow.audit == pytest.approx(1.0)
    assert wide.control_judges == 3 and wide.audit == pytest.approx(1 / 3)
    assert wide.control_judges > narrow.control_judges


def test_the_conformance_gap_is_still_reported():
    card = _score(audit_verdicts={"REQ-0001": {"TP-0000": True}},
                  audit_absent=["idle", "busyish"])
    joined = " ".join(card.notes)
    assert "NOT contract-conformant" in joined, (
        "a control exposing none of the declared probes must be named as "
        "non-conformant, or its missing interface reads as a property of the "
        "check set")
    assert "2 of the 2 declared probe(s)" in joined


def test_no_control_at_all_is_absent_not_zero():
    card = _score()
    assert card.control_judges == 0
    assert any("absent, not 0%" in n for n in card.notes), (
        "reporting 0.0% with no control is the class of error this guards")


def test_verdicts_outside_the_accepted_set_are_ignored():
    card = _score(audit_verdicts={
        "REQ-0001": {"TP-0000": False},
        "REQ-9999": {"TP-0000": False},      # not an accepted check
    })
    assert card.control_judges == 1, (
        "the audit denominator is the ACCEPTED set; a verdict for a check that "
        "is not in it must not enlarge it")
