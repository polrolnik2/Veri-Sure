"""The population selector, and the invariants that make it trustworthy.

An earlier version of this file passed while five of its eleven tests survived
removal of the behaviour they named -- the reject rule tolerated `> threshold+2`,
the "cannot reach a known-good design" test grepped for the literal "golden", and
the "no bare rate" test consulted a hardcoded blocklist of attribute names. Each
is now written against BEHAVIOUR, and the boundary is pinned on both sides.
"""

import ast
import inspect
from pathlib import Path

import pytest

from specflow import population as P
from specflow.refmodel.oracles import RequirementOracle

#: objects exactly when the design's `x` is 1 -- h is set by the population.
ON_X = "def decide(trace):\n    return (trace[0]['outputs']['x'] == 0, 0, 'x')\n"
#: objects on `s`, which three designs always carry, so this check always
#: SPLITS the population. Needed because a lone check at h=0 or h=N leaves the
#: population indistinguishable and `select` rightly refuses that.
ON_S = "def decide(trace):\n    return (trace[0]['outputs']['s'] == 0, 0, 's')\n"
SILENT = "def decide(trace):\n    return (None, None, 'never fired')\n"
RAISES = "def decide(trace):\n    raise RuntimeError('boom')\n"
TPS = ["TP-0000"]


def _rows(x, s):
    return lambda tp: [{"edge": 0, "held": 1, "inputs": {},
                        "outputs": {"x": x, "s": s}}]


def _pop(convicting: int, total: int = 7):
    return {f"d{i}": _rows(1 if i < convicting else 0, 1 if i < 3 else 0)
            for i in range(total)}


def _o(source=ON_X, uid="REQ-0001"):
    return RequirementOracle(req_uid=uid, clause="", source=source, tp_uids=TPS)


def _split():
    """A check that always splits, so the degenerate-population guard is quiet."""
    return ("splitter", _o(ON_S, "REQ-0009"))


def _select(convicting, threshold=2, extra=(), total=7):
    return P.select([_split(), ("k", _o())] + list(extra),
                    _pop(convicting, total), TPS, threshold=threshold)


# ---------------------------------------------------------------- the rule

@pytest.mark.parametrize("convicts,kept", [(0, True), (1, True), (2, True),
                                           (3, False), (4, False),
                                           (5, False), (6, False)])
def test_the_reject_boundary_is_pinned_on_both_sides(convicts, kept):
    # The earlier file tested only convicts 5 and 6, so `> threshold` could be
    # inflated to `> threshold + 2` with every test still green. Sweeping the
    # whole range pins the comparison exactly.
    got = _select(convicts)
    assert ("k" in got.kept) is kept
    if not kept:
        assert got.rejected["k"] == f"convicts {convicts} of 7"


def test_a_check_that_never_decides_is_rejected_for_silence():
    # THE LOAD-BEARING ONE. A silent check convicts nobody, so a rule written as
    # "convicts few" keeps it -- sound by silence rather than by evidence.
    got = _select(0, extra=[("s", _o(SILENT, "REQ-0002"))])
    assert "s" not in got.kept
    assert got.rejected["s"] == "decides nowhere"


def test_a_check_that_raises_everywhere_is_not_called_silent():
    # A check that crashes is a defect in the CHECK; a check that ran and found
    # no occasion to speak is a fact about the stimulus. Folding them loses the
    # distinction this project names in capitals one stage earlier.
    got = _select(0, extra=[("b", _o(RAISES, "REQ-0003"))])
    assert got.rejected["b"] == "broken on every design"


def test_the_conviction_count_carries_its_denominator():
    got = P.conviction(_o(), _pop(3), TPS)
    assert (got.decides, got.convicts, got.population) == (True, 3, 7)


# -------------------------------------------------------------- partition

def test_duplicate_keys_are_refused_rather_than_silently_merged():
    # Found by verification: with a dict for `rejected` and a counter for
    # `corpus`, a repeated key made one rejection vanish, or put a key in BOTH
    # halves, while `summary()` still read plausibly.
    with pytest.raises(ValueError, match="duplicate key"):
        P.select([_split(), ("k", _o()), ("k", _o(uid="REQ-0004"))],
                 _pop(5), TPS, threshold=2)


