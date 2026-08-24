"""The mechanical verdict: every requirement routed, none silently dropped."""

from __future__ import annotations

from specflow.refmodel import verdict as V


REQS = [{"uid": f"REQ-{i:04d}"} for i in range(6)]


def test_every_requirement_gets_a_verdict_even_with_no_evidence():
    """The property the enum exists for: no silent subset.

    A requirement absent from this map would be one nothing decided AND nothing
    reported -- which is what today's screening does to the 30 unexercised
    oracles, whose cause is computed and then dropped into a JSON blob.
    """
    out = V.classify(discarded={}, passing=set(), failing=set(),
                     had_oracle=set(), requirements=REQS)
    assert set(out) == {r["uid"] for r in REQS}
    assert set(out.values()) == {"UNDECIDED"}


def test_each_discard_reason_routes_to_a_different_party():
    """`trust.py` already knows these four causes apart; this is what keeps them
    apart once they leave `Screened.discarded`."""
    discarded = {
        "REQ-0000": "unexercised: its author said 'met' but the oracle's scenario ...",
        "REQ-0001": "over-strict: the known-good control fails it at edge 12 -- ...",
        "REQ-0002": "vacuous: passed all 4 mutants it could observe",
        "REQ-0003": "malformed: the oracle names no testpoint to replay",
        "REQ-0004": "disagreed: its author said 'met' but the oracle fails that same model",
    }
    out = V.classify(discarded=discarded, passing=set(), failing=set(),
                     had_oracle=set(discarded), requirements=REQS)
    assert out["REQ-0000"] == "NOT_EXERCISED"
    assert out["REQ-0001"] == "ORACLE_INVALID"
    assert out["REQ-0002"] == "VACUOUS"
    assert out["REQ-0003"] == "ORACLE_INVALID"
    assert out["REQ-0004"] == "ORACLE_INVALID"

    # The routing is the point, not the naming: a thin testplan and a wrong
    # model must not produce the same instruction.
    assert V.ROUTE[out["REQ-0000"]] == "fix the stimulus"
    assert V.ROUTE[out["REQ-0001"]] == "regenerate the oracle"


def test_a_decided_oracle_outranks_its_discard_record():
    """A requirement cannot be both decided and discarded, but if the inputs
    disagree the DECISION wins -- it is the one backed by something that ran."""
    out = V.classify(
        discarded={"REQ-0000": "unexercised: ..."},
        passing=set(), failing={"REQ-0000"},
        had_oracle={"REQ-0000"}, requirements=REQS,
    )
    assert out["REQ-0000"] == "VIOLATES"


def test_conforms_is_the_only_non_blocking_verdict():
    """Including UNOBSERVABLE, which blocks: a requirement with no observable at
    the boundary is a hole in the spec, and letting it through is the silent
    omission this pipeline exists to prevent. It routes to a human, not to an
    agent -- but it does not pass."""
    assert "CONFORMS" not in V.BLOCKING
    assert V.BLOCKING == frozenset(set(V.ROUTE) - {"CONFORMS"})
    assert "UNOBSERVABLE" in V.BLOCKING


def test_counts_keeps_the_zeroes():
    """`over_strict: 0` once meant "never looked" and read as "none found"
    (`trust.py:99-104`). A key that appears only when non-zero repeats that."""
    out = V.classify(discarded={}, passing={"REQ-0000"}, failing=set(),
                     had_oracle={"REQ-0000"}, requirements=REQS)
    counts = V.counts(out)
    assert set(counts) == set(V.ROUTE)
    assert counts["CONFORMS"] == 1
    assert counts["VACUOUS"] == 0


def test_every_verdict_has_a_route():
    """A verdict nobody can act on is worse than no verdict: it blocks and
    instructs nothing, which is exactly today's discarded-oracle behaviour."""
    from typing import get_args
    assert set(get_args(V.Verdict)) == set(V.ROUTE)
    assert all(V.ROUTE.values())


def test_an_unknown_discard_prefix_is_undecided_not_silently_dropped():
    out = V.of_discard("something trust.py does not write today")
    assert out == "UNDECIDED"
