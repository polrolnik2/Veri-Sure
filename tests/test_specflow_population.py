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
from dataclasses import replace
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


def test_a_gated_verdict_carries_no_conviction_evidence():
    #: **THE INVARIANT THAT MAKES THE CLONE GUARD SAFE**, pinned directly
    #: because the filter written to enforce it was dead code -- the gate leg
    #: `continue`s before `convictions` runs, so a gated verdict can never move
    #: either term. A filter for it survived its own mutation, which is how the
    #: deadness was found.
    got = P.select({"k": convicts(0), "g": convicts(3), **SPLITS}, POP,
                   gate=lambda key: "malformed" if key == "g" else None)
    gated = [v for v in got.dropped if v.key == "g"][0]
    assert gated.reason == "gate"
    assert (gated.decided, gated.convicts) == (0, 0)


def test_a_population_whose_only_splitter_is_gated_is_refused():
    #: With the splitter gated, nothing that reached the population split it,
    #: so the corpus cannot tell a real population from N copies of one design.
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


# --------------------------------------------------------- B2: characterise

def _pair(a_vals, b_vals, *names):
    """designs -> testpoint -> rows, from per-design output sequences."""
    return {n: {f"t{i}": [{"outputs": {"a": v}, "inputs": {}}]
                for i, v in enumerate(vals)}
            for n, vals in zip(names, (a_vals, b_vals))}


def test_characterise_finds_the_split_and_the_dissent():
    #: E is off the majority at t1; everyone agrees at t0.
    pop = {d: {"t0": [{"outputs": {"a": 0}}], "t1": [{"outputs": {"a": 0}}]}
           for d in "ABCD"}
    pop["E"] = {"t0": [{"outputs": {"a": 0}}], "t1": [{"outputs": {"a": 9}}]}
    shape = P.characterise(pop, ["a"])
    assert shape.split == frozenset({"t1"})
    assert shape.dissent["E"] == 1.0
    assert all(shape.dissent[d] == 0.0 for d in "ABCD")


def test_characterise_collapses_clones_into_one_opinion():
    pop = {d: {"t0": [{"outputs": {"a": 0}}], "t1": [{"outputs": {"a": 0}}]}
           for d in "ABCD"}
    pop["E"] = {"t0": [{"outputs": {"a": 0}}], "t1": [{"outputs": {"a": 9}}]}
    shape = P.characterise(pop, ["a"])
    assert len(shape.designs) == 5
    #: A-D behave identically, so they are one opinion, not four
    assert shape.effective_size() == 2
    assert len({shape.cluster[d] for d in "ABCD"}) == 1


def test_characterise_refuses_a_population_that_never_disagrees():
    pop = {d: {"t0": [{"outputs": {"a": 0}}]} for d in "ABCDE"}
    with pytest.raises(ValueError, match="behaviourally indistinguishable"):
        P.characterise(pop, ["a"])


def test_the_b2_gate_refuses_a_population_one_design_dominates():
    #: k1's shape: one design off the majority almost everywhere. The rule's
    #: precision there is that design, and every subset auditing at exactly
    #: zero contained it.
    shape = P.PopulationShape(
        designs=tuple("ABCDG"), testpoints=("t0", "t1"),
        split=frozenset({"t0", "t1"}),
        dissent={"A": 0.1, "B": 0.1, "C": 0.1, "D": 0.1, "G": 0.86},
        cluster={"A": 0, "B": 1, "C": 2, "D": 3, "G": 4},
        pairs={"t0": (("A", "G"),)})
    with pytest.raises(ValueError, match="off the population majority"):
        P.refuse_unusable_population(shape)
    #: and it accepts the same population once the outlier is not dominant
    ok = replace(shape, dissent={**shape.dissent, "G": 0.2})
    P.refuse_unusable_population(ok)


def test_the_b2_gate_puts_the_floor_on_EFFECTIVE_size_not_headcount():
    #: Five designs, one opinion four times over. MIN_POPULATION counts
    #: designs; four one-per-cluster reached 1.5% where seven reached 0%.
    shape = P.PopulationShape(
        designs=tuple("ABCDE"), testpoints=("t0",), split=frozenset({"t0"}),
        dissent=dict.fromkeys("ABCDE", 0.1),
        cluster={"A": 0, "B": 0, "C": 0, "D": 0, "E": 1},
        pairs={"t0": (("A", "E"),)})
    assert len(shape.designs) == 5
    with pytest.raises(ValueError, match="distinct opinion"):
        P.refuse_unusable_population(shape)


# ------------------------------------------------- A3: the corpus gate set

def test_the_corpus_path_drops_correspondence_and_keeps_liveness():
    legs = P.GateLegs.corpus_path()
    #: the expensive judge that produced 147 of 149 ORACLE_INVALID
    assert legs.correspondence is False
    #: the free floors, both of which the threshold rule needs
    assert legs.well_formed is True and legs.liveness is True
    #: and the shipping path is unchanged -- this is a corpus configuration,
    #: not a weakening of what ships
    assert P.GateLegs.shipping_path() == P.GateLegs()
    assert P.GateLegs.shipping_path().correspondence is True


