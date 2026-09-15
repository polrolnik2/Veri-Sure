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
    Selection,
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
    the_gates_and_the_rule_reject_different_checks,
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

def test_set_blindness_reads_zero_and_one_on_the_two_extremes():
    by_design = {"A": {"tp": rows(0)}, "B": {"tp": rows(1)}}
    differ = lambda a, b: a[0]["outputs"]["a"] != b[0]["outputs"]["a"]  # noqa: E731
    blind_to_all = set_blindness([convicts(0)], by_design, differ=differ)
    assert (blind_to_all.blind, blind_to_all.disagreements) == (1, 1)
    assert blind_to_all.rate == 1.0
    sees_it = set_blindness([convicts(1)], by_design, differ=differ)
    assert (sees_it.blind, sees_it.rate) == (0, 0.0)


def test_blindness_counts_only_cells_where_the_designs_disagree():
    """A cell the population agrees on is not a disagreement the set failed to
    see, so counting it would make an agreeing population look like a blind set.
    """
    by_design = {"A": {"tp": rows(0)}, "B": {"tp": rows(0)}}
    differ = lambda a, b: a[0]["outputs"]["a"] != b[0]["outputs"]["a"]  # noqa: E731
    got = set_blindness([convicts(0)], by_design, differ=differ)
    assert got.disagreements == 0
    assert got.rate == 0.0  # no cells is not "blind to everything"


def test_the_selected_set_at_zero_is_blind_by_construction():
    """The finding this module exists to stop anyone rediscovering: the rule
    that predicts soundness and the rule that selects blindness are ONE
    predicate read twice.
    """
    corpus = {f"c{n}": convicts(n) for n in range(5)}
    chosen = select(corpus, POP, ruleset=Ruleset(max_convictions=0))
    by_design = {"A": {"tp": rows(0)}, "B": {"tp": rows(1)}}
    differ = lambda a, b: a[0]["outputs"]["a"] != b[0]["outputs"]["a"]  # noqa: E731
    got = set_blindness([corpus[k] for k in chosen.kept], by_design,
                        differ=differ)
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
                      convicts_reference=0, blindness=Blindness(5646, 5656)))
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


def test_liveness_is_off_by_default_because_it_pulls_against_the_rule():
    """`liveness` reads verdict movement as proof a check is alive; the rule
    reads conviction of the population as proof it over-reaches. The maximally
    live check is the maximally over-strict one.
    """
    assert GateLegs().liveness is False
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
    assert "pulls the other way" in text.lower()
    # And that composing them is not what makes the set golden-free.
    assert "DOES NOT BUY IS ADMISSIBILITY" in text


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
