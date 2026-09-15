"""Tests for the golden-free selection ruleset.

Each test pins a property the RESULT depends on, not merely a code path. Where
a rule claims to distinguish two things, it is shown returning both verdicts on
inputs differing only in the thing it claims to detect -- a filter that cannot
fail is worth nothing, which this project has now measured five times.
"""
import inspect

import pytest

from specflow.selection import (
    Blindness,
    Bucket,
    GateLegs,
    Report,
    Ruleset,
    PopulationShape,
    Selection,
    TellProfile,
    Verdict,
    audit,
    buckets,
    convictions,
    pipeline_gates,
    refutable,
    select,
    set_blindness,
    soundness_and_blindness_are_one_knob,
    sweep,
    tells,
    the_conviction_matrix_carries_one_signal_not_nine,
    the_gates_and_the_rule_reject_different_checks,
    two_tells_were_pre_registered_backwards,
)
from specflow.selection import (
    objection_placement_buys_closure_more_cheaply_than_the_count,
)


def rows(*vals):
    return [{"outputs": {"a": v}, "inputs": {}} for v in vals]


#: Four designs. `convicts(n)` builds a check objecting to the first n of them.
POP = [rows(0), rows(1), rows(2), rows(3)]


def convicts(n):
    """A check that convicts the first `n` designs and decides on all of them."""
    def decide_on(r):
        return r[0]["outputs"]["a"] < n
    return decide_on


def silent(r):
    """Never decides. Sound by silence, which is not soundness."""
    return None


# --------------------------------------------------------------------------
# THE STRUCTURAL GUARANTEE. This is the one that cannot be restored by reading
# a docstring later, so it is pinned first.
# --------------------------------------------------------------------------

def test_select_has_no_parameter_that_could_carry_a_reference():
    """The audit cannot leak into a selection because there is nowhere to put it.

    A docstring saying "golden-free" is worth nothing against a future caller
    with a reference in hand; a signature with no slot for one is worth
    something. `audit` is where the reference goes, and it takes a `Selection`
    that has already been built.
    """
    names = set(inspect.signature(select).parameters)
    assert not {"reference", "golden", "audit", "convicts_reference"} & names
    assert names == {"corpus", "population", "ruleset", "gate"}
    # And the built object carries no reference information either, so nothing
    # downstream can recover one from it.
    fields = set(Selection.__dataclass_fields__)
    assert fields == {"ruleset", "verdicts", "population_size"}


def test_the_ruleset_has_no_reference_field():
    """Every leg reads spec-derived designs or the check's own text."""
    assert set(Ruleset.__dataclass_fields__) == {
        "max_convictions", "min_decides", "use_gates"}


# --------------------------------------------------------------------------
# THE RULE ITSELF, at both ends of the knob.
# --------------------------------------------------------------------------

def test_the_threshold_keeps_exactly_the_checks_below_it():
    corpus = {f"c{n}": convicts(n) for n in range(5)}
    at_zero = select(corpus, POP, ruleset=Ruleset(max_convictions=0))
    assert at_zero.kept == ("c0",)
    at_two = select(corpus, POP, ruleset=Ruleset(max_convictions=2))
    assert at_two.kept == ("c0", "c1", "c2")
    # And the drop is attributed, not merely a count.
    dropped = {v.key: v for v in at_zero.dropped}
    assert dropped["c3"].reason == "over_strict"
    assert dropped["c3"].convicts == 3


def test_a_check_that_never_decides_is_dropped_not_kept():
    """SOUND MEANS DECIDES AND SPARES. Convicting nothing is the same NUMBER as
    sparing everything and a different FACT about the check.

    This is the conflation that put one extra check in a published adequacy
    count -- a body deciding 0 testpoints on the reference and 1 on a held-out
    design, scored sound by silence.
    """
    corpus = {"good": convicts(0), "silent": silent}
    kept = select(corpus, POP).kept
    assert kept == ("good",)
    #: And it must be the DECIDES leg doing it, not the threshold: a silent
    #: check convicts zero, so the threshold alone would keep it.
    hits, decided = convictions(silent, POP)
    assert (hits, decided) == (0, 0)
    loose = select(corpus, POP, ruleset=Ruleset(min_decides=0))
    assert set(loose.kept) == {"good", "silent"}


