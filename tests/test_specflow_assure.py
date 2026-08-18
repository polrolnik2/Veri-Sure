"""M1: the deterministic gates, tested with no model anywhere.

Every fixture here is built so its ground truth is known by construction. That
is the whole reason M1 lands before S1: the gate is what tells us whether an
agent's output is acceptable, so a wrong gate makes every later failure
unattributable -- you cannot tell a bad agent from a bad gate by watching a loop
that will not converge.
"""

from __future__ import annotations

from specflow import ids
from specflow.assure import (
    assure_requirements_to_testplan,
    assure_testplan_to_bins,
    assure_testplan_to_checks,
    check_spec_attribution,
)
from specflow.schema import Issue, has_errors, render_issues


def kinds(issues: list[Issue]) -> set[str | None]:
    return {i.kind for i in issues}


def req(uid: str, rev: int = 1, needs=("testplan",)) -> dict:
    return {"uid": uid, "rev": rev, "needs": list(needs)}


def tp(uid: str, covers: list[str], rev: int = 1, needs=("bin", "check")) -> dict:
    return {"uid": uid, "rev": rev, "covers": covers, "needs": list(needs)}


# ---------------------------------------------------------------- ids


def test_mint_is_zero_padded_and_sorts_lexically():
    assert ids.mint("REQ", 7) == "REQ-0007"
    assert sorted([ids.mint("REQ", 10), ids.mint("REQ", 9)]) == ["REQ-0009", "REQ-0010"]


def test_parse_ref_pins_revision():
    assert ids.parse_ref("REQ-0007@2") == ids.Ref("REQ-0007", 2)
    assert ids.parse_ref("REQ-0007").rev is None


def test_next_index_never_reuses_a_retired_uid():
    # Hole at 0001 must NOT be refilled: an old reference would silently
    # re-resolve to a different artifact.
    assert ids.next_index(["REQ-0000", "REQ-0002"], "REQ") == 3


def test_method_name_is_mechanical_both_ways():
    assert ids.method_name("REQ-0007") == "_req_0007"


# ---------------------------------------------- link defects, one per test


def test_clean_link_produces_no_issues():
    issues = assure_requirements_to_testplan(
        [req("REQ-0000"), req("REQ-0001")],
        [tp("TP-0000", ["REQ-0000@1"]), tp("TP-0001", ["REQ-0001@1"])],
    )
    assert issues == []
    assert not has_errors(issues)


def test_uncovered_requirement_is_an_error():
    issues = assure_requirements_to_testplan(
        [req("REQ-0000"), req("REQ-0001")],
        [tp("TP-0000", ["REQ-0000@1"])],
    )
    assert "uncovered" in kinds(issues)
    assert any("REQ-0001" in i.path for i in issues)
    assert has_errors(issues)


def test_orphaned_cover_is_an_error():
    issues = assure_requirements_to_testplan(
        [req("REQ-0000")],
        [tp("TP-0000", ["REQ-0000@1"]), tp("TP-0001", ["REQ-9999@1"])],
    )
    assert "orphaned" in kinds(issues)


def test_unwanted_coverage_is_an_error():
    # REQ-0001 does not declare needs=testplan, so covering it is padding.
    issues = assure_requirements_to_testplan(
        [req("REQ-0000"), req("REQ-0001", needs=())],
        [tp("TP-0000", ["REQ-0000@1"]), tp("TP-0001", ["REQ-0001@1"])],
    )
    assert "unwanted" in kinds(issues)
    # ...and it must NOT also be reported uncovered; that would be double noise.
    assert not any(
        i.kind == "uncovered" and "REQ-0001" in i.path for i in issues
    )


def test_outdated_cover_is_an_error():
    issues = assure_requirements_to_testplan(
        [req("REQ-0000", rev=2)],
        [tp("TP-0000", ["REQ-0000@1"])],
    )
    assert "outdated" in kinds(issues)
    assert has_errors(issues)


def test_unpinned_cover_is_only_a_warning():
    issues = assure_requirements_to_testplan(
        [req("REQ-0000")], [tp("TP-0000", ["REQ-0000"])]
    )
    assert kinds(issues) == {"outdated"}
    assert not has_errors(issues)


