"""The triple, computed by the run that earned it.

Every span, blindness and audit figure on this branch was taken afterwards by a
driver, against inputs the driver chose -- which is how a run came to be scored
against a contract that was not the one in force, and against a nine-design
yardstick predating the probes 82 of its 96 checks read. These pin the rules so
the number a run prints is the number anyone re-running it gets.
"""
from __future__ import annotations

import inspect
import re

from specflow import scorecard as S


def _form(uid: str, observable: list[str]) -> dict:
    return {"req_uid": uid, "observable": observable}


def _check(uid: str, source: str = "def decide(trace):\n    return (True, None, '')"):
    return {"req_uid": uid, "tp_uids": ["TP-1"], "clause": "c", "source": source}


def _req(uid, kind="behavioural"):
    return {"uid": uid, "unit_kind": kind}


def test_span_is_over_the_BEHAVIOURAL_requirements():
    """S1 classifies each authorial unit it mints and only one of the three
    kinds is a claim about behaviour a check could decide.

    Measured on this module's own run: 120 behavioural, 19 scaffolding, 9
    interface. Scaffolding is a heading or a list marker; an interface unit
    states what ports the module declares, which the contract already fixes. A
    suite is not less complete for failing to check either.
    """
    card = S.score(
        oracles=[_check("R1")],
        normalized=[_form("R1", ["busy"]), _form("R2", ["al"]),
                    _form("R3", [])],
        requirements=[_req("R1"), _req("R2", "interface"),
                      _req("R3", "scaffolding")],
        stimulus_by_tp={}, contract={"io": []}, population=[])
    assert card.requirements_behavioural == 1
    assert card.requirements_minted == 3
    #: Reported beside it, because it is normalize's own evidence rather than a
    #: classifier's label and a reader has to be able to see them disagree.
    assert card.requirements_observable == 2
    assert card.trusted == 1 and card.span == 1.0, card

    #: A check written for a non-behavioural requirement is not laundered into
    #: the numerator either -- the rule applies at both ends or it is not a rate.
    card2 = S.score(
        oracles=[_check("R1"), _check("R2")],
        normalized=[_form("R1", ["busy"]), _form("R2", ["al"])],
        requirements=[_req("R1"), _req("R2", "interface")],
        stimulus_by_tp={}, contract={"io": []}, population=[])
    assert card2.trusted == 1 and card2.span == 1.0, card2


def test_span_falls_back_to_the_observable_forms_and_says_so():
    """A caller with no requirements -- an artifact predating `unit_kind`, or a
    driver that did not load them -- gets the weaker denominator and a note
    saying which one it got. Silently changing what a rate means is the defect
    this module exists to remove."""
    card = S.score(
        oracles=[_check("R1")],
        normalized=[_form("R1", ["busy"]), _form("R2", [])],
        stimulus_by_tp={}, contract={"io": []}, population=[])
    assert card.requirements_behavioural == 0
    assert card.span == 1.0, card
    assert any("falls back" in n for n in card.notes), card.notes


def test_a_span_of_text_with_no_observable_obligation_is_in_NEITHER_end():
    """`normalize` returns `observable: []` with an `unobservable_reason` for a
    heading or a list marker -- "This span is scaffolding rather than a
    standalone requirement". On the probe run that is 16 of 151 and all sixteen
    were abandoned: not one carried a check and none ever could.

    Dividing by them reports the specification's typography as a verification
    gap. The rule has to apply to the numerator too, or it is not a rate.
    """
    card = S.score(
        oracles=[_check("R1"), _check("R3")],
        normalized=[_form("R1", ["busy"]), _form("R2", []), _form("R3", ["al"])],
        stimulus_by_tp={}, contract={"io": []}, population=[])
    assert card.requirements_minted == 3
    assert card.requirements_observable == 2
    assert card.trusted == 2
    assert card.span == 1.0, card

    #: A check written for a no-observable requirement is not laundered into
    #: the numerator either.
    card2 = S.score(
        oracles=[_check("R1"), _check("R2")],
        normalized=[_form("R1", ["busy"]), _form("R2", [])],
        stimulus_by_tp={}, contract={"io": []}, population=[])
    assert card2.trusted == 1 and card2.span == 1.0, card2


def test_an_absent_figure_is_absent_and_never_zero():
    """A run with no control has no audit figure, and a run with fewer than two
    designs has no blindness figure. Reporting 0.0% there is the class of
    number this tree has retracted twice -- and it is the flattering direction
    in both cases, which is exactly why it has to be impossible."""
    card = S.score(oracles=[], normalized=[_form("R1", ["busy"])],
                   stimulus_by_tp={}, contract={"io": []}, population=[])
    assert card.audit is None, "no control is not audit 0%"
    assert card.blindness is None, "no population is not blindness 0%"
    assert any("not 0%" in n for n in card.notes), card.notes
    assert any("rather than as 0%" in n for n in card.notes), card.notes


