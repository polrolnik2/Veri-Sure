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


# ------------------------------------------------------- blocking on verdicts
#
# The one piece of wiring between an isolated oracle set and driving the loop.
# `_debug_turns` gates on `has_errors(issues)`, and until now only the JUDGE
# could produce those -- so mechanical verdicts could be reported and could not
# block, which is why the judge had to stay whatever the evidence said.


def test_mechanical_verdicts_produce_the_issues_the_gate_reads():
    from specflow.schema import has_errors

    out = V.issues({"REQ-0000": "CONFORMS", "REQ-0001": "VIOLATES"})
    assert has_errors(out)
    assert [i.path for i in out] == ["refmodel.REQ-0001.violates"]


def test_conforms_produces_no_issue():
    """Same acceptance asymmetry as `judge.to_issue` returning None for `met`:
    nothing here certifies anything. The must-pass/must-fail gates and the suite
    certify."""
    assert V.to_issue("REQ-0000", "CONFORMS") is None
    assert V.issues({f"REQ-{i:04d}": "CONFORMS" for i in range(5)}) == []


def test_the_issue_names_the_party_that_must_act():
    """The difference from the judge's issue, and the reason the enum exists.
    `judge.to_issue` hands every blocking verdict to the reference-model agent
    whatever the cause, so a thin testplan and a wrong model arrive as the same
    instruction."""
    stim = V.to_issue("REQ-0002", "NOT_EXERCISED", "cmd=8 never driven")
    assert "fix the stimulus" in stim.message
    assert "cmd=8 never driven" in stim.message

    impl = V.to_issue("REQ-0001", "VIOLATES")
    assert "fix the implementation" in impl.message

    spec = V.to_issue("REQ-0003", "UNOBSERVABLE")
    assert "return to spec authoring" in spec.message

    # Three different parties, three different instructions.
    assert len({stim.message.split(" -- ")[0], impl.message, spec.message}) == 3


def test_issues_are_ordered_by_requirement_not_by_dict_order():
    """A repair prompt that reorders itself between runs is a prompt whose cache
    never warms, and a diff nobody can read."""
    out = V.issues({"REQ-0009": "VIOLATES", "REQ-0001": "VACUOUS",
                    "REQ-0005": "NOT_EXERCISED"})
    assert [i.path.split(".")[1] for i in out] == ["REQ-0001", "REQ-0005", "REQ-0009"]


def test_every_blocking_verdict_can_produce_an_issue():
    """No verdict may be blocking-but-unreportable: that combination blocks the
    pipeline while instructing nobody, which is exactly today's discarded-oracle
    behaviour."""
    for v in V.BLOCKING:
        assert V.to_issue("REQ-0000", v) is not None, v


def test_an_off_target_oracle_is_invalid_not_undecided():
    """A well-formed, satisfiable, non-vacuous check OF THE WRONG THING still
    cannot discharge its requirement, and the party to fix it is the author.
    Without a mapping it fell through to UNDECIDED -- "nothing decided it" --
    which names no party at all."""
    from specflow.refmodel import verdict as V

    assert V.of_discard("off-target: it never reads y") == "ORACLE_INVALID"
    assert V.ROUTE["ORACLE_INVALID"] == "regenerate the oracle"