def test_the_drop_reason_distinguishes_silence_from_over_strictness():
    """They demand opposite work, so one reason code for both would be a defect."""
    corpus = {"silent": silent, "strict": convicts(4)}
    by_reason = select(corpus, POP).by_reason()
    assert by_reason == {"silent": 1, "over_strict": 1}


# --------------------------------------------------------------------------
# THE REFUTABLE LEG. Report with it; never select with it.
# --------------------------------------------------------------------------

def test_select_keeps_a_check_that_refutes_nothing():
    """The population may simply be RIGHT, and dropping such a check discarded
    21% of the entire measured yield when it was tried as a selection leg.
    """
    corpus = {"spares_all": convicts(0)}
    assert select(corpus, POP).kept == ("spares_all",)
    #: The same check, asked the refutable question with no mutant to catch,
    #: fails it -- so the leg WOULD have dropped it and `select` does not.
    assert refutable(convicts(0), POP, []) is False


def test_refutable_separates_a_dead_check_from_a_sparing_one():
    mutant = rows(9)
    catches_mutant = lambda r: r[0]["outputs"]["a"] == 9  # noqa: E731
    assert refutable(catches_mutant, POP, [mutant]) is True
    assert refutable(convicts(0), POP, [mutant]) is False
    #: And a check convicting the population is refused whatever it does to a
    #: mutant -- the first leg is "spares every candidate".
    assert refutable(convicts(4), POP, [mutant]) is False


# --------------------------------------------------------------------------
# COMPLETENESS.
# --------------------------------------------------------------------------

#: A disagrees with B; A is the one the reference contradicts.
BY_DESIGN = {"A": {"tp": rows(0)}, "B": {"tp": rows(1)}}
DIFFER = lambda a, b: a[0]["outputs"]["a"] != b[0]["outputs"]["a"]  # noqa: E731
A_IS_WRONG = lambda a, b, tp: {"A"}  # noqa: E731
B_IS_WRONG = lambda a, b, tp: {"B"}  # noqa: E731


def test_set_blindness_reads_zero_and_one_on_the_two_extremes():
    blind_to_all = set_blindness([convicts(0)], BY_DESIGN,
                                 differ=DIFFER, wrong=A_IS_WRONG)
    assert (blind_to_all.blind, blind_to_all.disagreements) == (1, 1)
    assert blind_to_all.rate == 1.0
    #: `convicts(1)` objects to A only, and A is the wrong one -> a TRUE catch.
    sees_it = set_blindness([convicts(1)], BY_DESIGN,
                            differ=DIFFER, wrong=A_IS_WRONG)
    assert (sees_it.blind, sees_it.rate, sees_it.spurious) == (0, 0.0, 0)


def test_objecting_to_the_CORRECT_design_is_not_coverage():
    """The defect the polarity check removes. The same check, the same cell,
    the same objection -- only which design the reference contradicts differs.
    """
    #: `convicts(1)` objects to A. When B is the wrong one, that objection is a
    #: FALSE REJECTION, and the cell stays blind.
    got = set_blindness([convicts(1)], BY_DESIGN, differ=DIFFER, wrong=B_IS_WRONG)
    assert got.blind == 1, "objecting to the correct design is not coverage"
    assert got.spurious == 1
    assert got.rate == 1.0
    #: It is still reported as apparent closure, so the two can be compared.
    assert got.apparent == 1
    assert got.spurious_rate == 1.0


def test_the_reference_is_required_so_the_flattering_number_cannot_be_taken():
    """A caller without a reference gets a TypeError, not a number.

    Blindness without the polarity check is a rebadged objection count. Offering
    it as a default is the defect; refusing is the fix.
    """
    with pytest.raises(TypeError):
        set_blindness([convicts(1)], BY_DESIGN, differ=DIFFER)
    names = inspect.signature(set_blindness).parameters
    assert names["wrong"].default is inspect.Parameter.empty


def test_blindness_counts_only_cells_where_the_designs_disagree():
    """A cell the population agrees on is not a disagreement the set failed to
    see, so counting it would make an agreeing population look like a blind set.
    """
    by_design = {"A": {"tp": rows(0)}, "B": {"tp": rows(0)}}
    got = set_blindness([convicts(0)], by_design,
                        differ=DIFFER, wrong=A_IS_WRONG)
    assert got.disagreements == 0
    assert got.rate == 0.0  # no cells is not "blind to everything"


