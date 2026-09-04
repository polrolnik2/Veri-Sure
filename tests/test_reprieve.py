"""A `live` verdict overturns a reachability discard, and never an off-target one.

The second half is the point. Correspondence asks whether the check tests its
requirement; liveness cannot see that, so a live-but-off-target check must stay
rejected. Measured on k1-dcfsm: 24 of 53 discards are live, but only 8 were held
on a reachability ground -- 16 were off-target, and admitting those would be a
verdict liveness does not support.
"""
import pytest

from specflow.oracles_stage import _reprieved
from specflow.refmodel import liveness as _L


@pytest.mark.parametrize("reason", [
    "never reached in 3 attempt(s)",
    "unreached: the activation was driven and the check saw nothing",
])
def test_live_overturns_a_reachability_discard(reason):
    assert _reprieved(reason, _L.LIVE) is True


@pytest.mark.parametrize("reason", [
    "off-target: the unlicensed False path is saved_addr != 0 on rst rising",
    "off-target: never reached the right window",          # substring trap
    # "not-assertable" is a claim about the REQUIREMENT stating no obligation,
    # not about the check being unreachable. Liveness cannot refute it, and both
    # of k1-dcfsm's NOT_ASSERTABLE checks are this shape.
    "not-assertable: The sentence lacks an actionable effect",
    "not-assertable: Both a normative trigger and a normative effect are missing",
])
def test_live_never_overturns_a_claim_about_the_requirement(reason):
    assert _reprieved(reason, _L.LIVE) is False


@pytest.mark.parametrize("verdict", [
    _L.DEAD_ORACLE, _L.DEAD_STIMULUS, _L.UNKNOWN, None, "",
])
def test_only_a_live_verdict_reprieves(verdict):
    assert _reprieved("never reached in 3 attempt(s)", verdict) is False


def test_an_unrecognised_ground_is_not_reprieved():
    # Silence is not evidence. A ground this predicate does not understand is
    # left alone rather than assumed to be a reachability claim.
    assert _reprieved("malformed: the reply did not parse", _L.LIVE) is False
    assert _reprieved("", _L.LIVE) is False