def test_covering_nothing_is_an_error():
    issues = assure_requirements_to_testplan([req("REQ-0000")], [tp("TP-0000", [])])
    assert "orphaned" in kinds(issues)


def test_duplicate_source_uid_is_an_error():
    issues = assure_requirements_to_testplan(
        [req("REQ-0000"), req("REQ-0000")], [tp("TP-0000", ["REQ-0000@1"])]
    )
    assert any("duplicate uid" in i.message for i in issues)


# ------------------------------------------- the same engine, other links


def test_testplan_needs_both_a_bin_and_a_check():
    tps = [tp("TP-0000", ["REQ-0000@1"])]
    bins = [{"uid": "BIN-0000", "covers": ["TP-0000@1"]}]

    assert assure_testplan_to_bins(tps, bins) == []

    # A bin with no check: coverable, and proves nothing when covered.
    check_issues = assure_testplan_to_checks(tps, [])
    assert "uncovered" in kinds(check_issues)


# ---------------------------------------------------------------- G1 spans

SPEC = (
    "The module adds two 8-bit inputs a and b.\n"
    "On overflow the output saturates to all ones.\n"
)


def span_for(text: str, fragment: str) -> dict:
    start = text.index(fragment)
    return {"start": start, "end": start + len(fragment), "quote": fragment}


def test_full_attribution_is_clean():
    issues = check_spec_attribution(
        SPEC,
        [
            {"uid": "REQ-0000", "spec_spans": [span_for(SPEC, SPEC.split("\n")[0])]},
            {"uid": "REQ-0001", "spec_spans": [span_for(SPEC, SPEC.split("\n")[1])]},
        ],
    )
    assert issues == []


def test_unattributed_spec_text_is_reported():
    # The saturation sentence is dropped -- exactly the failure the whole
    # pipeline exists to catch, since no downstream gate can see it.
    issues = check_spec_attribution(
        SPEC, [{"uid": "REQ-0000", "spec_spans": [span_for(SPEC, SPEC.split("\n")[0])]}]
    )
    assert "uncovered" in kinds(issues)
    assert any("saturates" in i.message for i in issues)


def test_non_verbatim_quote_is_rejected():
    issues = check_spec_attribution(
        SPEC,
        [
            {
                "uid": "REQ-0000",
                "spec_spans": [{"start": 0, "end": 10, "quote": "NOT THE SPEC"}],
            }
        ],
    )
    assert any("verbatim" in i.message for i in issues)


def test_requirement_with_no_span_is_rejected():
    issues = check_spec_attribution(SPEC, [{"uid": "REQ-0000", "spec_spans": []}])
    assert any("no spec span" in i.message for i in issues)


def test_a_wrong_offset_no_longer_rejects_a_verbatim_quote():
    """Offsets are a hint for disambiguation, not the check.

    Requiring exact character positions rejected 31 of 31 spans on a 14.3KB
    spec while 30 of those quotes were verbatim and locatable by search. The
    arithmetic was rejecting good attribution and saying nothing about what was
    actually wrong.
    """
    quote = SPEC.strip().split("\n")[0][:40]
    assert len(quote) >= 24, "fixture too short to be a valid span"
    issues = check_spec_attribution(
        SPEC,
        [{"uid": "REQ-0000",
          "spec_spans": [{"start": 99999, "end": 99999, "quote": quote}]}],
    )
    assert not any("verbatim" in i.message for i in issues)


def test_a_quote_that_is_not_in_the_spec_is_still_rejected():
    """Locating by search must not weaken the verbatim requirement."""
    issues = check_spec_attribution(
        SPEC,
        [{"uid": "REQ-0000",
          "spec_spans": [{"start": 0, "end": 40,
                          "quote": "this sentence appears nowhere in the spec"}]}],
    )
    assert any("verbatim" in i.message for i in issues)


def test_render_matches_contract_linter_format():
    # Same dialect as eda_agent.contract_linter.render_contract_issues, so the
    # repair prompt reads identically whichever gate produced the list.
    out = render_issues([Issue("error", "requirement.REQ-0001", "no testplan covers it")])
    assert out == "- [error] requirement.REQ-0001: no testplan covers it\n"
    assert render_issues([]) == ""