def test_the_selected_set_at_zero_is_blind_by_construction():
    """The finding this module exists to stop anyone rediscovering: the rule
    that predicts soundness and the rule that selects blindness are ONE
    predicate read twice.
    """
    corpus = {f"c{n}": convicts(n) for n in range(5)}
    chosen = select(corpus, POP, ruleset=Ruleset(max_convictions=0))
    got = set_blindness([corpus[k] for k in chosen.kept], BY_DESIGN,
                        differ=DIFFER, wrong=A_IS_WRONG)
    assert got.rate == 1.0, "a set convicting none of the population sees none of it"


# --------------------------------------------------------------------------
# THE SWEEP, and the correction the curve made to the two-point argument.
# --------------------------------------------------------------------------

def test_the_thresholds_nest_so_the_counts_carry_no_information():
    """Monotonicity here is a property of the CONSTRUCTION. Pinned so nobody
    reports it as a trend -- which is what the first version of the sweep
    finding did.
    """
    corpus = {f"c{n}": convicts(n) for n in range(5)}
    sets = [set(s.kept) for s in sweep(corpus, POP)]
    for tighter, looser in zip(sets, sets[1:]):
        assert tighter <= looser
    assert len(sets) == len(POP) + 1


def test_buckets_decompose_where_the_cumulative_table_cannot():
    corpus = {f"c{n}": convicts(n) for n in range(5)}
    assert buckets(corpus, POP) == (
        Bucket(0, 1), Bucket(1, 1), Bucket(2, 1), Bucket(3, 1), Bucket(4, 1))
    #: A silent check is in no bucket: it has no conviction count that means
    #: anything, and putting it in bucket 0 would inflate the one end the rule
    #: is measured exact at.
    assert buckets({"silent": silent}, POP) == ()


# --------------------------------------------------------------------------
# REPORTING. A span and its audit are one result.
# --------------------------------------------------------------------------

def test_a_report_cannot_be_built_without_its_audit():
    """Nine headlines on this work were retracted for quoting reach without the
    false-reject rate. The type is where that is stopped.
    """
    with pytest.raises(TypeError):
        Report(checks=10, requirements=8, of_requirements=20)  # no audit


def test_audit_is_computed_over_an_already_built_selection():
    corpus = {"a": convicts(0), "b": convicts(1)}
    chosen = select(corpus, POP, ruleset=Ruleset(max_convictions=1))
    report = audit(
        chosen, lambda k: k == "b",
        requirement_of=lambda k: f"REQ-{k}", of_requirements=4)
    assert (report.checks, report.requirements) == (2, 2)
    assert report.convicts_reference == 1
    assert report.false_reject == 0.5
    assert report.span == 0.5
    #: And the selection it scored is unchanged -- the audit feeds nothing back.
    assert chosen.kept == ("a", "b")


def test_the_report_string_always_carries_both_halves():
    line = str(Report(checks=126, requirements=55, of_requirements=87,
                      convicts_reference=0, blindness=Blindness(5646, 5656, 12)))
    assert "126 checks" in line and "63%" in line
    assert "audit" in line and "0.0%" in line
    assert "99.8% blind" in line


# --------------------------------------------------------------------------
# THE SHIPPED GATES, composed as the first leg.
# --------------------------------------------------------------------------

def test_a_missing_body_is_dropped_and_never_read_as_a_pass():
    """A key with no body is a missing artifact. Reading it as a check that
    passed is how a dropped body became a silent acceptance once already.
    """
    gate = pipeline_gates({}, {"io": []}, [])
    assert gate("nothing-here") == "no body for this key"


def test_a_gate_rejection_is_attributed_to_the_gate_leg():
    corpus = {"bad": convicts(0), "good": convicts(0)}
    chosen = select(corpus, POP, gate=lambda k: "malformed: no source"
                    if k == "bad" else None)
    assert chosen.kept == ("good",)
    dropped = chosen.dropped[0]
    assert dropped.reason == "gate" and "no source" in dropped.detail


def test_the_gate_runs_before_the_population_is_replayed():
    """A malformed body has no meaningful conviction count, and letting it score
    one spends the population's evidence on a body that cannot be used.
    """
    seen = []

    def counting(r):
        seen.append(r)
        return False

    select({"bad": counting}, POP, gate=lambda k: "malformed: no source")
    assert seen == []


