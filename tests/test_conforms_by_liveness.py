"""What a CONFORMS is worth, reported next to how many there are.

"46 CONFORMS of 70" was read as the loop converging, on a model that fails 138
of 168 testpoints against golden RTL. Eleven of those 46 came from checks that
no legal value of any port they read could move. The count was right and the
reading was wrong, and nothing in the artifact could have corrected it.
"""

from __future__ import annotations

from specflow.refmodel.compose import _conforms_by_liveness

MECHANICAL = {
    "REQ-0001": "CONFORMS",
    "REQ-0002": "CONFORMS",
    "REQ-0003": "CONFORMS",
    "REQ-0004": "VIOLATES",
    "REQ-0005": "NOT_EXERCISED",
}


def test_a_conforms_from_a_dead_check_is_counted_apart():
    got = _conforms_by_liveness(MECHANICAL, {
        "REQ-0001": "live",
        "REQ-0002": "dead-oracle",
        "REQ-0003": "dead-stimulus",
        "REQ-0004": "live",
    })
    assert got["conforms"] == 3
    assert got["from_a_check_that_can_fail"] == 1
    assert got["from_a_check_that_cannot"] == 2, (
        "both dead verdicts count: neither check decided anything here")
    assert got["not_measured"] == 0


def test_an_unmeasured_set_reports_none_and_never_zero():
    """`over_strict: 0` once meant "no control was supplied" and was read as
    "no oracle is over-strict". A key that says 0 for "did not look" repeats
    that exactly, one level up."""
    got = _conforms_by_liveness(MECHANICAL, {})
    assert got["conforms"] == 3
    assert got["from_a_check_that_can_fail"] is None
    assert got["from_a_check_that_cannot"] is None
    assert got["from_a_check_undecided"] is None


def test_a_partially_measured_set_says_how_much_it_could_not_see():
    """Absent from the map and `unknown` IN the map are different claims: one
    is "this run never asked", the other is "it asked and could not tell"."""
    got = _conforms_by_liveness(MECHANICAL, {"REQ-0001": "live"})
    assert got["from_a_check_that_can_fail"] == 1
    assert got["from_a_check_that_cannot"] == 0
    assert got["from_a_check_undecided"] == 0
    assert got["not_measured"] == 2, (
        "the two CONFORMS with no liveness verdict are neither live nor dead")


def test_an_unknown_liveness_verdict_joins_neither_side():
    """`unknown` means the instrument could not decide -- no replayable
    testpoint, no declared output port, or a model that would not run. Folding
    it into "can fail" would make the reassuring number the default for
    everything unmeasurable, and it is not evidence of deadness either."""
    got = _conforms_by_liveness(MECHANICAL, {
        "REQ-0001": "unknown", "REQ-0002": "unknown", "REQ-0003": "live"})
    assert got["from_a_check_that_can_fail"] == 1
    assert got["from_a_check_that_cannot"] == 0
    assert got["from_a_check_undecided"] == 2


def test_only_conforming_requirements_are_counted():
    got = _conforms_by_liveness(
        {"REQ-0004": "VIOLATES", "REQ-0005": "NOT_EXERCISED"},
        {"REQ-0004": "dead-oracle", "REQ-0005": "dead-oracle"})
    assert got["conforms"] == 0
    assert got["from_a_check_that_cannot"] == 0