def test_shared_and_short_spans_remain_legal():
    """Both are legitimate attribution, and an earlier attempt at this gate
    wrongly rejected them.

    A port declaration is a short quote, and one sentence can genuinely
    constrain two requirements -- in the half-adder fixture "The module should
    implement a half adder..." constrains both `sum` and `cout`. Rules banning
    short or shared spans looked like anti-gaming measures and were really
    false positives; the unattributed-text check below is what actually catches
    a decomposition that attributes nothing.
    """
    quote = SPEC.strip()
    issues = check_spec_attribution(
        SPEC,
        [
            {"uid": "REQ-0000", "spec_spans": [{"start": 0, "end": len(quote),
                                                "quote": quote}]},
            {"uid": "REQ-0001", "spec_spans": [{"start": 0, "end": len(quote),
                                                "quote": quote}]},
        ],
    )
    assert not [i for i in issues if i.severity == "error"], issues


def test_attributing_nothing_is_still_caught():
    """The load-bearing check. A decomposition whose spans cover a sliver of the
    spec must fail, which is what rejected every round of a live run that cited
    the same opening paragraph from 30 of 31 requirements."""
    issues = check_spec_attribution(
        SPEC,
        [{"uid": "REQ-0000", "spec_spans": [{"start": 0, "end": 8,
                                             "quote": SPEC.strip()[:8]}]}],
    )
    assert any(i.kind == "uncovered" for i in issues)


# ------------------------------------------------- G1 whitespace-insensitivity


def test_locate_tolerates_indentation_but_not_fabrication():
    """A faithful quote that differs only in whitespace runs still locates.

    The check exists to catch a fabricated quote, and it still does: the words
    must be the spec's words in the spec's order. What it no longer rejects is a
    transcription that lost two spaces of list indentation -- which is what
    hard-failed the `i2c_master_bit_ctrl` node after four rounds, on a span whose
    every one of 14,842 characters `difflib` placed in a matching block.
    """
    from specflow.assure import _locate

    spec = "Modes:\n    - START\n        - STOP\n  Any other command is ignored.\n"

    # exact still wins, and returns the exact span
    assert _locate(spec, "- STOP", 0) == (spec.index("- STOP"), spec.index("- STOP") + 6)

    # re-indented and re-wrapped: same words, different whitespace runs
    located = _locate(spec, "- START\n  - STOP\nAny other command is ignored.", 0)
    assert located is not None
    start, end = located
    assert spec[start:end].split() == "- START - STOP Any other command is ignored.".split()

    # fabricated text is still rejected, whitespace or not
    assert _locate(spec, "- RESTART", 0) is None
    assert _locate(spec, "Any   other   command   is   forbidden.", 0) is None


def test_locate_maps_whitespace_match_back_to_real_offsets():
    """The returned span must index the original text, not the projection."""
    from specflow.assure import _locate

    spec = "aaa\n\n\nbbb ccc\n\nddd"
    located = _locate(spec, "bbb ccc ddd", 0)
    assert located is not None
    start, end = located
    assert spec[start:end] == "bbb ccc\n\nddd"


def test_g1_accepts_a_span_that_differs_only_in_indentation():
    """End to end: the coverage hole closes, so the gate does not block."""
    from specflow.assure import check_spec_attribution

    spec = (
        "The counter counts up.\n"
        "  - On overflow it saturates.\n"
        "      - It does not wrap.\n"
    )
    # One span, covering the whole spec, with the list indentation flattened --
    # the exact shape that failed on i2c_master_bit_ctrl.
    reqs = [
        {"uid": "REQ-0000", "rev": 1, "text": "counts up and saturates",
         "kind": "function", "needs": ["testplan"],
         "spec_spans": [{"start": 0, "end": len(spec), "quote":
                         "The counter counts up.\n"
                         "- On overflow it saturates.\n"
                         "- It does not wrap."}]},
    ]
    assert check_spec_attribution(spec, reqs) == []