def test_gates_can_be_switched_off_for_a_priced_comparison():
    chosen = select({"bad": convicts(0)}, POP,
                    ruleset=Ruleset(use_gates=False),
                    gate=lambda k: "malformed: no source")
    assert chosen.kept == ("bad",)


def test_liveness_is_on_because_dead_oracle_is_a_floor_not_a_gradient():
    """It was defaulted OFF here on the argument that it pulls against the rule.
    That describes a gradient; `DEAD_ORACLE` fires only when NO legal value of
    any port the check reads moves its verdict anywhere -- a constant function,
    which is the class this rule selects for hardest.
    """
    assert GateLegs().liveness is True
    assert GateLegs().well_formed is True
    assert GateLegs().vacuity is True


def test_not_assertable_does_not_shrink_the_span_by_default():
    """It accuses the SPECIFICATION, so dropping the check removes a requirement
    from the denominator on a judge's say-so -- measured at 12 of 12 such
    verdicts being checks that simply never fired.
    """
    names = inspect.signature(pipeline_gates).parameters
    assert names["drop_not_assertable"].default is False


def test_a_negative_threshold_is_refused():
    with pytest.raises(ValueError, match="negative"):
        Ruleset(max_convictions=-1)


# --------------------------------------------------------------------------
# THE FINDINGS, pinned so an edit that drops the correction fails.
# --------------------------------------------------------------------------

def test_the_knob_finding_states_both_directions_and_the_off_curve_set():
    text = soundness_and_blindness_are_one_knob()
    assert "ONE KNOB" in text
    assert "BLINDNESS FALLS AND THE AUDIT RISES" in text
    # The part that makes it actionable rather than a shrug: the
    # reference-selected set is unreachable by any threshold.
    assert "OFF THE CURVE" in text
    assert "nothing sound replaces them" in text


def test_the_gate_finding_states_why_the_gates_run_first():
    text = the_gates_and_the_rule_reject_different_checks()
    assert "dead body is the cheapest way to convict nobody" in text
    # And that composing them is not what makes the set golden-free.
    assert "DOES NOT BUY IS ADMISSIBILITY" in text
    # The liveness correction: a FLOOR, not a gradient, and it says it was
    # previously recorded backwards rather than quietly changing the default.
    assert "GOT BACKWARDS" in text
    assert "FLOOR" in text
    # And that `must_fail` is the one left genuinely open.
    assert "ACTUALLY DEBATABLE" in text
    assert "0.95" in text and "0.52" in text


def test_a_verdict_records_the_count_that_decided_it():
    """A reason without the number behind it cannot be audited afterwards."""
    fields = set(Verdict.__dataclass_fields__)
    assert {"convicts", "decided", "reason", "detail"} <= fields


# --------------------------------------------------------------------------
# THE ADAPTER AGAINST REAL OBJECTS. The tests above drive `pipeline_gates`
# through its own error path only, which would pass with the wiring broken --
# the defect this project has made five times. These run the shipped gate.
# --------------------------------------------------------------------------

CONTRACT = {"io": [{"name": "busy", "dir": "output", "width": 1},
                   {"name": "go", "dir": "input", "width": 1}]}
TESTPLAN = [{"uid": "TP-0000"}]


def _oracle(source, *, tps=("TP-0000",)):
    from specflow.refmodel.oracles import RequirementOracle
    return RequirementOracle(req_uid="REQ-0001", tp_uids=list(tps),
                             source=source)


GOOD = (
    "def decide(trace):\n"
    "    for row in trace:\n"
    "        if row['outputs']['busy']:\n"
    "            return (True, row['edge'], 'busy seen')\n"
    "    return (None, None, 'never busy')\n"
)


def test_the_shipped_gate_accepts_a_well_formed_body():
    """The negative tests above pass with the wiring dead. This one does not."""
    gate = pipeline_gates({"k": _oracle(GOOD)}, CONTRACT, TESTPLAN,
                          legs=GateLegs(correspondence=False, vacuity=False))
    assert gate("k") is None


def test_the_shipped_gate_refuses_a_body_naming_no_output():
    """A check over the stimulus alone can be failed by NO design, because no
    design drives its own inputs. Eleven such bodies were found across four
    runs -- eight ABANDONED, and one TRUSTED AND FROZEN.
    """
    inputs_only = (
        "def decide(trace):\n"
        "    for row in trace:\n"
        "        if row['inputs']['go']:\n"
        "            return (True, row['edge'], 'go seen')\n"
        "    return (None, None, 'no go')\n"
    )
    gate = pipeline_gates({"k": _oracle(inputs_only)}, CONTRACT, TESTPLAN,
                          legs=GateLegs(correspondence=False, vacuity=False))
    why = gate("k")
    assert why and why.startswith("malformed:")


