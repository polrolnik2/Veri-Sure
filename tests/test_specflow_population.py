"""The population selector, and the invariants that make it trustworthy.

Two of these are not about behaviour but about what the module CANNOT do: the
selector must not be able to read a known-good design, because the moment an
audit lives beside a selector somebody wires one into the other and the grade
stops being independent.
"""

from pathlib import Path

import pytest

from specflow import population as P
from specflow.refmodel.oracles import RequirementOracle

#: returns False -- objects -- exactly when the design's `x` is 1.
OBJECTS_ON_X = "def decide(trace):\n    return (trace[0]['outputs']['x'] == 0, 0, 'x')\n"
SILENT = "def decide(trace):\n    return (None, None, 'never fired')\n"
TPS = ["TP-0000"]


def _rows(x):
    return lambda tp: [{"edge": 0, "held": 1, "inputs": {}, "outputs": {"x": x}}]


def _pop(convicting: int, total: int = 7):
    """`convicting` designs drive x=1, the rest x=0."""
    return {f"d{i}": _rows(1 if i < convicting else 0) for i in range(total)}


def _oracle(source=OBJECTS_ON_X, uid="REQ-0001"):
    return RequirementOracle(req_uid=uid, clause="", source=source, tp_uids=TPS)


def test_a_check_that_never_decides_is_rejected_for_silence_not_kept_for_soundness():
    # THE LOAD-BEARING ONE. A silent check convicts nobody, so a rule written as
    # "convicts few" keeps it -- sound by silence rather than by evidence. The
    # DECIDES clause exists to stop that, and the reason must say so by name.
    got = P.select([("k", _oracle(SILENT))], _pop(0), TPS, threshold=2)
    assert got.kept == ()
    assert got.rejected["k"] == "decides nowhere"


def test_the_conviction_count_carries_its_denominator():
    # h alone is not a measurement; 3 of 7 and 3 of 13 are different facts.
    got = P.conviction(_oracle(), _pop(3), TPS)
    assert (got.decides, got.convicts, got.population) == (True, 3, 7)


def test_a_check_inside_the_threshold_is_kept():
    got = P.select([("k", _oracle())], _pop(2), TPS, threshold=2)
    assert got.kept == ("k",)
    assert got.rejected == {}


def test_a_check_over_the_threshold_is_rejected_and_the_reason_names_the_count():
    got = P.select([("k", _oracle())], _pop(5), TPS, threshold=2)
    assert got.kept == ()
    assert got.rejected["k"] == "convicts 5 of 7"


def test_the_summary_cannot_omit_its_parameters():
    # The rule reads 59 of 59 at t=2 of 13 on one corpus and 66% at t=2 of 9 on
    # another. A count without (threshold, population, corpus) is not quotable.
    got = P.select([("k", _oracle())], _pop(1), TPS, threshold=2)
    line = got.summary()
    assert "1 of 1 kept" in line
    assert "convicts <= 2 of 7" in line


def test_rejections_are_partitioned_by_cause():
    # A cause holding nearly all the mass is a defect in the instrument rather
    # than a finding about the corpus, and that is only visible if counted.
    got = P.select(
        [("silent", _oracle(SILENT, "REQ-0001")), ("over", _oracle(uid="REQ-0002"))],
        _pop(6),
        TPS,
        threshold=2,
    )
    assert got.why() == {"decides nowhere": 1, "convicts 6 of 7": 1}


def test_it_refuses_a_population_too_small_to_be_a_consensus():
    with pytest.raises(ValueError, match="independently written designs"):
        P.select([("k", _oracle())], _pop(0, total=3), TPS, threshold=1)


def test_it_refuses_a_threshold_that_rejects_nothing():
    # threshold == population makes the rule the DECIDES clause under a second
    # name, which would read as a working selector and select everything.
    with pytest.raises(ValueError, match="rejects nothing"):
        P.select([("k", _oracle())], _pop(0), TPS, threshold=7)


def test_it_refuses_an_empty_testpoint_list():
    with pytest.raises(ValueError, match="no testpoints"):
        P.select([("k", _oracle())], _pop(0), [], threshold=2)


def test_the_selector_cannot_reach_a_known_good_design():
    # Structural, not stylistic. Nothing in this module may read the grade.
    src = Path(P.__file__).read_text()
    assert "golden" not in src.lower()
    assert not [n for n in dir(P) if "audit" in n.lower()]


def test_no_accessor_yields_a_rate_without_its_parameters():
    got = P.select([("k", _oracle())], _pop(1), TPS, threshold=2)
    # every public field that could be read as a score carries its context
    assert got.threshold == 2 and got.population == 7 and got.corpus == 1
    assert not [n for n in dir(got) if n in {"rate", "precision", "score"}]
