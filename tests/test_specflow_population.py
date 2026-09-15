"""The merged population selector, and the invariants that make it trustworthy.

Two implementations of one rule were merged back into this module. This file
carries the FIRST one's guarantees, because those are what the second dropped:
the population floor, the vacuous-threshold refusal, the clone guard, the
partition invariant, the parameter-bound summary, and the distinction between a
check that was SILENT and a check that RAISED. Each is written against
behaviour, and each boundary is pinned on both sides.

An earlier version of this file passed while five of its eleven tests survived
removal of the behaviour they named -- the reject rule tolerated `> threshold+2`,
the "cannot reach a known-good design" test grepped for the literal "golden", and
the "no bare rate" test consulted a hardcoded blocklist of attribute names.
"""

import ast
import inspect
from pathlib import Path

import pytest

from specflow import population as P
from specflow.refmodel.oracles import RequirementOracle

TPS = ["TP-0000"]
ON_X = "def decide(trace):\n    return (trace[0]['outputs']['x'] == 0, 0, 'x')\n"


def _rows(x, s):
    return lambda tp: [{"edge": 0, "held": 1, "inputs": {},
                        "outputs": {"x": x, "s": s}}]


def _pop(convicting: int, total: int = 7):
    """`convicting` designs carry x=1; the first three carry s=1."""
    return {f"d{i}": _rows(1 if i < convicting else 0, 1 if i < 3 else 0)
            for i in range(total)}


def rows(v):
    return [{"outputs": {"a": v}, "inputs": {}}]


#: Seven designs, matching the measured population's size.
POP = [rows(i) for i in range(7)]


def convicts(n):
    """Convicts the first `n` designs and decides on all of them."""
    return lambda r: r[0]["outputs"]["a"] < n


def silent(r):
    return None


def raises(r):
    raise RuntimeError("boom")


#: A check that convicts SOME of the population, so the clone guard -- which
#: refuses a corpus in which every check convicts 0 or N -- is exercised rather
#: than tripped by a fixture too degenerate to carry the rule.
SPLITS = {"splits": convicts(3)}


def sel(corpus, **kw):
    return P.select({**corpus, **SPLITS}, POP, ruleset=P.Ruleset(**kw))


# ---------------------------------------------------------------- the rule

@pytest.mark.parametrize("n,kept", [(0, True), (1, True), (2, True),
                                    (3, False), (4, False),
                                    (5, False), (6, False)])
def test_the_reject_boundary_is_pinned_on_both_sides(n, kept):
    #: The earlier file tested only 5 and 6, so `> t` could be inflated to
    #: `> t + 2` with every test still green. Sweeping the range pins it.
    got = sel({"k": convicts(n)}, max_convictions=2)
    assert ("k" in got.kept) is kept
    if not kept:
        assert [v for v in got.dropped if v.key == "k"][0].reason == "over_strict"


def test_a_check_that_never_decides_is_rejected_for_silence():
    #: THE LOAD-BEARING ONE. A silent check convicts nobody, so a rule written
    #: as "convicts few" KEEPS it -- sound by silence rather than by evidence.
    got = sel({"s": silent})
    assert "s" not in got.kept
    assert [v for v in got.dropped if v.key == "s"][0].reason == "silent"


def test_a_check_that_raises_everywhere_is_not_called_silent():
    #: A check that crashes is a defect in the CHECK; a check that ran and found
    #: no occasion to speak is a fact about the stimulus. The second
    #: implementation folded them and a body crashing on every design read as
    #: "sound, convicts nobody", which the rule at low `t` keeps.
    got = sel({"b": raises})
    dropped = [v for v in got.dropped if v.key == "b"][0]
    assert dropped.reason == "broken"
    assert "raised on all 7" in dropped.detail


def test_convictions_reports_all_three_facts_separately():
    assert P.convictions(convicts(3), POP) == (3, 7, 0)
    assert P.convictions(silent, POP) == (0, 0, 0)
    assert P.convictions(raises, POP) == (0, 0, 7)


def test_the_conviction_count_carries_its_denominator():
    oracle = RequirementOracle(req_uid="REQ-0001", clause="", source=ON_X,
                               tp_uids=TPS)
    got = P.conviction(oracle, _pop(3), TPS)
    assert (got.decides, got.convicts, got.population) == (True, 3, 7)


# -------------------------------------------------------------- partition

def test_the_halves_always_partition_the_corpus():
    got = sel({"a": convicts(0), "b": convicts(6), "c": silent})
    assert len(got.kept) + len(got.dropped) == len(got.verdicts)


def test_duplicate_verdict_keys_cannot_be_constructed():
    #: Found by verification: a repeated key made one rejection vanish, or put
    #: a key in BOTH halves, while `summary()` still read plausibly.
    with pytest.raises(ValueError, match="duplicate keys"):
        P.Selection(P.Ruleset(), (P.Verdict("a", True), P.Verdict("a", False)), 7)