# ------------------------------------------------------- B1: the producer

def test_the_producer_asks_each_author_in_isolation():
    """**THE ISOLATION IS THE SIGNATURE.** An author receives the index, the
    spec and the contract; there is no parameter through which another design
    could reach it. A producer that passed the accumulating population to each
    author would make every member after the first a reaction to the ones
    before, and the rule's premise is that they are independent readings.
    """
    seen = []

    def author(i, spec, contract):
        seen.append((i, spec, sorted(contract)))
        return f"module m; // {i}\nendmodule"

    got = P.produce_population(author, spec="the spec", contract={"io": []},
                               size=5)
    assert len(got.designs) == 5 and got.asked == 5
    assert [i for i, _, _ in seen] == [0, 1, 2, 3, 4]
    #: every call saw the SAME inputs -- nothing accumulated between them
    assert {(s, tuple(c)) for _, s, c in seen} == {("the spec", ("io",))}
    #: and the signature cannot carry a design or a reference
    params = set(inspect.signature(P.produce_population).parameters)
    assert params == {"author", "spec", "contract", "size"}


def test_the_producer_refuses_a_pile_of_identical_designs():
    with pytest.raises(ValueError, match="one opinion repeated"):
        P.produce_population(lambda i, s, c: "module m; endmodule",
                             spec="s", contract={"io": []}, size=5)


def test_an_author_returning_nothing_is_refused_not_skipped():
    """A population silently short of its size is how a headcount stops
    matching the rate computed from it."""
    def flaky(i, spec, contract):
        return "" if i == 2 else f"module m; // {i}\nendmodule"

    with pytest.raises(ValueError, match="author 2 returned nothing"):
        P.produce_population(flaky, spec="s", contract={"io": []}, size=5)


def test_the_producer_does_not_claim_independence_only_isolation():
    """Authors served by one model from one prompt are correlated however
    carefully they are isolated. The docstring has to say so, because the
    measured consequence -- one design off the majority at 86% of split
    testpoints -- is what retracted this module's headline result."""
    doc = P.produce_population.__doc__ or ""
    assert "It does\n    not guarantee independence" in doc or "not guarantee independence" in doc
    assert "86%" in doc
    #: and it says where the trace half is, rather than implying it is here
    assert "TRACE HALF IS NOT HERE" in doc


def test_clustering_separates_designs_that_dissent_together_but_differ():
    """Off-majority TOGETHER is not the same design. F3 found this live.

    `characterise` used to cluster on the off-majority signature -- the set of
    testpoints where a design sits off the population majority -- while its own
    rationale quoted PAIR DISTANCES. On k1 the two agreed and the substitution
    was invisible. On i2c's five designs they diverge completely: d0 and d2 are
    off the majority at largely the same testpoints while disagreeing with each
    other on 65.6% of them, and single-link chaining collapsed all five into one
    cluster -- `effective_size` 1 for a population that differs everywhere.

    Here X and Y are off the majority at EVERY testpoint, so their signatures
    are identical, and they disagree with each other at every testpoint too. A
    signature metric merges them; a pair-distance metric must not.
    """
    from specflow.population import characterise

    tps = [f"TP-{i:04d}" for i in range(8)]

    def rows(value):
        return {tp: [{"outputs": {"o": value}, "inputs": {}}] for tp in tps}

    shape = characterise(
        {"P": rows(0), "Q": rows(0), "X": rows(1), "Y": rows(2)}, ["o"])
    #: P and Q are genuine clones and collapse; X and Y are two opinions
    assert shape.cluster["P"] == shape.cluster["Q"]
    assert shape.cluster["X"] != shape.cluster["Y"]
    assert shape.cluster["X"] != shape.cluster["P"]
    assert shape.effective_size() == 3, (
        "X and Y share an off-majority signature but disagree with each other "
        "at every testpoint; merging them is the defect F3 surfaced")


def test_the_liveness_finding_reports_both_modules_and_names_the_cause():
    from specflow.population import (
        liveness_is_measured_against_the_witness_and_is_wrong_on_both_modules as f,
    )
    text = f()
    #: BOTH modules, so the pre-registration is decided rather than illustrated
    assert "12.5%" in text and "28.7%" in text
    assert "k1-dcfsm" in text and "c1-i2c" in text
    #: the cause is the evidence the instrument reads, not its threshold
    assert "replays the WITNESS" in text
    assert "THE CAUSE IS THE EVIDENCE, NOT THE THRESHOLD" in text
    #: and the structural half: the blocking leg cannot see the class
    assert "structurally outside" in text
    assert "DEAD_ORACLE" in text and "UNKNOWN" in text
