"""Tests for the golden-free ensemble instruments.

Each test pins a property the MEASUREMENT depends on, not merely the code path:
a filter that cannot fail is worth nothing, so every predicate here is shown
returning both verdicts on inputs that differ only in the thing it claims to
detect.
"""
import specflow.ensemble as ensemble
from specflow.ensemble import (
    a_perfectly_sound_majority_set_still_false_accepts,
    accuracy_is_the_wrong_axis_for_a_reference,
    adequacy_is_soundness_and_refutability,
    agreement_is_not_an_oracle,
    check_agreement_is_not_an_oracle,
    conviction_count_is_not_a_descent_criterion,
    soundness_buys_termination_not_correctness,
    soundness_is_what_makes_the_criterion_work,
    split_cells_are_a_specification_finding,
    strength_and_soundness_are_exchanged_not_traded,
    authoring_populations_are_complementary_not_ordered,
    zero_objections_can_be_incompatible_with_correctness,
    the_minority_rule_is_precise_and_that_is_what_it_costs,
    the_soundness_boundary_is_reachable_from_one_side_only,
    the_residue_is_check_strength,
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
    # and the second, larger set -- without it this reads as "a bigger set
    # would finish", which is measured and false
    assert "249 to 192" in why and "51%, a majority" in why


def test_the_stimulus_lever_is_sized_and_the_residue_named():
    # The lever everyone reaches for when a check set says nothing, and the
    # per-port measurement that sizes it at 3 of 50. The 3.9% has to travel
    # with it or the finding reads as "add stimulus".
    why = the_residue_is_check_strength()
    assert "3.9%" in why and "36 DECIDE" in why
    assert "CHECK STRENGTH" in why
    # and the reproduction on a larger set, without which this reads as a
    # one-set number that a wider set might dilute. It does not: same 3 silent,
    # 18 more blind, strength DOWN.
    assert "SAME THREE CHECKS AT " in why and "68 AS AT 50" in why
    assert "54 BLIND" in why and "2.8%" in why


def test_the_strength_edit_is_measured_as_a_partition_not_a_trade():
    # The one result that forecloses "a better author would land in between":
    # 34 single edits, 0 landed in between. Both marginals and the zero have
    # to travel together, or it reads as an ordinary anti-correlation.
    why = strength_and_soundness_are_exchanged_not_traded()
    assert "1.8% to 44.1%" in why
    assert "BOTH CELL IS 0 OF 34" in why and "6.8 expected" in why
    assert "MINIMUM the marginals allow" in why


def test_reaching_zero_objections_is_pinned_as_a_negative_result():
    # The one a repair loop acts on without reading anything else here: its
    # criterion going quiet. Three things have to travel together or the text
    # becomes an endorsement of the run that produced it -- the majority span
    # that makes the set look finished, the audit that makes zero unreachable
    # for a correct design, and the grade that confirms it.
    why = zero_objections_can_be_incompatible_with_correctness()
    assert "45 of 89 requirements = 51%" in why and "7 of the 68" in why
    assert "MUTUALLY" in why and "EXCLUSIVE" in why
    assert "DIFFERS" in why
    # and the inversion, which is the half a reader who already believes the
    # gradient is right will otherwise skip
    assert "249" in why and "192" in why and "200 testpoints" in why


def test_the_stopping_rule_is_stated_and_not_only_the_refutation():
    # A refutation that leaves the loop author with nothing to do gets ignored.
    # The disposition has to be in the same text as the number that motivates it.
    why = zero_objections_can_be_incompatible_with_correctness()
    assert "trial budget" in why
    assert "requirements it satisfies" in why


def test_a_losing_arm_is_not_an_empty_arm():
    # The one cheap positive here, and the half that gets dropped when it is
    # summarised. "Neither arm is better" is true and is NOT the finding; the
    # finding is that their adequate sets do not overlap, so the union beats
    # either. Both halves have to survive or this reads as another null result.
    why = authoring_populations_are_complementary_not_ordered()
    assert "p = 1.000" in why                       # neither arm is better
    assert "INTERSECTION 0" in why                  # and they are disjoint
    assert "union is 5 of" in why and "better arm alone is 3" in why


def test_the_arm_comparison_is_scoped_to_what_it_can_decide():
    # Without this the finding licenses "run more arms", which is not measured.
    why = authoring_populations_are_complementary_not_ordered()
    assert "which PROMPT to ship" in why and "which BODIES to keep" in why
    assert "does NOT say" in why


def test_the_one_endorsed_gate_carries_its_price():
    # The only instrument here that is recommended rather than refuted, which
    # makes it the one most likely to be quoted with the caveat stripped. The
    # 100% and the 9-of-18 have to be in the same text: a reader who takes only
    # the precision builds a set with half the discrimination removed.
    why = the_minority_rule_is_precise_and_that_is_what_it_costs()
    assert "59 OF 59" in why and "31%" in why          # precision against its base rate
    assert "9 of the 18" in why                        # and what that precision costs
    assert "never as a selector" in why


def test_the_endorsement_does_not_read_as_a_tuning_problem():
    # The obvious response -- "then use a looser threshold" -- is refuted in the
    # text, because the rejected checks convict most of the population by the
    # same property that makes them discriminate.
    why = the_minority_rule_is_precise_and_that_is_what_it_costs()
    assert "not a tuning loss" in why
    assert "same property" in why


def test_adequacy_has_a_decomposition_and_it_names_both_legs():
    # The only entry here that says what the adequate cell IS rather than how
    # hard it is to reach. The 52/16 split is the load-bearing evidence; the
    # composite's n = 7 is not, and must travel with it.
    why = adequacy_is_soundness_and_refutability()
    assert "52 checks,  3 adequate" in why and "16 checks, 15 adequate" in why
    assert "94% precision and 83% recall" in why
    assert "n = 7" in why


def test_the_adequacy_gate_is_labelled_calibrated_and_not_a_score():
    # Two ways this becomes an overclaim: quoting the 10.7x without saying the
    # threshold was set by reading the known-good design, and reading the
    # refutable leg as PREDICTING discrimination when it is at chance there.
    why = adequacy_is_soundness_and_refutability()
    assert "CALIBRATED rule" in why and "not a score" in why
    assert "at chance on its own" in why
    assert "do not use it to build the set" in why


def test_the_audit_column_is_a_defect_and_not_a_rate_to_trade():
    # This module quotes a false-reject rate beside every span, which invites
    # reading it as a price. The matched-pair measurement says otherwise, and
    # both halves have to travel: the corpus catches the design widely, and
    # almost none of those catches are sound.
    why = soundness_is_what_makes_the_criterion_work()
    assert "129, over 57 of 89 requirements = 64%" in why
    assert "SOUNDLY WITH EXACTLY ONE CHECK" in why
    assert "0 objections   ACCEPTED" in why and "1 objection    REJECTED" in why


def test_the_matched_pair_claim_is_bounded_to_what_it_shows():
    # One objection on a badly wrong design is discrimination, not adequacy.
    # Without this the entry reads as an endorsement of the sound set.
    why = soundness_is_what_makes_the_criterion_work()
    assert "not adequacy" in why
    assert "The claim is" in why and "narrow" in why


def test_the_ceiling_result_excludes_every_alternative_explanation():
    # The negative that closes the corpus. Each excluded explanation is one a
    # reader will otherwise supply for themselves, and the span and the audit
    # together are what make "zero objections" mean something here rather than
    # being the arithmetic impossibility of the unsound case.
    why = a_perfectly_sound_majority_set_still_false_accepts()
    assert "45 of 89 requirements = 51%" in why and "ZERO" in why
    assert "0 objections of 68 in 6 of 14 trials" in why
    assert "DIFFERS" in why and "193 of 318" in why
    assert "CONSISTENT with equivalence" in why      # not the unsound-set case
    assert "249" in why and "193" in why             # the gradient was right


def test_the_ceiling_result_is_exhaustive_and_not_a_selection_miss():
    # Without this the finding reads as "a better rule would have found them",
    # which is the response every other negative here has attracted. It cannot
    # apply: the set already contains every sound check in the corpus.
    why = a_perfectly_sound_majority_set_still_false_accepts()
    assert "ZERO of the\n124 are sound" in why or "ZERO of the " in why
    assert "there are none to " in why
    assert "No sound set this corpus can produce rejects this design" in why
    assert "54 decide where their own port is" in why and "2.8%" in why


def test_the_boundary_asymmetry_carries_both_directions_and_its_cost():
    # The only prescription this module makes. It corrects the partition claim
    # rather than replacing it, so both rates must be present -- the 0 of 34 is
    # what makes the 7 of 47 mean something.
    why = the_soundness_boundary_is_reachable_from_one_side_only()
    assert "34 checks,  0 adequate" in why and "47 checks,  7 adequate" in why
    assert "p = 0.0196" in why
    assert "AUTHOR STRICT AND NARROW" in why
    # and the cost, without which this reads as a route rather than a rate
    assert "twelve came back VACUOUS" in why
    assert "18%" in why and "26%" in why


def test_the_boundary_asymmetry_is_bounded_to_a_ceiling():
    # "Then run it again until a majority" is the obvious response and it is
    # wrong: the population is finite and its exhaustion is short of a majority
    # only if every member landed, which 15% a round does not deliver.
    why = the_soundness_boundary_is_reachable_from_one_side_only()
    assert "BOUNDED" in why and "63 of 89 = 71%" in why
    assert "does not by itself deliver a majority" in why


def test_the_narrowing_decay_is_measured_and_not_overclaimed():
    # Round 2 is what turns "a bounded route" into a number, and it is also the
    # place to overclaim: two levers landing on 1 of 28 is striking and is not
    # significant at that n. Both the coincidence and the caveat must be present.
    why = the_soundness_boundary_is_reachable_from_one_side_only()
    assert "1 of 28 = 4%" in why
    assert "8 of 45 = 18%" in why and "7 of 47 = 15%" in why
    assert "p = 0.245" in why and "NOT independently" in why
    assert "27-28 of 89 = 31%" in why


def test_every_refutation_is_named_where_someone_reaching_for_it_will_look():
    # A refutation kept in a function nothing points at is a refutation nobody
    # finds. The module docstring is the entry point, so it must name them all.
    doc = ensemble.__doc__ or ""
    for name in ("agreement_is_not_an_oracle",
                 "check_agreement_is_not_an_oracle",
                 "conviction_count_is_not_a_descent_criterion",
                 "split_cells_are_a_specification_finding",
                 "accuracy_is_the_wrong_axis_for_a_reference",
                 "soundness_buys_termination_not_correctness",
                 "the_residue_is_check_strength",
                 "strength_and_soundness_are_exchanged_not_traded",
                 "zero_objections_can_be_incompatible_with_correctness",
                 "authoring_populations_are_complementary_not_ordered",
                 "the_minority_rule_is_precise_and_that_is_what_it_costs",
                 "adequacy_is_soundness_and_refutability",
                 "soundness_is_what_makes_the_criterion_work",
                 "a_perfectly_sound_majority_set_still_false_accepts",
                 "the_soundness_boundary_is_reachable_from_one_side_only"):
        assert name in doc, f"{name} is unreachable from the module docstring"


def test_the_definition_of_sound_requires_the_check_to_decide():
    # An off-by-one in this plan's headline came from writing SOUND as "convicts
    # the known-good design nowhere", which a check that never decides there
    # satisfies for free. The module is where anyone recomputing these numbers
    # will look for the definition, so the requirement has to be stated there.
    doc = ensemble.__doc__ or ""
    assert "DECIDES ON THE KNOWN-GOOD DESIGN" in doc
    assert "sound by\nsilence" in doc
    assert "decides 0 of 318" in doc


def test_empty_population_is_not_an_error():
    assert consensus_cells({}, PORTS) == {}
    assert disagreement_cells({}, PORTS) == set()