def test_meets_is_a_conjunction_and_an_absent_figure_does_not_pass_it():
    """Two of the three is the shape of every claim this project has had to
    withdraw, and an absent third is the easiest way to produce one."""
    good = S.Scorecard(span=0.95, blindness=0.05, audit=0.0)
    assert good.meets(span=0.9, blindness=0.1, audit=0.0)

    for missing in ("span", "blindness", "audit"):
        card = S.Scorecard(**{**{"span": 0.95, "blindness": 0.05, "audit": 0.0},
                              missing: None})
        assert not card.meets(span=0.9, blindness=0.1, audit=0.0), missing

    assert not S.Scorecard(span=0.90, blindness=0.05, audit=0.0).meets(
        span=0.9, blindness=0.1, audit=0.0), "span must be strictly greater"
    assert not S.Scorecard(span=0.95, blindness=0.10, audit=0.0).meets(
        span=0.9, blindness=0.1, audit=0.0), "blindness must be strictly less"
    assert not S.Scorecard(span=0.95, blindness=0.05, audit=0.01).meets(
        span=0.9, blindness=0.1, audit=0.0), "audit must be at most the target"


def test_the_audit_control_reaches_the_scorecard_and_NOTHING_ELSE():
    """A control may REJECT an oracle and may never REPAIR one.

    `audit_control` is a separate parameter from `refmodel_control` so that the
    non-leak is structural rather than remembered: it must appear in the
    `scorecard.score(...)` call and must not appear in the `run_oracle_stage`
    call, which is the one with an author and a repair path behind it.

    A source-level pin because the call site is inside `build_artifacts`, and
    a call site there has twice been deleted on this branch without failing a
    single behavioural test.
    """
    from specflow import integration

    src = inspect.getsource(integration.build_artifacts)
    stage = re.search(r"oracle_set = run_oracle_stage\((.*?)\n        \)", src,
                      re.S)
    assert stage, "cannot find the run_oracle_stage call"
    assert "audit_control" not in stage.group(1), (
        "the control reached the oracle stage, which can act on it")

    card = re.search(r"_scorecard\.score\((.*?)\n        \)", src, re.S)
    assert card, "cannot find the scorecard.score call"
    assert "audit_control=audit_control" in card.group(1), card.group(1)
    assert "_scorecard.write(run_dir, card)" in src
    #: AND THE REQUIREMENTS, or span silently falls back to the weaker
    #: denominator on every real run while the tests keep passing on the
    #: stronger one.
    assert "requirements=list(reqs" in card.group(1), card.group(1)


def test_blindness_is_scored_against_the_population_the_RUN_built():
    """`_population_on_disk` reads back `specflow/population/*.py`.

    Scoring against a yardstick a driver picked afterwards is how the probe run
    came to be measured by nine designs that declare no probes, while 82 of its
    96 checks read one -- so 16 of 96 decided and the triple was taken over a
    sixth of the set, selected by not using the feature the run added.
    """
    from specflow.integration import _population_on_disk

    src = inspect.getsource(_population_on_disk)
    assert 'specflow" / "population"' in src, src
    body = inspect.getsource(
        __import__("specflow.integration", fromlist=["x"]).build_artifacts)
    #: Computed once and handed to BOTH the cover and the scorecard, so the set
    #: the run ships is cut against the same designs its card is scored on.
    assert "_population = list(_population_on_disk(run_dir) or population_sources)" \
        in body, "the scorecard must prefer the run's own population"
    assert "population=_population," in body
    assert "_ship_cover(run_dir, _scored, _population," in body


def test_a_population_that_agrees_everywhere_is_NAMED_not_reported_as_absent(
        monkeypatch):
    """**SEVEN DESIGNS AND ZERO DISAGREEMENT IS A BROKEN INPUT, NOT A CLEAN
    MEASUREMENT.** There was a note for "fewer than two is not a population"
    and none for a population of seven that disagrees nowhere, so the card
    printed `population 7` and `0/0 cells = n/a` on adjacent lines and remarked
    on neither.

    Measured on the run that found it: a resumed run replayed ONE recorded
    witness for all seven members -- `ResumePort` is keyed by `(stage,
    round_)` and `conforming_implementation` passes `stage=WITNESS_STAGE` for
    every member -- and wrote seven byte-identical files, 8748 bytes, one
    distinct md5. A span of 94.2% and an audit of 1/12 were then published over
    an instrument that had silently become a constant.
    """
    from specflow import oracles_stage as O
    from specflow import scorecard as SC
    from specflow import variety as V

    monkeypatch.setattr(O, "_population_rows",
                        lambda *a, **k: {str(i): {} for i in range(7)})
    monkeypatch.setattr(O, "_population_tables", lambda *a, **k: ({}, {}, {}))
    monkeypatch.setattr(V, "cells", lambda *a, **k: ())

    same = "def step(self, i):\n    return {}\n"
    card = SC.score(
        oracles=[], normalized=[], stimulus_by_tp={},
        contract={"module_name": "m", "io": [{"name": "q", "dir": "output"}]},
        population=[same] * 7, requirements=[])
    assert card.blindness is None, "blindness cannot have a denominator here"
    joined = " ".join(card.notes)
    assert "disagree NOWHERE" in joined, (
        "a degenerate population was reported as an ordinary absent blindness")
    assert "1 distinct source(s) among 7" in joined, (
        "the note does not name what makes it degenerate")