def test_the_shipped_gate_refuses_a_body_that_does_not_compile():
    gate = pipeline_gates({"k": _oracle("def decide(trace)\n    return None\n")},
                          CONTRACT, TESTPLAN,
                          legs=GateLegs(correspondence=False, vacuity=False))
    why = gate("k")
    assert why and why.startswith("malformed:")


def test_a_gate_leg_with_nothing_to_run_on_is_skipped_not_failed():
    """A missing artifact is a fact about the harness. Convicting a check for it
    is the conflation `must_fail` had to be repaired for twice.
    """
    gate = pipeline_gates({"k": _oracle(GOOD)}, CONTRACT, TESTPLAN,
                          legs=GateLegs(), variants=None, reviews=None,
                          traces=None)
    assert gate("k") is None


def test_select_composes_with_the_shipped_gate_end_to_end():
    corpus = {"good": convicts(0), "broken": convicts(0)}
    oracles = {"good": _oracle(GOOD), "broken": _oracle("not python at all(")}
    gate = pipeline_gates(oracles, CONTRACT, TESTPLAN,
                          legs=GateLegs(correspondence=False, vacuity=False))
    chosen = select(corpus, POP, gate=gate)
    assert chosen.kept == ("good",)
    assert chosen.dropped[0].reason == "gate"


# --------------------------------------------------------------------------
# `min_decides` AS A COUNT. The boolean form could not express the case the
# reproduction found: a check sparing six designs by silence and one by
# evidence, which the rule scores exactly as it scores a check that watched
# all seven and objected nowhere.
# --------------------------------------------------------------------------

def thin(r):
    """Decides on exactly one design and spares it. Sound on six by silence."""
    return False if r[0]["outputs"]["a"] == 0 else None


def test_the_weakest_leg_keeps_a_check_that_saw_one_design():
    """`min_decides = 1` is the default because it is what the measured rule
    had, NOT because it is the right threshold.
    """
    chosen = select({"thin": thin}, POP)
    assert chosen.kept == ("thin",)
    assert chosen.verdicts[0].decided == 1


def test_raising_the_leg_removes_a_check_that_spares_by_silence():
    chosen = select({"thin": thin}, POP, ruleset=Ruleset(min_decides=4))
    assert chosen.kept == ()
    dropped = chosen.dropped[0]
    assert dropped.reason == "silent"
    assert "1 of 4" in dropped.detail and "below the 4" in dropped.detail


def test_zero_turns_the_leg_off_entirely():
    chosen = select({"silent": silent}, POP, ruleset=Ruleset(min_decides=0))
    assert chosen.kept == ("silent",)


def test_a_negative_decide_floor_is_refused():
    with pytest.raises(ValueError, match="min_decides"):
        Ruleset(min_decides=-1)


def test_the_compiled_out_finding_states_the_null_and_the_residue():
    from specflow.selection import a_compiled_out_state_reads_as_sound_for_free
    text = a_compiled_out_state_reads_as_sound_for_free()
    # The leg removed nothing here, and saying so is half the result.
    assert "INERT ON THIS CORPUS" in text
    assert "ZERO" in text
    # And what it still lets through.
    assert "COMPILES OUT" in text
    assert "sound for free" in text
    # The threshold is not endorsed, only defaulted.
    assert "NOT been scored" in text


def test_the_reproduction_finding_states_its_own_scope():
    from specflow.selection import the_packaged_rule_reproduces_the_measured_sweep
    text = the_packaged_rule_reproduces_the_measured_sweep()
    assert "EVERY CELL MATCHES" in text
    # The limit is the part that keeps it honest: the decides were cached, so a
    # defect in `decide` would reproduce faithfully.
    assert "does NOT re-derive the decides" in text
    assert "nobody reads it as an end-to-end validation" in text


