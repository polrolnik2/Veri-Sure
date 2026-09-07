"""Tests for the golden-free ensemble instruments.

Each test pins a property the MEASUREMENT depends on, not merely the code path:
a filter that cannot fail is worth nothing, so every predicate here is shown
returning both verdicts on inputs that differ only in the thing it claims to
detect.
"""
import specflow.ensemble as ensemble
from specflow.ensemble import (
    accuracy_is_the_wrong_axis_for_a_reference,
    agreement_is_not_an_oracle,
    check_agreement_is_not_an_oracle,
    conviction_count_is_not_a_descent_criterion,
    soundness_buys_termination_not_correctness,
    split_cells_are_a_specification_finding,
    consensus_cells,
    disagreement_cells,
    refuted_by,
    split_cell_soundness,
)

PORTS = ["a", "b"]


def rows(*vals):
    return [{"outputs": {"a": a, "b": b}, "inputs": {}} for a, b in vals]


def test_unanimous_cells_are_the_ones_every_design_agrees_on():
    by = {"x": rows((1, 0), (1, 1)), "y": rows((1, 0), (0, 1))}
    cons = consensus_cells(by, PORTS)
    assert (0, "a") in cons and (0, "b") in cons
    assert (1, "a") not in cons          # x says 1, y says 0
    assert (1, "b") in cons


def test_a_relaxed_threshold_admits_a_cell_unanimity_rejects():
    by = {"x": rows((1, 0)), "y": rows((1, 0)), "z": rows((0, 0))}
    assert (0, "a") not in consensus_cells(by, PORTS)
    assert consensus_cells(by, PORTS, min_agree=2)[(0, "a")] == ("1", 2)


def test_disagreement_finds_the_row_and_not_the_others():
    by = {"x": rows((1, 0), (1, 1), (0, 0)),
          "y": rows((1, 0), (0, 1), (0, 0))}
    assert disagreement_cells(by, PORTS) == {1}


def test_split_cell_soundness_flags_a_demand_where_the_population_agrees():
    # row 0 is unanimous, row 1 splits. A check that convicts on row 0 is
    # demanding something every design got right.
    by = {"x": rows((1, 0), (1, 1)), "y": rows((1, 0), (0, 1))}
    convicts_row0 = lambda rs: any(r["outputs"]["a"] == 1 for r in rs)  # noqa: E731
    assert split_cell_soundness(convicts_row0, by, PORTS) is True


def test_split_cell_soundness_clears_a_demand_only_in_split_territory():
    # THE PIN THAT MAKES THE TEST ABOVE MEAN SOMETHING: the same shape of check,
    # firing only on the row the designs disagree about, must come back clean.
    by = {"x": rows((1, 0), (1, 1)), "y": rows((1, 0), (0, 1))}
    convicts_row1_only = lambda rs: any(r["outputs"]["b"] == 1 for r in rs)  # noqa: E731
    assert split_cell_soundness(convicts_row1_only, by, PORTS) is False


def test_refuted_by_needs_both_halves():
    spares = rows((0, 0))
    breaks = rows((1, 0))
    fires_on_a = lambda rs: any(r["outputs"]["a"] == 1 for r in rs)  # noqa: E731
    assert refuted_by(fires_on_a, [spares], [breaks]) is True
    # convicts a candidate -> not a refutation, it is over-strictness
    assert refuted_by(fires_on_a, [breaks], [breaks]) is False
    # convicts nothing -> cannot fail
    assert refuted_by(fires_on_a, [spares], [spares]) is False


def test_the_refutation_of_consensus_as_an_oracle_is_carried_in_the_code():
    # This one exists so the idea is not rediscovered as a good one: the numbers
    # that refute it must travel with the function that tempts you into it.
    why = agreement_is_not_an_oracle()
    assert "correlated" in why
    assert "174 against 189" in why