def test_by_reason_actually_counts_and_does_not_merely_mark():
    #: The earlier version expected every count to be 1, so replacing the
    #: increment with `= 1` passed -- the method's entire purpose untested.
    #: max_convictions=3 so the splitter itself is KEPT and does not add a
    #: fourth over_strict, which would make "3" pass for the wrong reason.
    got = sel({f"r{i}": convicts(6) for i in range(3)}
              | {f"s{i}": silent for i in range(2)}, max_convictions=3)
    assert got.by_reason()["over_strict"] == 3
    assert got.by_reason()["silent"] == 2


# --------------------------------------------------------------- refusals

def test_it_refuses_a_population_too_small_to_be_a_consensus():
    with pytest.raises(ValueError, match="independently written designs"):
        P.select({"k": convicts(0)}, POP[:4])


def test_the_population_floor_is_a_parameter_a_caller_must_state():
    #: The concession belongs in the call, not in a comment. Four designs pass
    #: only when the caller says four is enough.
    got = P.select({"k": convicts(0), **SPLITS}, POP[:4],
                   ruleset=P.Ruleset(min_population=4))
    assert got.kept == ("k",)


def test_it_refuses_a_threshold_that_rejects_nothing():
    with pytest.raises(ValueError, match="rejects nothing"):
        sel({"k": convicts(0)}, max_convictions=7)


def test_the_sweep_may_report_the_endpoint_the_rule_refuses():
    #: `t = N` is the whole corpus -- what every other bucket is measured
    #: against -- so the sweep states the exemption rather than the refusal
    #: being quietly absent.
    sets = P.sweep({"k": convicts(0), **SPLITS}, POP)
    assert len(sets) == len(POP) + 1
    assert sets[-1].ruleset.allow_vacuous_threshold is True
    assert sets[0].ruleset.allow_vacuous_threshold is False


def test_it_refuses_a_negative_threshold():
    #: Untested before: deleting the guard left every test green.
    with pytest.raises(ValueError, match="negative"):
        P.Ruleset(max_convictions=-1)


def test_it_refuses_an_empty_corpus():
    with pytest.raises(ValueError, match="not a selection"):
        P.select({}, POP)


def test_it_refuses_a_population_that_never_splits():
    #: The clone attack: pass ONE design under seven keys and the rule becomes
    #: a false-reject filter against it. The module cannot know WHICH designs a
    #: caller passed; it can see that no check found any disagreement, which is
    #: the shape N copies of one design take.
    clones = [rows(0) for _ in range(7)]
    with pytest.raises(ValueError, match="never split|indistinguishable"):
        P.select({"k": convicts(1)}, clones)


def test_a_gated_check_is_not_evidence_that_the_population_split():
    #: A gated check never consulted the population, so counting it made a
    #: corpus whose every member the gate rejected read as a cloned population.
    with pytest.raises(ValueError, match="never split|indistinguishable"):
        P.select({"k": convicts(0), "g": convicts(3)}, POP,
                 gate=lambda key: "malformed" if key == "g" else None)


# -------------------------------------------------------------- structural

def test_the_module_performs_no_io_at_all():
    #: Behaviour, not spelling. The earlier test grepped for "golden", so adding
    #: REFERENCE_DESIGN_PATH and a false_reject_rate() left it green.
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


def test_the_selector_cannot_import_the_scoring_module():
    #: THE SEPARATION IS THE IMPORT GRAPH, NOT THE DOCSTRING. `scoring` imports
    #: from here; a reverse edge would be a cycle, so wiring the audit into the
    #: selector becomes an ImportError rather than a review comment.
    tree = ast.parse(Path(P.__file__).read_text())
    imported = {
        (n.module or "") for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)
    } | {
        a.name for n in ast.walk(tree) if isinstance(n, ast.Import)
        for a in n.names
    }
    assert not any("scoring" in m for m in imported), imported


def test_no_public_surface_yields_a_bare_number():
    #: Return TYPES, not a blocklist of names -- adding `Selection.adequacy`
    #: returning a float passed the earlier version.
    got = sel({"k": convicts(1)})
    oracle = RequirementOracle(req_uid="REQ-0001", clause="", source=ON_X,
                               tp_uids=TPS)
    for obj in (got, P.conviction(oracle, _pop(1), TPS)):
        for name in dir(obj):
            if name.startswith("_"):
                continue
            value = getattr(obj, name)
            if callable(value) and not inspect.signature(value).parameters:
                value = value()
            assert not isinstance(value, float), f"{name} returns a bare rate"


def test_the_summary_cannot_omit_its_parameters():
    #: PRECISION IS PARAMETER-BOUND: the rule read 59 of 59 at threshold 2 of
    #: THIRTEEN designs over 259 bodies, and 66% at threshold 2 of NINE over
    #: 502. Same rule, different instruments.
    got = sel({"k": convicts(6)}, max_convictions=3)
    assert len(got.verdicts) == 2 and len(got.kept) == 1   # cannot be confused
    assert "1 of 2 kept" in got.summary()
    assert "convicts <= 3 of 7" in got.summary()