def test_the_polarity_finding_carries_the_split_and_the_price():
    from specflow.selection import blindness_credits_objecting_to_the_correct_design
    text = blindness_credits_objecting_to_the_correct_design()
    # The defect, stated as the mechanism rather than as a caveat.
    assert "WITHOUT ASKING WHICH ONE WAS WRONG" in text
    # The number that makes it a finding rather than a worry.
    assert "12.6x" in text and "34.1% against 2.7%" in text
    # The actionable half: a clean set costs half what it appeared to.
    assert "6.1 points" in text and "87.8%" in text
    # And what the correction costs the metric itself.
    assert "SCORING instrument" in text
    assert "never feed a selection rule" in text
    # The golden-free signal it surfaced, with its own negative attached.
    assert "3.35x" in text
    assert "good predictor and a bad optimiser" in text.lower() or \
           "GOOD PREDICTOR AND A BAD OPTIMISER" in text


def test_a_spurious_catch_counts_toward_blindness_not_against_it():
    """`apparent - spurious == disagreements - blind` is an ALGEBRAIC IDENTITY
    given how `apparent` is derived, so asserting it pins nothing -- the first
    version of this test did exactly that and passed against a mutant that
    stopped counting spurious catches as blind. Assert the values instead.
    """
    spur = set_blindness([convicts(1)], BY_DESIGN, differ=DIFFER, wrong=B_IS_WRONG)
    true = set_blindness([convicts(1)], BY_DESIGN, differ=DIFFER, wrong=A_IS_WRONG)
    #: Same check, same cell, same objection. Only the side differs.
    assert (spur.blind, spur.spurious, spur.apparent) == (1, 1, 1)
    assert (true.blind, true.spurious, true.apparent) == (0, 0, 1)
    #: Apparent closure is IDENTICAL and real closure is not -- which is the
    #: whole finding in two numbers.
    assert spur.apparent == true.apparent
    assert spur.rate == 1.0 and true.rate == 0.0


# --------------------------------------------------------------------------
# THE OTHER TELLS IN THE CONVICTION MATRIX
# --------------------------------------------------------------------------

def shape(**over):
    """Three designs over four testpoints. A and B are clones; C is the
    outlier. t1 and t2 split the population, t3 and t4 are agreed."""
    base = dict(
        designs=("A", "B", "C"),
        testpoints=("t1", "t2", "t3", "t4"),
        split=frozenset({"t1", "t2"}),
        dissent={"A": 0.0, "B": 0.0, "C": 0.9},
        cluster={"A": 0, "B": 0, "C": 1},
        pairs={"t1": (("A", "C"), ("B", "C")), "t2": (("A", "C"),)},
    )
    base.update(over)
    return PopulationShape(**base)


def test_a_population_that_never_splits_is_refused():
    """The clone guard, one layer up from `population.select`. With nothing to
    disagree about every tell is a constant, and a constant reads as a result."""
    with pytest.raises(ValueError, match="behaviourally indistinguishable"):
        shape(split=frozenset())


def test_a_design_with_no_dissent_rate_is_refused():
    """A structure that does not cover the population would weight the missing
    designs at zero rather than raise, and `dissent_weighted` would read low
    for a check convicting exactly them."""
    with pytest.raises(ValueError, match="no dissent rate or cluster"):
        shape(dissent={"A": 0.0, "B": 0.0})


def test_effective_size_collapses_clones_and_headcount_does_not():
    s = shape()
    assert len(s.designs) == 3
    assert s.effective_size() == 2


def test_the_count_and_the_mass_separate_breadth_from_footprint():
    """Two checks convicting the SAME number of designs, one at four times the
    footprint. The shipped rule cannot tell them apart; `mass` can."""
    narrow = tells({"A": {"t1"}}, shape())
    wide = tells({"A": {"t1", "t2", "t3", "t4"}}, shape())
    assert narrow.count == wide.count == 1
    assert wide.mass == pytest.approx(4 * narrow.mass)
    #: and it is a SHARE of the matrix, not a raw tally -- three designs over
    #: four testpoints is twelve cells, so one objection is one twelfth. A raw
    #: count cannot be compared between populations of different sizes.
    assert narrow.mass == pytest.approx(1 / 12)


def test_split_purity_counts_only_objections_where_the_population_agrees():
    at_split = tells({"A": {"t1", "t2"}}, shape())
    at_agreed = tells({"A": {"t3", "t4"}}, shape())
    assert at_split.split_purity == 0.0
    assert at_agreed.split_purity == 1.0