def test_the_per_requirement_check_ensemble_is_refuted_in_the_code_too():
    # The tempting variant of the same idea, and the reason it needs its own
    # entry: the correlation argument that kills the DESIGN ensemble does not
    # obviously apply to several checks written for one sentence. It is still
    # refuted, so the numbers must be where the next reader will look.
    why = check_agreement_is_not_an_oracle()
    assert "never reaches past its own best member" in why
    assert "15.2" in why and "observed overlap is 4" in why


def test_the_objection_count_is_refuted_as_a_descent_signal():
    # The one a repair loop reaches for first, and the only refutation here that
    # is about USING a check set rather than selecting one. It must carry the
    # sign, because a reader who remembers only "weakly correlated" will still
    # descend on it.
    why = conviction_count_is_not_a_descent_criterion()
    assert "-0.223" in why and "-0.542" in why
    assert "requirements it satisfies, not on objections it has left" in why


def test_resolving_a_split_cell_with_another_model_is_refuted():
    # disagreement_cells is the one instrument here that works, so the next move
    # -- ask a model to resolve or flag those cells -- is the one most likely to
    # be tried. Both halves of why it fails have to survive in the text: the
    # reader is worse than the population, AND it cannot see the gap.
    why = split_cells_are_a_specification_finding()
    assert "7 of 20" in why and "0 of 20" in why
    assert "SPECIFICATION defect" in why


def test_a_highly_accurate_reference_is_refuted_as_a_loop_driver():
    # The most seductive number on this plan -- 99.822% accurate, golden-free --
    # attached to the instrument that ranks the known-good design 15th of 16.
    # Both halves must survive together or the text becomes an endorsement.
    why = accuracy_is_the_wrong_axis_for_a_reference()
    assert "99.822%" in why and "15th of 16" in why
    assert "right WHERE THE DESIGN UNDER TEST IS WRONG" in why


def test_objecting_to_no_candidate_is_not_a_rejection_reason():
    # The leg this project ran for months and has now measured as harmful:
    # three of the fourteen checks that caught a held-out design convict none
    # of the population. The warning has to sit on the function that tempts
    # you into the rejection, or it will be re-derived.
    doc = refuted_by.__doc__ or ""
    assert "is NOT" in doc and "may simply be RIGHT" in doc
    assert "THREE convict none" in doc


def test_a_perfectly_sound_set_gives_direction_but_not_sufficiency():
    # The one positive property any rule here produced, and the exact way it
    # is misread. Both numbers must travel together: 45% of the spec with zero
    # unsound checks is what makes the 194 -> 217 mean anything.
    why = soundness_buys_termination_not_correctness()
    # BOTH runs must survive in the text. The clean one is the evidence that
    # the gradient is right; the confounded one is named as confounded so it
    # cannot be re-quoted as a reproduction, which is how it was first read.
    assert "249 to 188" in why and "45% of the specification" in why
    assert "194 to 217" in why and "injected" in why
    assert "SPARSITY, not direction" in why
    # and the obvious response to sparsity, with its measured yield, so the
    # 53%-against-0% split travels with the diagnosis that invites it
    assert "53%" in why and "40 to 43 of 89" in why


def test_every_refutation_is_named_where_someone_reaching_for_it_will_look():
    # A refutation kept in a function nothing points at is a refutation nobody
    # finds. The module docstring is the entry point, so it must name them all.
    doc = ensemble.__doc__ or ""
    for name in ("agreement_is_not_an_oracle",
                 "check_agreement_is_not_an_oracle",
                 "conviction_count_is_not_a_descent_criterion",
                 "split_cells_are_a_specification_finding",
                 "accuracy_is_the_wrong_axis_for_a_reference",
                 "soundness_buys_termination_not_correctness"):
        assert name in doc, f"{name} is unreachable from the module docstring"


def test_empty_population_is_not_an_error():
    assert consensus_cells({}, PORTS) == {}
    assert disagreement_cells({}, PORTS) == set()