def test_the_halves_always_partition_the_corpus():
    got = _select(5)
    assert len(got.kept) + len(got.rejected) == got.corpus


def test_a_selection_that_does_not_partition_cannot_be_constructed():
    with pytest.raises(ValueError, match="do not partition"):
        P.Selection(threshold=2, population=7, corpus=3,
                    kept=("a",), rejected={"b": "x"})


def test_why_actually_counts_and_does_not_merely_mark():
    # The earlier version expected every count to be 1, so replacing the
    # increment with `= 1` passed -- why()'s entire stated purpose untested.
    #: threshold 3 so the splitter itself is KEPT and does not add a reason.
    got = P.select(
        [_split()] + [(f"r{i}", _o(uid=f"REQ-01{i}")) for i in range(3)]
        + [(f"s{i}", _o(SILENT, uid=f"REQ-02{i}")) for i in range(2)],
        _pop(6), TPS, threshold=3)
    assert got.why() == {"convicts 6 of 7": 3, "decides nowhere": 2}


# --------------------------------------------------------------- refusals

def test_it_refuses_a_population_too_small_to_be_a_consensus():
    with pytest.raises(ValueError, match="independently written designs"):
        P.select([("k", _o())], _pop(0, total=3), TPS, threshold=1)


def test_it_refuses_a_threshold_that_rejects_nothing():
    with pytest.raises(ValueError, match="rejects nothing"):
        P.select([("k", _o())], _pop(0), TPS, threshold=7)


def test_it_refuses_a_negative_threshold():
    # Untested before: deleting the guard left every test green.
    with pytest.raises(ValueError, match="negative"):
        P.select([("k", _o())], _pop(0), TPS, threshold=-1)


def test_it_refuses_an_empty_testpoint_list():
    with pytest.raises(ValueError, match="no testpoints"):
        P.select([("k", _o())], _pop(0), [], threshold=2)


def test_it_refuses_an_empty_corpus():
    with pytest.raises(ValueError, match="not a selection"):
        P.select([], _pop(0), TPS, threshold=2)


def test_it_refuses_a_population_that_never_splits():
    # The clone attack: pass ONE design under seven keys and the rule becomes a
    # false-reject filter against it. The module cannot know WHICH design a
    # caller passed; it can see that no check found any disagreement, which is
    # the shape N copies of one design take.
    clone = _rows(0, 0)
    with pytest.raises(ValueError, match="never split|indistinguishable"):
        P.select([("k", _o())], {f"d{i}": clone for i in range(7)},
                 TPS, threshold=0)


# -------------------------------------------------------------- structural

def test_the_module_performs_no_io_at_all():
    # Behaviour, not spelling. The earlier test grepped for "golden", so adding
    # REFERENCE_DESIGN_PATH and a false_reject_rate() left it green.
    tree = ast.parse(Path(P.__file__).read_text())
    banned = {"open", "read_text", "read_bytes", "loads", "load", "glob",
              "iterdir", "run", "getenv", "system", "Path"}
    hits = [
        n.func.attr if isinstance(n.func, ast.Attribute) else n.func.id
        for n in ast.walk(tree)
        if isinstance(n, ast.Call)
        and isinstance(n.func, (ast.Name, ast.Attribute))
        and (n.func.attr if isinstance(n.func, ast.Attribute) else n.func.id)
        in banned
    ]
    assert hits == [], f"the selector reaches the filesystem via {hits}"


def test_no_public_surface_yields_a_bare_number():
    # Return TYPES, not a blocklist of names -- adding `Selection.adequacy`
    # returning a float passed the earlier version.
    got = _select(1)
    for obj in (got, P.conviction(_o(), _pop(1), TPS)):
        for name in dir(obj):
            if name.startswith("_"):
                continue
            value = getattr(obj, name)
            if callable(value) and not inspect.signature(value).parameters:
                value = value()
            assert not isinstance(value, float), f"{name} returns a bare rate"


def test_the_summary_cannot_omit_its_parameters():
    # corpus and len(kept) differ here, so `{corpus} of {corpus}` cannot pass.
    got = _select(5, threshold=3)
    assert got.corpus == 2 and len(got.kept) == 1   # they cannot be confused
    assert "1 of 2 kept" in got.summary()
    assert "convicts <= 3 of 7" in got.summary()