def test_indiscriminacy_separates_picking_a_side_from_objecting_to_both():
    """t1 carries the pair (A, C). A check objecting to A alone has picked a
    side; one objecting to both has not, and at a cell where they disagree
    objecting to both is a false rejection unless both are wrong."""
    one_side = tells({"A": {"t1"}}, shape())
    both_sides = tells({"A": {"t1"}, "C": {"t1"}}, shape())
    assert one_side.indiscriminacy == 0.0
    assert both_sides.indiscriminacy > 0.0


def test_convicting_the_outlier_costs_less_than_convicting_the_centre():
    """The whole point of the re-weighting: k1's rule reads 126-for-126 partly
    because one design absorbs over-strict checks."""
    centre = tells({"A": {"t1"}}, shape())
    outlier = tells({"C": {"t1"}}, shape())
    assert centre.count == outlier.count == 1
    assert outlier.dissent_weighted < centre.dissent_weighted
    assert outlier.dissent_weighted == pytest.approx(0.1)


def test_two_clones_convicted_count_as_one_opinion():
    clones = tells({"A": {"t1"}, "B": {"t1"}}, shape())
    across = tells({"A": {"t1"}, "C": {"t1"}}, shape())
    assert clones.count == across.count == 2
    assert clones.cluster_count == 1
    assert across.cluster_count == 2


def test_concentration_reads_zero_for_a_silent_check_and_for_a_spread_one():
    """**THE CONFOUND, PINNED SO IT CANNOT BE QUIETLY REMOVED.** Selecting the
    LOW side of concentration selects the silent checks, which are sound by
    silence; that is why the pre-registered direction scored 0 of 38 against a
    chance of 7.2 and had to be reversed."""
    silent = tells({}, shape())
    spread = tells({"A": {"t1"}, "B": {"t1"}, "C": {"t1"}}, shape())
    focused = tells({"A": {"t1"}}, shape())
    assert silent.concentration == 0.0
    assert spread.concentration < focused.concentration
    assert focused.concentration == 1.0


def test_placement_is_signed_by_where_the_check_speaks():
    """Positive when it speaks only where the designs differ, negative when
    only where they agree, and near zero for a check that speaks everywhere."""
    targeted = tells({"A": {"t1", "t2"}}, shape())
    misplaced = tells({"A": {"t3", "t4"}}, shape())
    everywhere = tells({"A": {"t1", "t2", "t3", "t4"}}, shape())
    assert targeted.placement == pytest.approx(1.0)
    assert misplaced.placement == pytest.approx(-1.0)
    assert everywhere.placement == pytest.approx(0.0)


def test_tells_has_no_parameter_that_could_carry_a_reference():
    """The same structural guarantee `select` has. A tell is a selection-side
    instrument; the audit is computed afterwards from a set already built."""
    params = set(inspect.signature(tells).parameters)
    assert params == {"objections", "shape"}
    assert not any("ref" in f or "golden" in f or "audit" in f
                   for f in TellProfile.__dataclass_fields__)


def test_the_one_signal_finding_states_the_null_and_its_power():
    text = the_conviction_matrix_carries_one_signal_not_nine()
    assert "+0.997" in text and "+0.045" in text
    assert "14 to 19 of 33" in text and "16.5" in text
    assert "p = 0.727" in text
    #: the model's own result is reported WITH the bar it failed
    assert "3.06x" in text and "3.35x" in text
    #: and the power limit, or the null reads stronger than it is
    assert "cannot exclude a modest one" in text


def test_the_backwards_finding_names_all_three_defects():
    text = two_tells_were_pre_registered_backwards()
    assert "0 of 38" in text and "0.0003" in text
    assert "randomises per process" in text and "19 hits" in text
    assert "5.29x" in text
    assert "198 of t=6's 201" in text
    #: the harness defect, which is the one that invalidates the others
    assert "byte-identical in length" in text and "mtime, size" in text


def test_the_placement_finding_reports_the_triple_and_the_calibration():
    text = objection_placement_buys_closure_more_cheaply_than_the_count()
    #: the whole triple, never one number alone
    assert "69.0%" in text and "15.9%" in text and "20.8%" in text
    #: the mechanism, stated so it is not read as a soundness filter
    assert "96%" in text and "COMPLETENESS INSTRUMENT" in text
    #: the threshold was chosen against a frontier containing the audit
    assert "belongs in the calibrated column" in text
    #: and the fragility
    assert "766" in text
