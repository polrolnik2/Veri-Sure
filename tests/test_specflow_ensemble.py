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
    the_two_legs_cannot_be_composed_from_separate_bodies,
    the_adequacy_filter_does_not_survive_being_a_target,
    golden_free_span_grew_and_the_precision_did_not_hold,
    a_wider_sound_set_lands_the_same_design_in_the_same_place,
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
                 "the_soundness_boundary_is_reachable_from_one_side_only",
                 "the_two_legs_cannot_be_composed_from_separate_bodies",
                 "the_adequacy_filter_does_not_survive_being_a_target",
                 "golden_free_span_grew_and_the_precision_did_not_hold",
                 "a_wider_sound_set_lands_the_same_design_in_the_same_place"):
        assert name in doc, f"{name} is unreachable from the module docstring"


def test_the_merge_round_reports_zero_and_says_zero_is_the_floor():
    # "0 of 26" alone reads as a weak round. The claim is stronger and rests on
    # the marginals: 8 sound + 18 discriminating = 26 = n, so the sets COULD be
    # disjoint and are. Dropping that arithmetic turns a structural result into
    # a tally, which is the retraction this module exists to prevent.
    why = the_two_legs_cannot_be_composed_from_separate_bodies()
    assert "**ADEQUATE**           0         0       **0**" in why
    assert "8 + 18 = 26 = n" in why
    assert "MINIMUM THE MARGINALS ALLOW" in why
    assert "5.5" in why                      # the independence expectation


def test_the_merge_round_records_that_the_target_was_stated_in_numbers():
    # The result only means what it says if the author was told where the answer
    # sits. If the prompt merely gestured at "between", 0 of 26 would measure the
    # instruction rather than the task.
    why = the_two_legs_cannot_be_composed_from_separate_bodies()
    assert "MINORITY of the 13" in why
    assert "Three hit the band and none of the three is" in why


def test_the_merge_round_retires_the_ceiling_that_licensed_it():
    # The round was run because 50 of 89 requirements hold both legs in different
    # bodies. Reporting the negative without retiring that arithmetic leaves the
    # next reader free to re-derive the same unreachable ceiling.
    why = the_two_legs_cannot_be_composed_from_separate_bodies()
    assert "50" in why and "upper bound" in why
    doc = ensemble.__doc__ or ""
    assert "exactly\ndisjoint" in doc


def test_the_merge_round_states_the_prompt_defect_and_bounds_it():
    # A round with a defect in its own prompt must say so, and must say why the
    # defect cannot carry the result -- otherwise the negative is unfalsifiable.
    why = the_two_legs_cannot_be_composed_from_separate_bodies()
    assert "declared-port block" in why
    assert "22 of the 26 dropped no" in why


def test_the_target_round_says_what_the_band_actually_contains():
    # "2 of 24 reached the band" alone reads as a weak round. The result is that
    # BOTH of the two are sound and NEITHER discriminates, which is what makes it
    # a statement about the rule rather than about the authors.
    why = the_adequacy_filter_does_not_survive_being_a_target()
    assert "both are sound and NEITHER" in why
    assert "CONVICTS 12 OF 13 -- OUTSIDE THE BAND" in why


def test_the_target_round_does_not_blame_the_feedback():
    # If the count were simply unusable the finding would be about the signal's
    # legibility, not about what it points at. The text has to record that the
    # distribution moved, or the negative overstates itself.
    why = the_adequacy_filter_does_not_survive_being_a_target()
    assert "The distribution moved" in why
    assert "five do after" in why


def test_the_marginal_minimum_is_carried_for_all_three_rounds():
    # One round at the marginal floor is a coincidence; three is the structure.
    # Dropping any row turns the claim back into a tally of low yields.
    why = the_adequacy_filter_does_not_survive_being_a_target()
    for row in ("strength   -- blind, assert MORE  34     11     21    32    0    0",
                "merge      -- both ends shown     26      8     18    26    0    0",
                "band       -- numeric target      24     10     15    25    1    1"):
        assert row in why
    assert "6.8, " in why and "5.5 and 6.2 expected under independence" in why


def test_the_third_four_percent_is_recorded_beside_the_other_two():
    why = the_adequacy_filter_does_not_survive_being_a_target()
    assert "1 of 28" in why and "1 of 24" in why
    assert "24 to 25 " in why


def test_the_golden_free_table_never_prints_a_span_without_its_audit():
    # A span without its false-reject rate is the defect nine headlines here were
    # retracted for. Every row of the golden-free table carries both, and the
    # ceiling row is labelled as selected BY the known-good design.
    why = golden_free_span_grew_and_the_precision_did_not_hold()
    for row in ("C  convicts <= 2 of 13        108         44          49%    *3%*",
                "B  convicts a minority        125         50        **56%**  *10%*"):
        assert row in why
    assert "selected BY the" in why


def test_the_majority_span_is_not_reported_as_an_accept_criterion():
    # 56% is the largest golden-free span measured here and it is still unusable
    # as an accept criterion, for the arithmetic reason. Dropping that sentence
    # turns the number into the claim the plan keeps having to withdraw.
    why = golden_free_span_grew_and_the_precision_did_not_hold()
    assert "STILL NOT AN ACCEPT CRITERION" in why
    assert "any design scoring " in why and "zero is a different design" in why


def test_the_minority_rules_perfect_precision_is_corrected_with_its_base_rate():
    # 59 of 59 was quoted as perfect. It is not, on the corpus that grew, and a
    # precision without its base rate is not a measurement either.
    why = golden_free_span_grew_and_the_precision_did_not_hold()
    assert "105 of them spare the known-good design: 97%, not " in why
    assert "126 sound among 424 deciding = 30%" in why
    doc = ensemble.__doc__ or ""
    assert "97%, not 100%" in doc


def test_the_precision_loss_is_attributed_to_the_rounds_that_used_the_rule():
    # If the rule simply degraded with size, the lesson would be "measure on more
    # bodies". The measured cause is that the rounds authored against it, which
    # is a different and actionable rule about when to recompute an audit.
    why = golden_free_span_grew_and_the_precision_did_not_hold()
    assert "did not shape" in why
    assert "recomputed" in why


def test_the_rerun_names_what_changed_about_the_set():
    # "we re-ran it and got the same answer" is only worth recording if the input
    # actually differed. The row pair is what makes this a second experiment
    # rather than a repetition.
    why = a_wider_sound_set_lands_the_same_design_in_the_same_place()
    assert "the earlier set       68   45 of 89=51%    *0*        18" in why
    assert "**this one**         119   52 of 89=58%    *0*        31" in why
    assert "12 objections against a held-out design" in why


def test_the_rerun_excludes_a_wrong_gradient_explicitly():
    # The earlier over-strict run failed with an INVERTED gradient, which left
    # "the set mis-steered it" available as an explanation. This run has no
    # inversion, and the text has to say so or the negative is weaker than it is.
    why = a_wider_sound_set_lands_the_same_design_in_the_same_place()
    assert "no\ninversion over the final approach" in why or "inversion" in why
    assert "Not a wrong gradient" in why
    assert "7 trials unspent" in why


def test_the_rerun_reports_the_grade_with_its_pins_and_a_clean_rescore():
    # A verdict quoted without its pins is the defect that produced a spurious
    # UNKNOWN here once, and a verdict taken in a directory a commit overwrote is
    # the compare-a-design-against-itself defect. Both guards are in the text.
    why = a_wider_sound_set_lands_the_same_design_in_the_same_place()
    assert "all three grade pins green" in why
    assert "re-scored from scratch in " in why


def test_the_residue_is_unchanged_and_that_is_the_conclusion():
    why = a_wider_sound_set_lands_the_same_design_in_the_same_place()
    assert "134 of 3,399 exposed decisions = 3.9%" in why
    assert "300 of 7,677 = 3.9%" in why
    assert "not a property of a set" in why


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


def test_the_vacuous_state_is_named_as_holding_adequate_checks():
    t = ensemble.a_vacuous_check_is_not_a_defect_and_the_routing_assumes_it_is()
    assert "8 OF THE 14 ADEQUATE CHECKS ARE CLASSIFIED VACUOUS" in t
    assert "3 of 14" in t and "8 of 14" in t


def test_the_vacuous_finding_names_the_instrument_that_fixes_it():
    t = ensemble.a_vacuous_check_is_not_a_defect_and_the_routing_assumes_it_is()
    assert "refuted_by" in t
    assert "Route a refutable vacuous check" in t


def test_the_keep_band_is_reported_below_the_base_rate_not_above_it():
    """The keep set is 90% sound against a 95% base, and that is the point."""
    t = ensemble.a_vacuous_check_is_not_a_defect_and_the_routing_assumes_it_is()
    assert "90% against 95%" in t
    assert "choosing against adequacy" in t


def test_the_vacuous_finding_refuses_to_be_read_as_a_rule_calibration():
    """A soundness filter measured on a soundness-selected set says nothing."""
    t = ensemble.a_vacuous_check_is_not_a_defect_and_the_routing_assumes_it_is()
    assert "WHAT THIS DOES NOT SAY" in t
    assert "1.03x" in t and "31%" in t


def test_the_evidence_round_reports_the_agreement_in_both_directions():
    t = ensemble.new_evidence_moves_the_rule_and_the_audit_together()
    assert "state-changed but still sound                 0" in t
    assert "newly unsound but state unchanged             0" in t


def test_the_evidence_round_says_why_it_is_not_a_fitted_threshold():
    t = ensemble.new_evidence_moves_the_rule_and_the_audit_together()
    assert "Nothing was fitted" in t
    assert "neither column had seen" in t


def test_the_evidence_round_reports_the_span_loss_beside_the_agreement():
    """A round that removes false keeps reads as a loss and must say so."""
    t = ensemble.new_evidence_moves_the_rule_and_the_audit_together()
    assert "BOUGHT NO SPAN" in t
    assert "14 before, 14 after" in t
    assert "A span that falls when the evidence widens was never a span" in t


def test_the_keep_rule_names_what_the_refutable_leg_costs():
    t = ensemble.the_keep_state_must_include_the_zero()
    assert "COSTS 30 REQUIREMENTS OF SPAN AND QUADRUPLES THE FALSE-REJECT RATE" in t
    assert "loses on both" in t


def test_the_keep_rule_reports_span_and_audit_as_a_pair_on_every_row():
    """Every row of the golden-free table carries its false-reject rate."""
    t = ensemble.the_keep_state_must_include_the_zero()
    for span, audit in (("16%", "*48%*"), ("49%", "***12%***"), ("39%", "*0%*"),
                        ("69%", "*96%*"), ("75%", "*74%*")):
        line = next(ln for ln in t.splitlines() if span in ln and "|" in ln)
        assert audit in line


def test_the_cut_is_rederived_for_the_population_it_runs_on():
    t = ensemble.the_keep_state_must_include_the_zero()
    assert "88% precision at 88% recall" in t
    assert "must be re-derived when N changes" in t


def test_the_ten_percent_audit_is_retracted_as_a_population_artefact():
    t = ensemble.the_keep_state_must_include_the_zero()
    assert "10% false-reject rate" in t
    assert "artefact of the population" in t


def test_the_validation_run_reports_the_grade_beside_the_objection_fall():
    t = ensemble.the_editor_can_read_a_state_it_cannot_argue_about()
    assert "DIFFERS" in t and "pins green" in t
    assert "too SPARSE" in t


def test_the_validation_run_names_the_two_it_stopped_on_as_the_unsound_two():
    t = ensemble.the_editor_can_read_a_state_it_cannot_argue_about()
    assert "EXACTLY THE TWO CHECKS THE AUDIT CALLS UNSOUND" in t
    assert "0 of the reference's 5,723 rows" in t


def test_the_validation_run_attributes_the_judgement_to_the_probe():
    t = ensemble.the_editor_can_read_a_state_it_cannot_argue_about()
    assert "THE STATE IS A DECLARED PROBE" in t
    assert "n is two" in t


def test_the_occurrence_meaning_split_corrects_the_earlier_rate():
    t = ensemble.an_occurrence_claim_is_checkable_and_a_meaning_claim_is_not()
    assert "1 of 5, not 2 of 2" in t
    assert "RIGHT, 1 of 1" in t and "WRONG, 0 of 4" in t


def test_the_occurrence_meaning_split_states_the_bound():
    t = ensemble.an_occurrence_claim_is_checkable_and_a_meaning_claim_is_not()
    assert "does nothing for a meaning claim" in t
    assert "recorded rather than trusted" in t


def test_more_span_did_not_buy_more_correctness_reports_both_grades():
    t = ensemble.more_span_did_not_buy_more_correctness()
    assert "THREE TESTPOINTS CLOSER" in t
    assert "both are DIFFERS" in t


def test_more_span_excludes_the_editor_running_out_of_room():
    t = ensemble.more_span_did_not_buy_more_correctness()
    assert "trial budget unspent" in t


def test_the_exhaustion_finding_counts_both_sides():
    t = ensemble.selection_is_exhausted_and_authoring_is_the_constraint()
    assert "278 of 484" in t and "6 = 7% of 89" in t
    assert "no rule can select what was never written" in t


def test_the_exhaustion_finding_reports_the_residue_per_check():
    """The strength denominator is per check, not per testpoint."""
    t = ensemble.selection_is_exhausted_and_authoring_is_the_constraint()
    assert "95 of 6,521 exposed decisions = 1.5%" in t
    assert "not blind for passing a defect on another" in t


def test_the_exhaustion_finding_says_it_is_not_a_count_of_checks():
    t = ensemble.selection_is_exhausted_and_authoring_is_the_constraint()
    assert "not the NUMBER of" in t and "what a check asserts" in t


def test_the_majority_round_reports_all_three_columns():
    t = ensemble.narrowing_the_span_gap_reaches_a_majority()
    assert "SPAN UP, FALSE REJECTS DOWN, ADEQUACY UP" in t
    assert "| **after** | **117** | **50** | **56%** | ***11%*** | ***16*** |" in t


def test_the_majority_round_does_not_quote_span_as_adequacy():
    t = ensemble.narrowing_the_span_gap_reaches_a_majority()
    assert "56% SPAN IS NOT 56% ADEQUACY" in t
    assert "16 of 89 = 18%" in t


def test_the_majority_round_records_its_admissibility_check():
    t = ensemble.narrowing_the_span_gap_reaches_a_majority()
    assert "0 violations over 23 prompts" in t
    assert "0 duplicates, 0 unchanged" in t


def test_the_substitute_for_adequacy_is_reported_as_collapsing():
    t = ensemble.the_refutable_leg_predicts_discrimination_and_still_must_not_select()
    assert "THE TWO SETS ARE IDENTICAL" in t
    assert "under a new name" in t


def test_the_substitute_names_the_structural_reason_the_test_was_weak():
    t = ensemble.the_refutable_leg_predicts_discrimination_and_still_must_not_select()
    assert "nothing to align on" in t and "untested" in t


def test_the_surviving_instrument_carries_its_recall_loss():
    t = ensemble.the_refutable_leg_predicts_discrimination_and_still_must_not_select()
    assert "misses 9 of the 25 catchers" in t
    assert "Report with it; never select with it" in t


def test_the_majority_validation_reports_the_grade_and_the_residue():
    t = ensemble.a_majority_span_set_satisfied_in_full_is_still_not_equivalent()
    assert "DIFFERS, three pins green" in t
    assert "0 objections in 6,542 exposed decisions = 0.0%" in t


def test_the_majority_validation_excludes_every_excuse_by_name():
    t = ensemble.a_majority_span_set_satisfied_in_full_is_still_not_equivalent()
    for excuse in ("Not soundness", "Not span", "Not selection", "Not stimulus",
                   "Not the editor", "Not the gradient"):
        assert excuse in t


def test_the_majority_validation_says_span_is_not_the_target():
    t = ensemble.a_majority_span_set_satisfied_in_full_is_still_not_equivalent()
    assert "Span is not the quantity to optimise" in t
    assert "every SOUND check the set contains" in t


def test_the_gate_is_credited_and_the_authors_are_not():
    t = ensemble.a_gate_makes_a_failing_repair_free_without_making_it_work()
    assert "THE ENTIRE DIFFERENCE FROM THE ROUND THAT FAILED" in t
    assert "The authors did not improve" in t


def test_the_gated_round_honours_its_pre_registered_bar():
    t = ensemble.a_gate_makes_a_failing_repair_free_without_making_it_work()
    assert "no further validation run was dispatched" in t
    assert "Moving a bar after seeing the number" in t


def test_the_gated_round_reports_its_own_prompt_defect():
    t = ensemble.a_gate_makes_a_failing_repair_free_without_making_it_work()
    assert "11 of 40 strengthened bodies dropped an input" in t
    assert "3 of 40 is a FLOOR" in t


def test_the_consensus_oracle_reports_its_false_reject_rate_in_advance():
    t = ensemble.the_consensus_is_an_oracle_even_though_it_is_not_a_ranking()
    assert "2,073" in t and "0.86%" in t
    assert "known IN ADVANCE" in t


def test_the_consensus_oracle_refuses_zero_as_an_accept_criterion():
    t = ensemble.the_consensus_is_an_oracle_even_though_it_is_not_a_ranking()
    assert "ZERO IS STILL NOT THE ACCEPT CRITERION" in t
    assert "DESCENT under a trial budget" in t


def test_the_consensus_correction_names_what_it_cannot_separate():
    t = ensemble.the_consensus_is_an_oracle_even_though_it_is_not_a_ranking()
    assert "CANNOT BE SEPARATED" in t
    assert "closed on a sample of one held-out design" in t


def test_the_consensus_oracle_excludes_probes_on_the_port_only_argument():
    t = ensemble.the_consensus_is_an_oracle_even_though_it_is_not_a_ranking()
    assert "convict a correct design for its encoding" in t


def test_the_coarse_ratchet_defect_is_stated_as_arithmetic_not_anecdote():
    t = ensemble.a_ratchet_on_counts_refuses_an_improvement_it_cannot_see()
    assert "ARITHMETIC RATHER THAN EMPIRICAL" in t
    assert "passing requirements 1 -> 1" in t


def test_the_ratchet_finding_prescribes_two_numbers_not_a_better_one():
    t = ensemble.a_ratchet_on_counts_refuses_an_improvement_it_cannot_see()
    assert "a FINE one to steer" in t and "a COARSE one to judge" in t
    assert "it is NO gradient, and it rejects correct work" in t


def test_the_contended_directory_finding_names_its_tell():
    t = ensemble.a_run_directory_written_by_two_agents_is_not_a_measurement()
    assert "matched neither the design the run started from" in t
    assert "NO NUMBER FROM EITHER DIRECTORY IS QUOTED" in t


def test_the_contended_directory_finding_refuses_repair_by_inspection():
    t = ensemble.a_run_directory_written_by_two_agents_is_not_a_measurement()
    assert "cannot be repaired by inspection" in t
    assert "one agent per run directory" in t.lower()


def test_the_module_docstring_carries_the_two_driver_findings():
    d = ensemble.__doc__ or ""
    assert "a_ratchet_on_counts_refuses_an_improvement_it_cannot_see" in d
    assert "a_run_directory_written_by_two_agents_is_not_a_measurement" in d


def test_the_obligation_ceiling_is_labelled_golden_selected():
    t = ensemble.a_body_is_judged_whole_and_its_obligations_are_not()
    assert "GOLDEN-SELECTED" in t
    assert "ceiling in the sense MAXSOUND is, never a score" in t


def test_the_obligation_instrument_reports_its_own_blindness():
    t = ensemble.a_body_is_judged_whole_and_its_obligations_are_not()
    assert "BLIND TO 78% OF ITS OWN POPULATION" in t
    assert "39%" in t


def test_the_obligation_extrapolation_is_marked_an_estimate():
    t = ensemble.a_body_is_judged_whole_and_its_obligations_are_not()
    assert "DOES NOT REACH A MAJORITY" in t
    assert "an ESTIMATE and not a measurement" in t


def test_the_obligation_finding_names_the_prize_and_the_prescription():
    t = ensemble.a_body_is_judged_whole_and_its_obligations_are_not()
    assert "61 of 89 = 69%" in t
    assert "name the obligation it fires on" in t


def test_the_obligation_cuts_were_read_not_trusted():
    t = ensemble.a_body_is_judged_whole_and_its_obligations_are_not()
    assert "READ RATHER THAN TRUSTED" in t
    assert "All four are real cuts" in t


def test_the_obligation_instrument_admits_the_syntactic_luck():
    t = ensemble.a_body_is_judged_whole_and_its_obligations_are_not()
    assert "SYNTACTIC LUCK" in t
    assert "the +4 is not robust either" in t
    assert "STRUCTURED FIELD" in t


def test_the_contention_finding_corrects_its_own_prescription():
    t = ensemble.a_run_directory_written_by_two_agents_is_not_a_measurement()
    assert "BROKE IT A THIRD TIME WITHIN THE HOUR" in t
    assert "THE REMEDY IS NOT A RULE, IT IS A LOCK" in t


def test_the_lock_is_described_as_built_not_proposed():
    t = ensemble.a_run_directory_written_by_two_agents_is_not_a_measurement()
    assert "reads are unlocked so a reader can never block a writer" in t
    assert "reclaimed and the takeover is printed" in t


def test_the_dead_slice_names_which_runs_it_touches():
    t = ensemble.the_editors_dataflow_slice_was_dead_in_every_run_here()
    assert "NO DATAFLOW SLICE IN ANY RUN ON THIS PLAN" in t
    assert "21-, 111- or 117-check runs" in t


def test_the_dead_slice_separates_what_stands_from_what_does_not():
    t = ensemble.the_editors_dataflow_slice_was_dead_in_every_run_here()
    assert "CONFOUND IS CONSTANT ACROSS ARMS" in t
    assert "pessimistic by an unknown amount" in t
    assert "COSTS COMPARABILITY" in t


def test_the_floor_finding_is_arithmetic_before_it_is_a_miter_result():
    t = ensemble.the_loop_descended_through_the_reference_designs_own_floor()
    assert "DESCENDED THROUGH THE FLOOR" in t
    assert "2,073" in t and "1,758" in t
    assert "before any miter runs" in t.lower()


def test_the_floor_finding_removes_the_reconstructed_value_explanation():
    t = ensemble.the_loop_descended_through_the_reference_designs_own_floor()
    assert "reconstructed, not observed" in t
    assert "Being real rather than reconstructed is not what was missing" in t


def test_the_floor_finding_does_not_overclaim_the_percentages():
    t = ensemble.the_loop_descended_through_the_reference_designs_own_floor()
    assert "Different denominators" in t
    assert "Stop on the floor, not on the trial budget" in t


def test_the_ratchet_finding_is_corrected_by_its_own_follow_up_run():
    t = ensemble.a_ratchet_on_counts_refuses_an_improvement_it_cannot_see()
    assert "FALSE as a general claim -- finer is not better" in t
    assert "26% improvement in cells" in t


def test_the_ratchet_correction_states_the_rule_as_the_property():
    t = ensemble.a_ratchet_on_counts_refuses_an_improvement_it_cannot_see()
    assert "GRANULARITY OF THE PROPERTY BEING CLAIMED, NOT OF THE EVIDENCE" in t
    assert "lower than any of the three designs the cell ratchet would have accepted" in t
    assert "must be the number that latches" in t


def test_the_consensus_bound_names_the_share_the_criterion_cannot_see():
    t = ensemble.the_consensus_route_is_bounded_by_the_specification_not_the_editor()
    assert "66% OF WHAT IS STILL WRONG" in t
    assert "12.0x" in t
    assert "SILENT on, by construction" in t


def test_the_consensus_bound_explains_the_floor_result():
    t = ensemble.the_consensus_route_is_bounded_by_the_specification_not_the_editor()
    assert "0.7%" in t and "0.86%" in t
    assert "one event seen from two sides" in t


def test_the_consensus_bound_refuses_the_unregistered_tiebreak():
    t = ensemble.the_consensus_route_is_bounded_by_the_specification_not_the_editor()
    assert "NOT PRE-REGISTERED AND MUST NOT BE USED AS A TIEBREAK" in t
    assert "mixed is what stands" in t


def test_the_head_to_head_reports_the_two_criteria_as_indistinguishable():
    t = ensemble.two_criteria_on_one_harness_land_the_same_design_in_the_same_place()
    assert "INDISTINGUISHABLE" in t
    assert "206 = 59%" in t and "210 = 60%" in t


def test_the_head_to_head_names_the_criterion_as_not_binding():
    t = ensemble.two_criteria_on_one_harness_land_the_same_design_in_the_same_place()
    assert "THE CRITERION IS NOT THE BINDING CONSTRAINT" in t
    assert "0.7%" in t and "1.3%" in t


def test_the_head_to_head_names_both_confounds_and_their_direction():
    t = ensemble.two_criteria_on_one_harness_land_the_same_design_in_the_same_place()
    assert "handicaps the check set" in t
    assert "not separable here" in t


def test_the_floor_is_stated_in_testpoints_with_the_reachable_share():
    t = ensemble.the_floor_on_any_spec_derived_pipeline_is_146_of_348_testpoints()
    assert "146 = 42%" in t
    assert "ONLY 22 OF 348 TESTPOINTS = 6%" in t


def test_the_floor_bounds_steering_not_achievement():
    t = ensemble.the_floor_on_any_spec_derived_pipeline_is_146_of_348_testpoints()
    assert "what a criterion can STEER, not what a design can ACHIEVE" in t
    assert "by luck" in t


def test_the_floor_is_supported_by_a_trajectory():
    t = ensemble.the_floor_on_any_spec_derived_pipeline_is_146_of_348_testpoints()
    assert "37%" in t and "56%" in t and "66%" in t
    assert "mechanism rather than a correlation" in t


def test_the_stacked_criterion_reports_one_testpoint_of_gain():
    t = ensemble.two_spec_only_instruments_stacked_still_stop_at_the_floor()
    assert "205 = 59%" in t
    assert "bought ONE testpoint over either alone" in t


def test_the_stacked_criterion_carries_the_goodhart_sample():
    t = ensemble.two_spec_only_instruments_stacked_still_stop_at_the_floor()
    assert "-12% and -25% on what the loop optimises" in t
    assert "17 trials behind it" in t


def test_the_majority_vote_is_recorded_as_below_chance():
    t = ensemble.two_spec_only_instruments_stacked_still_stop_at_the_floor()
    assert "38.4%" in t and "12.3%" in t
    assert "OPTIMAL for a population criterion" in t


def test_the_weighting_defect_names_the_exchange_rate():
    t = ensemble.stacking_two_criteria_needs_weights_and_mine_had_none()
    assert "3.2% of the total" in t and "1/29" in t
    assert "the ratchet refused every one" in t.lower()


def test_the_weighting_defect_states_the_general_rule():
    t = ensemble.stacking_two_criteria_needs_weights_and_mine_had_none()
    assert "prices one in units of the other" in t
    assert "sparse is what it is FOR" in t


def test_the_missing_history_names_what_a_run_retains():
    t = ensemble.a_finished_run_cannot_be_asked_what_its_ratchet_refused()
    assert "records 27 decisions and keeps ONE" in t
    assert "Overwritten by every commit" in t


def test_the_missing_history_bounds_the_band_claim():
    t = ensemble.a_finished_run_cannot_be_asked_what_its_ratchet_refused()
    assert "205, 206, 210 and 205" in t
    assert "not attributable" in t


def test_the_missing_history_states_the_remedy_as_a_log():
    t = ensemble.a_finished_run_cannot_be_asked_what_its_ratchet_refused()
    assert "one append per commit" in t.lower()
    assert "CONSIDERED" in t and "ACCEPTED" in t


def test_the_weighted_run_reports_the_same_grade():
    t = ensemble.weighting_the_two_instruments_equally_changes_nothing_at_the_grade()
    assert "205 OF 348, AGAINST THE UNWEIGHTED RUN'S 205 OF 348" in t
    assert "the commit latched" in t


def test_the_weighted_run_carries_the_opposed_movement():
    t = ensemble.weighting_the_two_instruments_equally_changes_nothing_at_the_grade()
    assert "proxy improved 22%" in t and "2.4% WORSE" in t
    assert "NOT attributable" in t


def test_the_weighted_run_closes_the_combination_question():
    t = ensemble.weighting_the_two_instruments_equally_changes_nothing_at_the_grade()
    assert "combination question is closed" in t.lower()
    assert "not of how its parts are priced" in t


def test_the_fifth_contradiction_claim_is_refuted():
    t = ensemble.the_fifth_contradiction_claim_is_the_fifth_refutation()
    assert "REFUTED IN ONE LINE" in t
    assert "All five members spare" in t


def test_the_editor_soundness_tally_is_carried_forward():
    t = ensemble.the_fifth_contradiction_claim_is_the_fifth_refutation()
    assert "9 of 36 = 25%" in t
    assert "third independent editor to name REQ-0081" in t


def test_the_editors_hedge_is_recorded_as_the_reliable_part():
    t = ensemble.the_fifth_contradiction_claim_is_the_fifth_refutation()
    assert "right to decline" in t.lower()
    assert "REQ-0015.v2@n3" in t


def test_the_answer_is_measured_present_in_the_population():
    t = ensemble.a_criterion_only_corrects_where_it_beats_the_design_under_test()
    assert "13,210 of 13,973 cells = 94.5%" in t
    assert "SELECTION, not absence" in t


def test_the_split_distribution_is_recorded_as_bimodal():
    t = ensemble.a_criterion_only_corrects_where_it_beats_the_design_under_test()
    assert "24.5%" in t and "31.4%" in t and "31.1%" in t
    assert "opposite polarity" in t


def test_dissent_is_recorded_as_a_spec_only_predictor():
    t = ensemble.a_criterion_only_corrects_where_it_beats_the_design_under_test()
    assert "r = +0.882" in t
    assert "correctness makes a design dissent" in t


def test_no_selector_reaches_fifty_percent_precision():
    t = ensemble.a_criterion_only_corrects_where_it_beats_the_design_under_test()
    assert "NOT ONE REACHES 50%" in t
    assert "30.8%" in t and "19.2%" in t


def test_the_general_law_names_the_design_under_test():
    t = ensemble.a_criterion_only_corrects_where_it_beats_the_design_under_test()
    assert "CORRECTS ONLY WHERE ITS ACCURACY EXCEEDS THE DESIGN'S" in t
    assert "77.5%" in t


def test_the_law_qualifies_the_outside_the_loop_conclusion():
    t = ensemble.a_criterion_only_corrects_where_it_beats_the_design_under_test()
    assert "The first half is now refuted" in t
    assert "a BETTER one" in t


def test_the_inversion_names_both_accuracies():
    t = ensemble.the_loop_drove_the_design_past_its_own_criterion()
    assert "99.13%" in t and "99.30%" in t
    assert "OVERTAKEN ITS OWN CRITERION" in t


def test_the_inversion_carries_the_objection_split():
    t = ensemble.the_loop_drove_the_design_past_its_own_criterion()
    assert "773   58.8%" in t and "375   28.5%" in t
    assert "repaired 375 cells and broken" in t


def test_the_inversion_states_the_fixed_versus_rising_mechanism():
    t = ensemble.the_loop_drove_the_design_past_its_own_criterion()
    assert "one accuracy is fixed and the other rises" in t.lower()
    assert "no way to see the inversion" in t


def test_the_inversion_prescribes_a_stopping_rule():
    t = ensemble.the_loop_drove_the_design_past_its_own_criterion()
    assert "STOPPING RULE, NOT A BETTER CRITERION" in t
    assert "trial budget" in t


def test_the_inversion_records_the_authors_own_error():
    t = ensemble.the_loop_drove_the_design_past_its_own_criterion()
    assert "my correction of it was" in t
    assert "stopped at very nearly the right moment" in t


def test_the_population_curve_is_negative_at_every_size():
    t = ensemble.a_consensus_cannot_outrank_a_competent_reader_at_any_size()
    assert "NEGATIVE AT EVERY SIZE" in t
    assert "-1.337%" in t and "-0.167%" in t


def test_the_population_curve_extrapolates_before_generating():
    t = ensemble.a_consensus_cannot_outrank_a_competent_reader_at_any_size()
    assert "asymptotic to zero FROM BELOW" in t
    assert "six generations and six suite runs unspent" in t


def test_the_population_curve_names_the_hidden_variable():
    t = ensemble.a_consensus_cannot_outrank_a_competent_reader_at_any_size()
    assert "SELECTS FOR EASY CELLS" in t
    assert "how hard" in t and "in lockstep" in t


def test_the_crossing_point_is_located():
    t = ensemble.a_consensus_cannot_outrank_a_competent_reader_at_any_size()
    assert "+3.003%" in t
    assert "between trials 7 and 8" in t
    assert "ONE TRIAL after" in t


def test_the_requirement_on_a_working_criterion_is_stated():
    t = ensemble.a_consensus_cannot_outrank_a_competent_reader_at_any_size()
    assert "BETTER READER than the design" in t
    assert "reads the SENTENCES rather than voting" in t


def test_the_two_instruments_are_scored_side_by_side():
    t = ensemble.the_two_instruments_came_apart_and_only_one_was_overtaken()
    assert "28.5%" in t and "71.4%" in t
    assert "ONE HAS INVERTED AND THE OTHER HAS NOT" in t


def test_the_mechanism_predicts_which_instrument_survives():
    t = ensemble.the_two_instruments_came_apart_and_only_one_was_overtaken()
    assert "vote over IMPLEMENTATIONS" in t
    assert "reads one requirement SENTENCE" in t


def test_the_editor_is_recorded_as_discarding_true_objections():
    t = ensemble.the_two_instruments_came_apart_and_only_one_was_overtaken()
    assert "five true objections" in t
    assert "REQ-0081" in t and "right about those" in t


def test_the_conclusion_is_split_rather_than_generalised():
    t = ensemble.the_two_instruments_came_apart_and_only_one_was_overtaken()
    assert "TRUE of a consensus" in t and "NOT SHOWN of checks" in t
    assert "COVERAGE" in t


def test_the_calibration_is_labelled_before_the_arm_runs():
    t = ensemble.the_two_instruments_came_apart_and_only_one_was_overtaken()
    assert "that is calibration" in t
    assert "may be quoted as an uncalibrated golden-free score" in t


def test_sequencing_reports_the_best_grade_on_the_plan():
    t = ensemble.sequencing_the_two_instruments_breaks_the_band()
    assert "186 of 348, against a band five arms could not leave" in t
    assert "first_miss_err" in t


def test_sequencing_is_isolated_from_a_better_criterion():
    t = ensemble.sequencing_the_two_instruments_breaks_the_band()
    assert "reach 206" in t and "reach 205" in t
    assert "not a better criterion" in t


def test_sequencing_reports_against_its_pre_registration():
    t = ensemble.sequencing_the_two_instruments_breaks_the_band()
    assert "target was TWO objections" in t
    assert "three SOUND objections" in t
    assert "'partial' band" in t


def test_sequencing_attributes_the_residue_to_coverage():
    t = ensemble.sequencing_the_two_instruments_breaks_the_band()
    assert "moved the check count by ZERO" in t
    assert "COVERAGE IS THE ONE THING THE GOAL" in t


def test_the_gap_round_reports_total_separation():
    t = ensemble.the_soundness_filter_selects_exactly_the_silent_checks()
    assert "NINE OF NINE SILENT, TWENTY-SEVEN OF THIRTY-ONE OBJECTING" in t
    assert "0 bodies shared across requirements" in t


def test_the_gap_round_names_the_selection_coupling():
    t = ensemble.the_soundness_filter_selects_exactly_the_silent_checks()
    assert "selects for checks that SPARE spec-derived designs" in t
    assert "precise about the wrong population" in t


def test_the_gap_round_separates_span_from_signal():
    t = ensemble.the_soundness_filter_selects_exactly_the_silent_checks()
    assert "52 of 89" in t
    assert "+5 and +0 now" in t
    assert "SPAN IS NOT THE METRIC" in t


def test_the_narrowing_round_landed_zero():
    t = ensemble.narrowing_crosses_the_boundary_without_landing_on_it()
    assert "ZERO OF THIRTY-ONE, AGAINST A MEASURED FIRST-ATTEMPT RATE OF 15%" in t
    assert "0 shared bodies" in t


def test_the_narrowing_round_names_the_jump():
    t = ensemble.narrowing_crosses_the_boundary_without_landing_on_it()
    assert "SEVEN convictions to ZERO" in t
    assert "no gradual narrowing" in t


def test_the_narrowing_round_joins_the_strength_round():
    t = ensemble.narrowing_crosses_the_boundary_without_landing_on_it()
    assert "34 of 34 crossed" in t
    assert "measured empty on 65 attempts" in t


def test_the_narrowing_round_prices_a_second_attempt():
    t = ensemble.narrowing_crosses_the_boundary_without_landing_on_it()
    assert "1 of 28 = 4%" in t
    assert "about one check" in t


def test_the_aiming_defect_names_all_three_consequences():
    t = ensemble.the_editor_could_not_aim_at_what_it_was_judged_by()
    assert "JUDGED BY 117 CHECKS AND COULD AIM AT TEN OUTPUTS" in t
    assert "Unknown requirement" in t and "listed outputs, not checks" in t


def test_the_aiming_defect_records_the_waveform_was_present():
    t = ensemble.the_editor_could_not_aim_at_what_it_was_judged_by()
    assert "THE WAVEFORM WAS THERE" in t
    assert "accurate about its experience and wrong about the cause" in t


def test_the_aiming_defect_records_the_failed_first_fix():
    t = ensemble.the_editor_could_not_aim_at_what_it_was_judged_by()
    assert "every CLI call is\\na fresh process" in t or "fresh process" in t
    assert "dataflow slice dead in every run" in t


def test_the_aiming_defect_bounds_its_own_claim():
    t = ensemble.the_editor_could_not_aim_at_what_it_was_judged_by()
    assert "does not claim the editor" in t
    assert "reporting my harness as a finding" in t


def test_the_stuck_run_reports_no_progress():
    t = ensemble.five_sound_checks_jointly_satisfiable_and_the_editor_is_stuck()
    assert "5 objections to 5" in t
    assert "both commits rejected and discarded" in t


def test_the_stuck_run_proves_joint_satisfiability():
    t = ensemble.five_sound_checks_jointly_satisfiable_and_the_editor_is_stuck()
    assert "ALL FIVE SPARE THE KNOWN-GOOD DESIGN" in t
    assert "JOINTLY SATISFIABLE" in t


def test_the_stuck_run_is_named_a_search_failure():
    t = ensemble.five_sound_checks_jointly_satisfiable_and_the_editor_is_stuck()
    assert "SEARCH FAILURE, NOT AN ORACLE FAILURE" in t
    assert "local optimum" in t and "worse intermediate state" in t


def test_the_contradiction_claim_is_recorded_as_reproducible():
    t = ensemble.five_sound_checks_jointly_satisfiable_and_the_editor_is_stuck()
    assert "sixth refutation" in t
    assert "systematic misreading" in t


def test_the_stuck_run_qualifies_itself():
    t = ensemble.five_sound_checks_jointly_satisfiable_and_the_editor_is_stuck()
    assert "trace=False" in t
    assert "plus the criterion's" in t


def test_the_evidence_path_names_three_dropped_values():
    t = ensemble.three_dropped_values_and_one_root_cause()
    assert "FEEDING IT THREE EMPTY ARGUMENTS" in t
    assert "349" in t and "vcd_by_tp" in t


def test_the_evidence_path_names_the_shared_root_cause():
    t = ensemble.three_dropped_values_and_one_root_cause()
    assert "every CLI call is a fresh process" in t
    assert "did not need persisting" in t.lower()


def test_the_perturbation_contradicts_both_editors():
    t = ensemble.three_dropped_values_and_one_root_cause()
    assert "the defect is TEMPORAL" in t
    assert "memoryless edits" in t


def test_the_earlier_stops_are_not_editor_results():
    t = ensemble.three_dropped_values_and_one_root_cause()
    assert "NEITHER\\nMEASURED THE EDITOR" in t or "MEASURED THE EDITOR" in t
    assert "reporting my harness as a finding" in t


def test_the_editor_trades_one_clause_for_the_other():
    t = ensemble.the_editor_oscillates_between_two_clauses_of_one_sentence()
    assert "FOUR COMMITS, ALL REJECTED" in t
    assert "One objection traded for four." in t


def test_the_two_clauses_come_from_one_sentence():
    t = ensemble.the_editor_oscillates_between_two_clauses_of_one_sentence()
    assert "REQ-0087" in t and "REQ-0029" in t and "REQ-0030" in t
    assert "clause A" in t and "clause B" in t


def test_the_ratchet_is_cleared_before_the_editor_is_blamed():
    t = ensemble.the_editor_oscillates_between_two_clauses_of_one_sentence()
    assert "RATCHET IS NOT MISCALIBRATED" in t
    assert "4 failing to 6" in t


def test_the_perturbation_verdict_was_available_and_unused():
    t = ensemble.the_editor_oscillates_between_two_clauses_of_one_sentence()
    assert "the defect is TEMPORAL" in t
    assert "fact about the editor rather than about the harness" in t


def test_a_committing_run_has_no_stable_design():
    t = ensemble.a_committing_design_is_not_stable_while_the_commit_runs()
    assert "ROLLED BACK" in t
    assert "diff that went empty" in t.lower() or "DIFF THAT WENT EMPTY" in t


def test_the_four_artifacts_are_distinguished():
    t = ensemble.a_committing_design_is_not_stable_while_the_commit_runs()
    for name in ("dut.v", "staged.v", "best.v", "run1/"):
        assert name in t
    assert "note_best" in t


def test_the_unreachable_state_is_proved_not_assumed():
    t = ensemble.a_check_on_an_unreachable_state_reads_as_sound_and_costs_half_a_budget()
    assert "k-induction" in t and "UNREACHABLE" in t
    assert "control in_lrefill3" in t and "REACHABLE" in t


def test_the_population_rule_is_blind_to_abstention():
    t = ensemble.a_check_on_an_unreachable_state_reads_as_sound_and_costs_half_a_budget()
    assert "silence is scored as soundness" in t
    assert "convict 2 of 7" in t


def test_the_wrong_steer_cost_half_the_budget():
    t = ensemble.a_check_on_an_unreachable_state_reads_as_sound_and_costs_half_a_budget()
    assert "Commits 1, 2 and 3" in t
    assert "BUILD\\nCONFIGURATION" in t or "BUILD CONFIGURATION" in t.replace("\\n", " ")


def test_the_screen_keeps_partly_live_requirements():
    t = ensemble.a_check_on_an_unreachable_state_reads_as_sound_and_costs_half_a_budget()
    assert "ENTIRELY about it" in t
    assert "REQ-0026" in t and "one branch beside a live LREFILL3" in t


def test_the_screened_criterion_spans_a_majority():
    t = ensemble.a_check_on_an_unreachable_state_reads_as_sound_and_costs_half_a_budget()
    assert "52 of 89 = 58%, A MAJORITY" in t
    assert "3 objections of 114" in t


def test_the_group_is_satisfiable_by_six_witnesses():
    t = ensemble.six_designs_satisfy_the_group_three_editors_called_unsatisfiable()
    assert "SIX OF SEVEN" in t and "B, C, D, E, F and H" in t
    assert "exactly one" in t


def test_the_refutation_is_golden_free():
    t = ensemble.six_designs_satisfy_the_group_three_editors_called_unsatisfiable()
    assert "golden-free refutation of a golden-free claim" in t


def test_the_failure_is_reclassified_as_search():
    t = ensemble.six_designs_satisfy_the_group_three_editors_called_unsatisfiable()
    assert "SEARCH failure" in t
    assert "one step from where the loop is standing" in t


def test_the_editor_is_never_shown_the_existence_proof():
    t = ensemble.six_designs_satisfy_the_group_three_editors_called_unsatisfiable()
    assert "THREE EDITORS HAVE NOW MADE THE SAME WRONG CALL" in t
    assert "sitting unused as an existence proof" in t


def test_the_population_has_seven_equivalence_classes():
    t = ensemble.seven_readings_seven_designs_and_the_soundness_sufficiency_trade()
    assert "SEVEN EQUIVALENCE CLASSES" in t
    assert "All 21 pairs" in t and "reads no known-good design" in t


def test_rejecting_six_of_seven_is_discrimination():
    t = ensemble.seven_readings_seven_designs_and_the_soundness_sufficiency_trade()
    assert "DISCRIMINATION, not" in t
    assert "at most one of seven" in t


def test_soundness_does_not_survive_conjunction():
    t = ensemble.seven_readings_seven_designs_and_the_soundness_sufficiency_trade()
    assert "SOUNDNESS DOES NOT SURVIVE CONJUNCTION" in t
    assert "rejections UNION" in t.replace("\\n", " ")


def test_the_unanimity_rule_has_perfect_recall():
    t = ensemble.seven_readings_seven_designs_and_the_soundness_sufficiency_trade()
    assert "10 of the 10" in t and "100% recall" in t
    assert "SELECTED BY golden" in t and "ceiling" in t


def test_both_ends_fail_in_opposite_ways():
    t = ensemble.seven_readings_seven_designs_and_the_soundness_sufficiency_trade()
    assert "UNREACHABLE for a correct design" in t
    assert "cannot force equivalence" in t
    assert "one defect with two signs" in t


def test_the_ceiling_set_accepts_two_inequivalent_designs():
    t = ensemble.no_sound_subset_of_this_corpus_forces_equivalence()
    assert "0 convict it" in t
    assert "B, and only B" in t and "DIFFERS" in t


def test_the_impossibility_generalises_to_every_sound_subset():
    t = ensemble.no_sound_subset_of_this_corpus_forces_equivalence()
    assert "No sound subset of this corpus forces" in t
    assert "Exhaustive" in t


def test_no_threshold_separates_sound_from_convicting():
    t = ensemble.no_sound_subset_of_this_corpus_forces_equivalence()
    assert "near-even at every level" in t
    assert "ceiling, not a score" in t


def test_the_remedy_and_its_blocker_are_both_named():
    t = ensemble.no_sound_subset_of_this_corpus_forces_equivalence()
    assert "NEW CHECKS separating B" in t
    assert "control leak" in t
    assert "one design, one corpus" in t


def test_the_impossibility_claim_carries_its_own_retraction():
    """The correction must live where the claim does, not only below it.

    A reader who reaches `no_sound_subset_of_this_corpus_forces_equivalence`
    and stops there must not come away with the overstated conclusion.
    """
    d = ensemble.no_sound_subset_of_this_corpus_forces_equivalence.__doc__
    assert "CORRECTED" in d
    assert "SCORED" in d
    assert "a_proof_is_exhaustive_only_over_what_it_enumerated" in d


def test_the_proof_broke_on_bodies_that_were_never_scored():
    t = ensemble.a_proof_is_exhaustive_only_over_what_it_enumerated()
    assert "477 distinct authored bodies" in t
    assert "not one of which had ever been decided against any design" in t
    assert "14, over 7 requirements" in t


def test_the_recovered_set_is_sound_wide_and_able_to_reject():
    t = ensemble.a_proof_is_exhaustive_only_over_what_it_enumerated()
    assert "163" in t and "68%" in t
    assert "ALL EIGHT REJECTED" in t
    # the three legs, and that every earlier set failed exactly one of them
    assert "failed on exactly one of the three legs" in t


def test_the_recovered_corpus_moves_the_ceiling_and_not_the_golden_free_set():
    """The half that would be easy to drop, and it is the half that matters.

    A reader who takes only the 68% away from this finding would think the
    golden-free pipeline had improved. It did not.
    """
    t = ensemble.a_proof_is_exhaustive_only_over_what_it_enumerated()
    assert "ZERO of them" in t
    assert "anti-correlation confirmed a third time" in t


def test_a_negative_result_needs_its_denominator_checked_too():
    t = ensemble.a_proof_is_exhaustive_only_over_what_it_enumerated()
    assert "exhaustive over the population it enumerated" in t
    assert "the sign is reversed" in t
    assert "as hard as a positive one" in t


def test_a_skipped_check_is_indistinguishable_from_a_passing_one():
    t = ensemble.a_missing_body_reads_as_a_check_that_passed()
    assert "104 OF THEM" in t
    assert "like a check that passed" in t


def test_the_scorer_must_refuse_an_incomplete_denominator():
    t = ensemble.a_missing_body_reads_as_a_check_that_passed()
    assert "REFUSE AN INCOMPLETE DENOMINATOR, NEVER SKIP IT" in t
    assert "8 of 348" in t


def test_the_recovered_check_fires_on_an_optimised_design():
    t = ensemble.a_recovered_check_catches_a_design_the_scored_set_almost_accepted()
    assert "1 objection" in t and "**2**" in t
    assert "REQ-0037" in t and "477 bodies" in t


def test_one_objection_is_discrimination_not_sufficiency():
    t = ensemble.a_recovered_check_catches_a_design_the_scored_set_almost_accepted()
    assert "51%" in t
    assert "discrimination, not sufficiency" in t
    # and the golden-free rule still cannot reach the check that did the work
    assert "minority rule's threshold" in t


def test_the_three_descriptions_of_a_design_are_distinguished():
    t = ensemble.the_accepted_design_is_not_the_last_one_simulated()
    assert "dut.v" in t and "run1" in t and "best.v" in t
    assert "LAST SIMULATED" in t


def test_disagreeing_in_both_directions_means_two_designs():
    t = ensemble.the_accepted_design_is_not_the_last_one_simulated()
    assert "BOTH DIRECTIONS AT ONCE" in t
    assert "never one design seen at two times" in t


def test_the_conflict_conclusion_is_refuted_by_the_selection_rule():
    t = ensemble.three_editors_called_a_sound_set_self_contradictory()
    assert "no subset of the set is jointly unsatisfiable" in t
    assert "REQ-0032" in t and "REQ-0069" in t


def test_the_conflict_conclusion_costs_budget_not_just_accuracy():
    t = ensemble.three_editors_called_a_sound_set_self_contradictory()
    assert "8 of 14 trials unspent" in t
    assert "adjudicating the oracle set" in t


def test_per_check_satisfiability_does_not_compose():
    """The number that separates the admissible fact from the needed one."""
    t = ensemble.three_editors_called_a_sound_set_self_contradictory()
    assert "161 of 163" in t
    assert "**0**" in t
    assert "does not compose" in t


def test_the_joint_satisfiability_witness_is_circular():
    t = ensemble.three_editors_called_a_sound_set_self_contradictory()
    assert "circular" in t.lower() or "CIRCULAR" in t
    assert "artifact the loop is trying to produce" in t
    assert "not a missing instrument someone could go and build" in t


def test_all_three_measures_moved_together():
    t = ensemble.the_gradient_holds_on_a_set_that_rejects_everything()
    assert "22 objections" in t and "**5**" in t
    assert "80%" in t and "55%" in t
    assert "ALL THREE TOGETHER" in t


def test_the_run_is_not_reported_as_a_set_result():
    """The pre-registered reading must survive the numbers being good."""
    t = ensemble.the_gradient_holds_on_a_set_that_rejects_everything()
    assert "2 trials unspent" in t
    assert "measures the EDITOR" in t
    assert "not the strongest negative and it is not a positive" in t


def test_the_recovered_checks_carry_the_endgame():
    t = ensemble.the_gradient_holds_on_a_set_that_rejects_everything()
    assert "FOUR OF THE FIVE" in t
    assert "three distinct defects" in t


def test_the_untouched_output_is_named():
    t = ensemble.the_gradient_holds_on_a_set_that_rejects_everything()
    assert "first_hit_ack" in t and "1,063" in t and "938" in t


def test_the_pair_construction_needs_no_reference():
    t = ensemble.blindness_has_a_golden_free_instrument_that_ranks_but_cannot_certify()
    assert "PASSES TWO DESIGNS which DIFFER" in t
    assert "whichever of the two is right" in t


def test_the_correlation_is_the_strongest_measured_here():
    t = ensemble.blindness_has_a_golden_free_instrument_that_ranks_but_cannot_certify()
    assert "+0.908" in t
    assert "-0.54" in t          # the order route it beats


def test_the_clean_cell_is_the_number_that_matters_and_it_is_small():
    """Precision reads well; the cell that would certify does not."""
    t = ensemble.blindness_has_a_golden_free_instrument_that_ranks_but_cannot_certify()
    assert "5/8 = 62%, n=8" in t
    assert "clean by SILENCE" in t
    assert "PRIORITISER, NOT A CERTIFICATE" in t


def test_more_designs_do_not_fix_the_clean_cell():
    t = ensemble.blindness_has_a_golden_free_instrument_that_ranks_but_cannot_certify()
    assert "shared-misreading blind spot" in t
    assert "closed the consensus route" in t


def test_the_blindness_round_misses_its_own_bar():
    t = ensemble.a_witness_makes_blindness_authorable_and_does_not_break_the_trade()
    assert "6 of 39 = 15%" in t
    assert "BAR WAS 8 AND IT LANDED ON 6" in t
    assert "do NOT rebuild the set on it" in t


def test_targeting_is_the_variable_against_the_strength_round():
    t = ensemble.a_witness_makes_blindness_authorable_and_does_not_break_the_trade()
    assert "0 of 34" in t and "p = 0.0271" in t
    assert "asserting more with nothing to aim at" in t


def test_the_blindness_drop_is_split_by_soundness():
    """The deflation. The aggregate is mostly over-strictness."""
    t = ensemble.a_witness_makes_blindness_authorable_and_does_not_break_the_trade()
    assert "-9%" in t and "-43%" in t
    assert "FOR THE WRONG REASON" in t
    assert "REQ-0001" in t and "168 convictions" in t


def test_the_trade_survives_the_round():
    t = ensemble.a_witness_makes_blindness_authorable_and_does_not_break_the_trade()
    assert "does not break the trade" in t.lower()
    assert "56%" in t


def test_the_per_check_metric_is_not_a_set_metric():
    t = ensemble.blindness_is_correlated_across_checks_so_strengthening_one_adds_nothing()
    assert "121 to 136" in t
    assert "measuring the denominator" in t


def test_set_blindness_is_unchanged_by_the_round():
    t = ensemble.blindness_is_correlated_across_checks_so_strengthening_one_adds_nothing()
    assert "3,221 = 56.9%" in t
    assert "ZERO" in t
    assert "strict subset" in " ".join(t.split())


def test_the_identical_numbers_were_verified_not_accepted():
    """This plan's own signature for a harness defect is byte-identical output."""
    t = ensemble.blindness_is_correlated_across_checks_so_strengthening_one_adds_nothing()
    assert "signature for a harness" in t
    assert "163" in t and "486" in t


def test_blindness_is_one_blind_spot_not_many():
    t = ensemble.blindness_is_correlated_across_checks_so_strengthening_one_adds_nothing()
    assert "one blind spot with 163 checks in front of it" in t
    assert "scored on cells the SET newly reaches" in t


def test_the_holes_are_uniform_not_concentrated():
    t = ensemble.no_body_in_this_corpus_closes_a_set_hole_soundly()
    assert "196 of 348" in t and "14%" in t
    assert "43%" in t and "76%" in t


def test_the_stimulus_is_ruled_out_by_construction():
    """These cells are already driven; the set is silent on evidence it has."""
    t = ensemble.no_body_in_this_corpus_closes_a_set_hole_soundly()
    assert "the suite already runs" in t
    assert "no stimulus round closes any of them" in t


def test_no_body_closes_a_hole_soundly():
    t = ensemble.no_body_in_this_corpus_closes_a_set_hole_soundly()
    assert "**296**" in t and "288" in t
    assert "**0**" in t
    assert "it is total" in t


def test_the_sound_by_silence_correction_is_recorded():
    t = ensemble.no_body_in_this_corpus_closes_a_set_hole_soundly()
    assert "decides: false" in t
    assert "sound BY SILENCE" in t
    assert "withdrawn" in t


def test_both_routes_reach_zero_on_the_composing_metric():
    t = ensemble.no_body_in_this_corpus_closes_a_set_hole_soundly()
    assert "does not close AUTHORING" in t
    assert "Two routes, two zeroes" in t


def test_the_minority_rule_loses_its_precision_on_the_full_corpus():
    t = ensemble.convicting_none_of_the_population_is_the_soundness_rule()
    assert "59 of 59" in t and "13% false-reject" in t
    assert "does not survive the corpus growing" in t


def test_the_step_is_at_zero_convictions_not_two():
    t = ensemble.convicting_none_of_the_population_is_the_soundness_rule()
    assert "126 FOR 126" in t
    assert "48%" in t and "61%" in t
    assert "sharp rather than monotone" in " ".join(t.split())


def test_the_zero_set_is_sound_and_discriminates_on_held_out():
    t = ensemble.convicting_none_of_the_population_is_the_soundness_rule()
    assert "**11**" in t
    assert "held out of its own selection" in t
    assert "56%" in t


def test_the_rule_predicts_soundness_but_not_sufficiency():
    t = ensemble.convicting_none_of_the_population_is_the_soundness_rule()
    assert "self-certification" in t
    assert "nothing here predicts SUFFICIENCY without one" in t


def test_the_audit_re_dates_the_run_in_flight():
    t = ensemble.convicting_none_of_the_population_is_the_soundness_rule()
    flat = " ".join(t.split())
    assert "certificate of NON-equivalence" in flat
    assert "126-check set is the one to carry forward" in flat


def test_both_ends_of_the_trade_are_scored_on_one_metric():
    t = ensemble.the_golden_free_soundness_rule_costs_essentially_all_discrimination()
    assert "56.9%" in t and "99.8%" in t
    assert "12 of 5,656" in " ".join(t.split())


def test_selecting_for_predictable_soundness_is_selecting_for_blindness():
    t = ensemble.the_golden_free_soundness_rule_costs_essentially_all_discrimination()
    assert "same predicate read twice" in t
    assert "126 for 126" in t


def test_the_golden_free_completeness_answer_is_no():
    t = ensemble.the_golden_free_soundness_rule_costs_essentially_all_discrimination()
    assert "+0.908" in t
    assert "IT IS NO ON THIS CORPUS" in " ".join(t.split())


def test_what_survives_is_stated_and_bounded():
    t = ensemble.the_golden_free_soundness_rule_costs_essentially_all_discrimination()
    assert "11 times to design L" in t
    assert "two orders of magnitude short" in " ".join(t.split())


def test_the_next_run_is_pre_registered_as_not_a_new_negative():
    t = ensemble.the_golden_free_soundness_rule_costs_essentially_all_discrimination()
    assert "PRE-REGISTERED" in t
    assert "not a new negative" in " ".join(t.split()).lower()


def test_the_editor_scored_zero_on_a_labelled_set():
    t = ensemble.an_editor_cannot_locate_over_strictness_even_when_it_is_there()
    assert "REQ-0015" in t and "REQ-0064" in t
    assert "ZERO PRECISION AND ZERO RECALL" in t


def test_the_target_really_existed_this_time():
    """What separates this from the three refuted-by-construction runs."""
    t = ensemble.an_editor_cannot_locate_over_strictness_even_when_it_is_there()
    assert "22 of the 167" in t
    assert "it could have been -- and it was not" in " ".join(t.split())


def test_the_finding_is_scoped_to_the_run_that_produced_it():
    # This test previously pinned "THEY CANNOT LOCATE IT" -- the generalisation
    # a later run refuted at 7 of 7. It now pins the scoped claim instead, so
    # the retraction cannot be silently undone.
    t = ensemble.an_editor_cannot_locate_over_strictness_even_when_it_is_there()
    flat = " ".join(t.split())
    assert "THIS EDITOR DID NOT LOCATE IT" in flat
    assert "THEY CANNOT LOCATE IT" not in flat
    assert "this identification is at chance or worse" in flat


def test_the_matched_pair_separates_on_divergence_closed():
    t = ensemble.set_blindness_predicts_how_far_an_editor_gets()
    flat = " ".join(t.split())
    assert "56.9%" in flat and "99.8%" in flat
    assert "-32%" in flat and "-3%" in flat


def test_the_prediction_was_made_before_the_run():
    t = ensemble.set_blindness_predicts_how_far_an_editor_gets()
    assert "PRE-REGISTERED" in t
    assert "12 of 5,656" in " ".join(t.split())


def test_it_is_scored_on_what_the_loop_achieves():
    t = ensemble.set_blindness_predicts_how_far_an_editor_gets()
    assert "scored on what the loop achieves" in " ".join(t.split())


def test_the_unequal_trial_counts_are_addressed_not_hidden():
    t = ensemble.set_blindness_predicts_how_far_an_editor_gets()
    flat = " ".join(t.split())
    assert "10 of 21" in flat and "19 of 21" in flat
    assert "Neither stopped for budget" in flat


def test_the_scope_is_two_runs():
    t = ensemble.set_blindness_predicts_how_far_an_editor_gets()
    assert "two points do not establish a slope" in " ".join(t.split())


def test_the_sweep_spans_the_whole_range_in_both_columns():
    t = ensemble.blindness_and_soundness_are_one_golden_free_knob()
    flat = " ".join(t.split())
    assert "99.8%" in flat and "0.0%" in flat
    assert "64.4%" in flat
    assert "BLINDNESS FALLS AND THE AUDIT RISES ACROSS THE WHOLE SWEEP" in flat


def test_the_cumulative_monotonicity_is_disclaimed():
    t = ensemble.blindness_and_soundness_are_one_golden_free_knob()
    flat = " ".join(t.split())
    assert "CORRECTION TO THE FIRST VERSION OF THIS FINDING" in flat
    assert "a property of the construction and carries no information" in flat
    assert "it dips at t = 5" in flat


def test_the_rule_is_a_step_function_with_a_coin_flip_in_the_middle():
    t = ensemble.blindness_and_soundness_are_one_golden_free_knob()
    flat = " ".join(t.split())
    assert "126 times out of 126" in flat
    assert "261 times out of 263" in flat
    assert "NO SIGNAL AT ALL, at 50.7%" in flat


def test_the_blind_band_is_where_the_blindness_reduction_lives():
    t = ensemble.blindness_and_soundness_are_one_golden_free_knob()
    flat = " ".join(t.split())
    assert "Those 75 checks are everything between" in flat
    assert "every point inside it is bought blind" in flat


def test_the_sweep_reproduces_sets_built_separately():
    t = ensemble.blindness_and_soundness_are_one_golden_free_knob()
    assert "byte-for-byte" in " ".join(t.split())


def test_the_reference_selected_set_is_off_the_curve():
    t = ensemble.blindness_and_soundness_are_one_golden_free_knob()
    flat = " ".join(t.split())
    assert "56.9% blind with an audit of zero" in flat
    assert "No golden-free threshold reaches that point" in flat


def test_the_mechanism_is_the_thirty_eight_unsound_checks():
    t = ensemble.blindness_and_soundness_are_one_golden_free_knob()
    flat = " ".join(t.split())
    assert "161 of CEIL2's 163" in flat
    assert "933 disagreement cells" in flat


def test_the_set_arithmetic_closes_with_nothing_left_over():
    t = ensemble.blindness_and_soundness_are_one_golden_free_knob()
    flat = " ".join(t.split())
    assert "the only two checks in the whole corpus that convict all seven " \
        "and still spare the reference" in flat
    assert "with nothing left over" in flat


def test_the_completeness_question_is_answered_negatively():
    t = ensemble.blindness_and_soundness_are_one_golden_free_knob()
    flat = " ".join(t.split())
    assert "you cannot" in flat
    assert "rather than a missing instrument" in flat


def test_the_one_knob_scope_is_stated():
    t = ensemble.blindness_and_soundness_are_one_golden_free_knob()
    assert "a different golden-free rule could in principle find a different" \
        in " ".join(t.split())


def test_the_complete_set_cannot_order_the_population():
    t = ensemble.a_complete_set_is_an_undrivable_one()
    flat = " ".join(t.split())
    assert "285 - 301" in flat
    assert "**5.4%**" in flat


def test_drivability_is_opposed_independently_of_soundness():
    t = ensemble.a_complete_set_is_an_undrivable_one()
    flat = " ".join(t.split())
    assert "independently of soundness" in flat.lower() or \
        "INDEPENDENTLY OF SOUNDNESS" in flat
    assert "not the same reason as the audit" in flat


def test_the_amendment_preceded_the_run_it_would_have_explained():
    t = ensemble.a_complete_set_is_an_undrivable_one()
    flat = " ".join(t.split())
    assert "amended in advance" in flat
    assert "rather than attributing the outcome to soundness after seeing it" \
        in flat


def test_the_raw_count_limit_is_scoped_to_the_raw_count():
    t = ensemble.a_complete_set_is_an_undrivable_one()
    flat = " ".join(t.split())
    assert "Spread is not the only way a set can steer" in flat
    assert "RAW COUNT" in flat


def test_the_stop_had_nothing_to_do_with_the_checks():
    t = ensemble.an_unspent_budget_is_not_evidence_about_the_set()
    flat = " ".join(t.split())
    assert "trial 2 of 21" in flat and "trial 0 of 21" in flat
    assert "ends the RUN" in flat


def test_a_harness_stop_is_indistinguishable_from_a_satisfied_one():
    t = ensemble.an_unspent_budget_is_not_evidence_about_the_set()
    flat = " ".join(t.split())
    assert "looks identical to a loop that finished early" in flat.lower()
    assert "Nothing in the artifacts distinguishes" in flat


def test_the_inference_is_retracted_and_the_earlier_runs_are_not():
    t = ensemble.an_unspent_budget_is_not_evidence_about_the_set()
    flat = " ".join(t.split())
    assert "neither is an instance of this" in flat
    assert "only when the run says, in its own record, what it stopped for" \
        in flat


def test_the_first_prescription_is_retracted():
    t = ensemble.an_unspent_budget_is_not_evidence_about_the_set()
    flat = " ".join(t.split())
    assert "THE FIRST FIX I WROTE DOWN WAS THE WRONG ONE" in flat
    assert "both stopped again the same way" in flat


def test_the_working_fix_removes_the_wait():
    t = ensemble.an_unspent_budget_is_not_evidence_about_the_set()
    flat = " ".join(t.split())
    assert "ORDINARY FOREGROUND COMMAND with an explicit long timeout" in flat
    assert "four to six minutes against a ten-minute maximum" in flat


def test_the_general_form_is_stated():
    t = ensemble.an_unspent_budget_is_not_evidence_about_the_set()
    flat = " ".join(t.split())
    assert "answers *how do I not have to*" in flat
    assert "Measure the unit against the maximum before reaching for " \
        "concurrency" in flat


def test_the_generalisation_is_retracted_not_the_measurement():
    t = ensemble.an_editor_cannot_locate_over_strictness_even_when_it_is_there()
    flat = " ".join(t.split())
    assert "IS RETRACTED" in flat
    assert "an_editor_can_locate_over_strictness_when_it_tests_the_claim" in flat
    assert "12 checks and been right about 8" in flat
    assert "what needs explaining rather than an average" in flat


def test_the_difference_is_testing_not_the_editor():
    t = ensemble.an_editor_cannot_locate_over_strictness_even_when_it_is_there()
    flat = " ".join(t.split())
    assert "they do not present identically to an EDIT" in flat


def test_the_editor_partitioned_the_survivors_exactly():
    t = ensemble.an_editor_can_locate_over_strictness_when_it_tests_the_claim()
    flat = " ".join(t.split())
    assert "PARTITIONED THE SURVIVORS EXACTLY" in flat
    assert "false accusations **0**" in flat


def test_the_flattering_base_rate_is_named_and_rejected():
    t = ensemble.an_editor_can_locate_over_strictness_when_it_tests_the_claim()
    flat = " ".join(t.split())
    assert "THE BASE RATE THAT MATTERS IS 64%, NOT 19%" in flat
    assert "the survivors are enriched" in flat
    assert "p = 0.003" in flat


def test_the_unaccused_four_are_credited_correctly():
    t = ensemble.an_editor_can_locate_over_strictness_when_it_tests_the_claim()
    flat = " ".join(t.split())
    assert "its diagnosis is wrong" in flat
    assert "it declined to convict them" in flat


def test_the_mechanism_is_that_a_gate_cannot_run_the_experiment():
    t = ensemble.an_editor_can_locate_over_strictness_when_it_tests_the_claim()
    flat = " ".join(t.split())
    assert "it cannot run the experiment" in flat
    assert "every one of them was a way of READING checks" in flat


def test_the_editor_scope_is_one_run():
    t = ensemble.an_editor_can_locate_over_strictness_when_it_tests_the_claim()
    flat = " ".join(t.split())
    assert "n = 11 survivors" in flat
    assert "a second run is what would turn a procedure into a method" in flat


def test_the_golden_free_set_landed_in_the_middle_band():
    t = ensemble.a_golden_free_set_did_not_out_drive_the_reference_selected_one()
    flat = " ".join(t.split())
    assert "-28%" in flat and "-32%" in flat
    assert "**-28% is the middle band**" in flat


def test_the_matched_pair_slope_does_not_extend():
    t = ensemble.a_golden_free_set_did_not_out_drive_the_reference_selected_one()
    flat = " ".join(t.split())
    assert "THE MATCHED PAIR'S SLOPE DOES NOT EXTEND" in flat
    assert "From 56.9% to 40.4% it separates nothing" in flat


def test_the_two_explanations_are_not_separated():
    t = ensemble.a_golden_free_set_did_not_out_drive_the_reference_selected_one()
    flat = " ".join(t.split())
    assert "a single point cannot distinguish" in flat
    assert "40% blind AND sound, which this corpus does not contain" in flat


def test_four_runs_are_not_ordered_by_blindness():
    t = ensemble.completeness_bought_with_unsoundness_drives_a_design_worse()
    flat = " ".join(t.split())
    assert "BLINDNESS DOES NOT ORDER THEM" in flat
    assert "beaten by one 57 points blinder" in flat


def test_splitting_by_soundness_resolves_the_order():
    t = ensemble.completeness_bought_with_unsoundness_drives_a_design_worse()
    flat = " ".join(t.split())
    assert "99.8% closes 3%, 56.9% closes 32%" in flat
    assert "40.4% closes 28% and 0.0% closes 14%" in flat
    assert "stops helping the moment it is spent" in flat


def test_the_goal_completeness_push_is_answered_negatively():
    t = ensemble.completeness_bought_with_unsoundness_drives_a_design_worse()
    flat = " ".join(t.split())
    assert "AND THE ANSWER IS NO" in flat
    assert "cost more than the completeness gains" in flat


def test_the_audit_cost_shows_up_as_a_rejected_repair():
    t = ensemble.completeness_bought_with_unsoundness_drives_a_design_worse()
    flat = " ".join(t.split())
    assert "970 consensus cells" in flat
    assert "it rejects right repairs" in flat


def test_the_floor_run_is_not_attributed_to_soundness():
    t = ensemble.completeness_bought_with_unsoundness_drives_a_design_worse()
    flat = " ".join(t.split())
    assert "cannot be attributed to soundness alone" in flat.lower()
    assert "pre-registered as uninterpretable between the two causes" in flat


def test_no_run_reached_equivalence():
    t = ensemble.completeness_bought_with_unsoundness_drives_a_design_worse()
    flat = " ".join(t.split())
    assert "orders four failures rather than finding a winner" in flat


def test_the_second_accusation_run_is_disclaimed():
    t = ensemble.a_second_accusation_run_carried_no_information()
    flat = " ".join(t.split())
    assert "NOT A SECOND CONFIRMATION" in flat
    assert "0.71" in flat and "0.003" in flat


def test_the_denominator_rule_is_stated():
    t = ensemble.a_second_accusation_run_carried_no_information()
    flat = " ".join(t.split())
    assert "the population the accuser could have drawn from" in flat
    assert "inverting which one carries evidence" in flat


def test_the_replication_is_still_owed():
    t = ensemble.a_second_accusation_run_carried_no_information()
    flat = " ".join(t.split())
    assert "REPLICATION IS STILL OWED" in flat
    assert "a wrong accusation is the default outcome" in flat


def test_the_hazard_is_named_precisely():
    t = ensemble.the_leak_rule_named_source_and_the_traces_were_next_door()
    flat = " ".join(t.split())
    assert "It names SOURCE" in flat
    assert "p4G/suite/results` holds the reference's 348" in flat


def test_the_hazard_was_checked_not_assumed():
    t = ensemble.the_leak_rule_named_source_and_the_traces_were_next_door()
    flat = " ".join(t.split())
    assert "CHECKED RATHER THAN ARGUED" in flat
    assert "zero accesses to `p4G/suite/results`" in flat
    assert "271, 241, 200 and 190" in flat


def test_the_fix_is_free_and_the_general_form_is_stated():
    t = ensemble.the_leak_rule_named_source_and_the_traces_were_next_door()
    flat = " ".join(t.split())
    assert "copies only `suite/tests` and `manifest.json`" in flat
    assert "names artifacts by KIND" in flat
    assert "then check the transcripts rather than trusting the wording" in flat


def test_the_top_band_was_cleared_and_is_not_claimed():
    t = ensemble.the_balanced_sample_was_balanced_in_labels_and_not_in_difficulty()
    flat = " ".join(t.split())
    assert "CORRECT 16 of 20" in flat and "p = 0.0059" in flat
    assert "IT CLEARED THE TOP BAND, AND THE BAND IS NOT CLAIMABLE" in flat


def test_the_control_names_the_free_half():
    t = ensemble.the_balanced_sample_was_balanced_in_labels_and_not_in_difficulty()
    flat = " ".join(t.split())
    assert "SEVEN OF THE TEN SOUND ITEMS NEVER CONVICT ANY DESIGN" in flat
    assert "the 50% coin the p-value is computed against does not exist" in flat


def test_there_is_no_lift_on_the_hard_items():
    t = ensemble.the_balanced_sample_was_balanced_in_labels_and_not_in_difficulty()
    flat = " ".join(t.split())
    assert "IT SCORED 10" in flat
    assert "Answering `OVER-STRICT` to all thirteen also scores 10" in flat
    assert "No measurable lift" in flat


def test_the_sampler_defect_and_its_fix_are_stated():
    t = ensemble.the_balanced_sample_was_balanced_in_labels_and_not_in_difficulty()
    flat = " ".join(t.split())
    assert "admits one that fires and only ever returns True" in flat
    assert "must convict at least one of the nine" in flat


def test_the_instrument_was_not_the_one_under_test():
    t = ensemble.the_balanced_sample_was_balanced_in_labels_and_not_in_difficulty()
    flat = " ".join(t.split())
    assert "spent **zero** of its 25 commit trials" in flat
    assert "does not replicate that run's method either" in flat


def test_the_replication_is_owed_a_third_time():
    t = ensemble.the_balanced_sample_was_balanced_in_labels_and_not_in_difficulty()
    flat = " ".join(t.split())
    assert "STILL OWED, FOR THE THIRD TIME" in flat


def test_the_pair_landed_blindness_down_and_audit_zero():
    t = ensemble.authoring_at_a_named_hole_closes_cells_that_selection_cannot()
    flat = " ".join(t.split())
    assert "**55.1%**" in flat and "56.9%" in flat
    assert "102 CELLS CLOSED AT AN AUDIT OF ZERO" in flat


def test_the_previous_authoring_round_is_the_null_it_beats():
    t = ensemble.authoring_at_a_named_hole_closes_cells_that_selection_cannot()
    flat = " ".join(t.split())
    assert "closed **exactly zero** new cells" in flat
    assert "Naming the cell is the difference" in flat


def test_the_corpus_finding_stands_and_the_generalisation_does_not():
    t = ensemble.authoring_at_a_named_hole_closes_cells_that_selection_cannot()
    flat = " ".join(t.split())
    assert "STANDS AND THE GENERALISATION I BUILT ON IT DOES NOT" in flat
    assert "a curve over SELECTIONS, and authoring moves off that curve" in flat


def test_the_authoring_rate_did_not_move():
    t = ensemble.authoring_at_a_named_hole_closes_cells_that_selection_cannot()
    flat = " ".join(t.split())
    assert "6 of 37 = 16%" in flat
    assert "naming the cell did not change how often an author lands" in flat


def test_the_mis_assignment_denominator_is_corrected():
    t = ensemble.authoring_at_a_named_hole_closes_cells_that_selection_cannot()
    flat = " ".join(t.split())
    assert "TEXT MENTIONED THE PORT" in flat
    assert "~29 answerable targets it is 21%" in flat
    assert "Both numbers, never one" in flat


def test_the_positive_is_a_rate_not_a_set():
    t = ensemble.authoring_at_a_named_hole_closes_cells_that_selection_cannot()
    flat = " ".join(t.split())
    assert "102 of 3,221 is 3% of the residue" in flat
    assert "a positive RATE, not a complete set" in flat


def test_the_fifth_run_is_the_best_drive_and_still_differs():
    t = ensemble.six_authored_checks_drove_a_design_further_than_any_selection()
    flat = " ".join(t.split())
    assert "279 -> **151 (43%)**" in flat
    assert "BEST-DRIVEN DESIGN ON THIS PLAN BY 39 TESTPOINTS" in flat
    assert "IT IS `DIFFERS`" in flat


def test_zero_at_audit_zero_is_explained_by_blindness_not_thinness():
    t = ensemble.six_authored_checks_drove_a_design_further_than_any_selection()
    flat = " ".join(t.split())
    assert "ZERO STILL DOES NOT MEAN EQUIVALENT" in flat
    assert "3,119 of 5,656 disagreement cells -- 55.1% -- are invisible" in flat
    assert "Blindness and the residual divergence are the same fact" in flat


def test_the_attribution_is_a_fixed_design_not_two_runs():
    t = ensemble.six_authored_checks_drove_a_design_further_than_any_selection()
    flat = " ".join(t.split())
    assert "TWO OF THE SIX CONVICT THE DESIGN CEIL2's OWN RUN STOPPED ON" in flat
    assert "REQ-0029@dc_addr" in flat and "REQ-0087@biu_read" in flat
    assert "with no editor in the loop" in flat


def test_blindness_is_a_poor_unit_of_account_at_the_margin():
    t = ensemble.six_authored_checks_drove_a_design_further_than_any_selection()
    flat = " ".join(t.split())
    assert "BLINDNESS DID NOT PREDICT THE IMPROVEMENT" in flat
    assert "1.8 points of blindness** and by **39 testpoints of drive" in flat
    assert "report the cells closed and which they were, not the percentage" in flat


def test_the_unspent_budget_is_not_read_as_an_editor_limit():
    t = ensemble.six_authored_checks_drove_a_design_further_than_any_selection()
    flat = " ".join(t.split())
    assert "spent 10 of 21 trials" in flat
    assert "evidence the set stopped asking" in flat


def test_the_second_draw_is_the_tell():
    t = ensemble.the_authoring_round_was_capped_by_a_regex_not_by_the_holes()
    flat = " ".join(t.split())
    assert "yields **ONE**" in flat
    assert "never a sample of the residue" in flat
    assert "draw the sample twice" in flat


def test_the_normalized_map_is_a_strict_superset():
    t = ensemble.the_authoring_round_was_capped_by_a_regex_not_by_the_holes()
    flat = " ".join(t.split())
    assert "**TOTAL** **38** **237** **199**" in flat
    assert "REACHED 16% OF WHAT THE PIPELINE ALREADY KNEW" in flat
    assert "their union is 237" in flat


def test_one_shortcut_erred_in_both_directions():
    t = ensemble.the_authoring_round_was_capped_by_a_regex_not_by_the_holes()
    flat = " ".join(t.split())
    assert "over-matched" in flat and "under-matched" in flat
    assert "wrong in both directions at once" in flat


def test_the_round_one_numbers_are_not_revised():
    t = ensemble.the_authoring_round_was_capped_by_a_regex_not_by_the_holes()
    flat = " ".join(t.split())
    assert "The round's own numbers are unchanged" in flat
    assert "is a separate measurement and is not claimed here" in flat


def test_four_designs_estimate_blindness_as_well_as_nine():
    t = ensemble.blindness_saturates_at_four_designs_and_two_can_read_zero()
    flat = " ".join(t.split())
    assert "FOUR INDEPENDENTLY WRITTEN DESIGNS ESTIMATE A SET'S BLINDNESS AS WELL AS NINE" in flat
    assert "**4** **55.1%** **42.0%**" in flat


def test_a_small_population_can_read_a_clean_sheet():
    t = ensemble.blindness_saturates_at_four_designs_and_two_can_read_zero()
    flat = " ".join(t.split())
    assert "TWO DESIGNS CAN READ ZERO ON A SET THAT IS 43% BLIND" in flat
    assert "0 of 23, a clean sheet" in flat
    assert "the per-pair spread reported beside the aggregate, never the aggregate alone" in flat


def test_accepted_designs_are_worth_twelve_points():
    t = ensemble.blindness_saturates_at_four_designs_and_two_can_read_zero()
    flat = " ".join(t.split())
    assert "42.9% -> 55.1%, twelve points" in flat
    assert "adversarially selected against the checks by construction" in flat


def test_a_trustworthy_instrument_is_not_a_good_number():
    t = ensemble.blindness_saturates_at_four_designs_and_two_can_read_zero()
    flat = " ".join(t.split())
    assert "Saturation of the ESTIMATE is not completeness of the SET" in flat
    assert "four is what it took here, not a constant" in flat


def test_the_largest_blindness_drop_is_a_negative():
    t = ensemble.the_biggest_blindness_drop_here_was_bought_entirely_with_false_rejection()
    flat = " ".join(t.split())
    assert "1,293 CELLS -- BLINDNESS 55.1% -> 32.3%" in flat
    assert "THE AUDIT IS 2 OF 2" in flat
    assert "EVERY ONE OF THOSE 1,293 CELLS WAS BOUGHT WITH FALSE REJECTION" in flat


def test_the_minority_rule_cannot_see_the_sentence():
    t = ensemble.the_biggest_blindness_drop_here_was_bought_entirely_with_false_rejection()
    flat = " ".join(t.split())
    assert "Both checks convict **2 of 7**" in flat
    assert "its audit was **0 of 6**" in flat
    assert "Same rule, same threshold, same population, opposite outcome" in flat
    assert "Requirement specificity is a golden-free property" in flat


def test_a_scaffolding_sentence_makes_the_author_invent():
    t = ensemble.the_biggest_blindness_drop_here_was_bought_entirely_with_false_rejection()
    flat = " ".join(t.split())
    assert "A SCAFFOLDING SENTENCE LICENSES NOTHING, SO THE AUTHOR INVENTS AN OBLIGATION" in flat
    assert "cannot read whether the check's own requirement gave it anything to say" in flat


def test_the_broad_arm_is_labelled_as_the_control():
    t = ensemble.the_biggest_blindness_drop_here_was_bought_entirely_with_false_rejection()
    flat = " ".join(t.split())
    assert "It is the BROAD arm and it was run by accident" in flat
    assert "This round becomes its control" in flat


def test_the_two_arms_are_both_negatives():
    t = ensemble.authoring_at_a_named_hole_does_not_escape_the_soundness_trade()
    flat = " ".join(t.split())
    assert "ONE END BUYS 1,293 CELLS AT A 100% FALSE-REJECT RATE; THE OTHER BUYS NOTHING AT ZERO" in flat
    assert "76 calls on the corrected targeting closed ZERO cells soundly" in flat


def test_the_anti_correlation_is_measured_inside_authoring():
    t = ensemble.authoring_at_a_named_hole_does_not_escape_the_soundness_trade()
    flat = " ".join(t.split())
    assert "n= 4 mean 74 cells" in flat and "n=65 mean 638 cells" in flat
    assert "Spearman(cells objected, designs convicted) = **+0.350**" in flat
    assert "EXACTLY THE ONES THE GOLDEN-FREE SOUNDNESS RULE REJECTS" in flat


def test_the_round_one_positive_is_re_read_not_retracted():
    t = ensemble.authoring_at_a_named_hole_does_not_escape_the_soundness_trade()
    flat = " ".join(t.split())
    assert "**17 each**, inside the kept band's own mean of 74" in flat
    assert "a sound hole-closer is **writable** where the corpus contains none" in flat
    assert "What is now refuted is the reading I put next to it" in flat


def test_the_projected_cost_is_stated():
    t = ensemble.authoring_at_a_named_hole_does_not_escape_the_soundness_trade()
    flat = " ".join(t.split())
    assert "**250 to 3,600 authoring calls**" in flat
    assert "the rate fell from 16% to 5% between the rounds" in flat


def test_the_rejected_checks_are_not_dismissed_as_wrong():
    t = ensemble.authoring_at_a_named_hole_does_not_escape_the_soundness_trade()
    flat = " ".join(t.split())
    assert "The 65 rejected checks are not obviously wrong" in flat
    assert "right on average and wrong exactly where the residue is" in flat


def test_the_hedge_about_the_rejected_checks_is_retracted():
    t = ensemble.the_blindness_residue_is_closeable_and_almost_none_of_it_soundly()
    flat = " ".join(t.split())
    assert "A HEDGE OF MINE, REFUTED BY MEASUREMENT" in flat
    assert "**0 of 65 spare the reference.**" in flat
    assert "which is where I said it would fail" in flat


def test_every_blind_cell_is_closeable():
    t = ensemble.the_blindness_residue_is_closeable_and_almost_none_of_it_soundly()
    flat = " ".join(t.split())
    assert "**closed by NOTHING among the 76 authored** **0** **0.0%**" in flat
    assert "EVERY BLIND CELL IS CLOSEABLE" in flat
    assert "The author is not failing to reach the cells" in flat


def test_the_soundly_closeable_share_is_the_headline():
    t = ensemble.the_blindness_residue_is_closeable_and_almost_none_of_it_soundly()
    flat = " ".join(t.split())
    assert "**0 of 3,119 = 0.00%**" in flat
    assert "EVERY TIME THE CHECK IT WRITES CONVICTS A CORRECT DESIGN" in flat


def test_the_zero_point_seven_percent_is_retracted():
    """Pins the correction so it cannot be silently undone."""
    t = ensemble.the_blindness_residue_is_closeable_and_almost_none_of_it_soundly()
    flat = " ".join(t.split())
    assert "A CORRECTION, AND IT IS MINE" in flat
    assert "The first version of this finding read **21 of 3,119 = 0.7%**" in flat
    assert "counts EVERY cell they object on, blind or not" in flat
    assert "moved blindness by exactly nothing, 3,119 to 3,119" in flat


def test_the_named_cell_leg_was_never_implemented():
    t = ensemble.the_blindness_residue_is_closeable_and_almost_none_of_it_soundly()
    flat = " ".join(t.split())
    assert "the named-cell leg was never coded" in flat
    assert "Zero of 76 checks both closed the cell it was given and spared the reference" in flat


def test_the_partition_is_golden_free_and_the_audit_only_calibrates():
    t = ensemble.the_blindness_residue_is_closeable_and_almost_none_of_it_soundly()
    flat = " ".join(t.split())
    assert "The partition above needs no reference" in flat
    assert "a pipeline with no golden CAN determine that a cell is irreducibly blind" in flat
    assert "What it cannot do is close it anyway" in flat


def test_blindness_should_be_reported_as_a_pair():
    t = ensemble.the_blindness_residue_is_closeable_and_almost_none_of_it_soundly()
    flat = " ".join(t.split())
    assert "On this evidence **none of it is**" in flat
    assert "residue, and the share of it any check could soundly close" in flat


def test_the_floor_is_named_as_a_floor():
    t = ensemble.the_blindness_residue_is_closeable_and_almost_none_of_it_soundly()
    flat = " ".join(t.split())
    assert "76 checks is a cover, not an exhaustive search" in flat
    assert "0.00% is a floor and the gap between it and the truth is unmeasured" in flat


def test_narrowing_lands_zero_against_a_fifteen_percent_prior():
    t = ensemble.narrowing_the_hole_closers_moved_the_conviction_count_by_nothing()
    flat = " ".join(t.split())
    assert "**7 of 47 = 15%**" in flat
    assert "**BOTH -- the pre-registered measure** **0 of 30**" in flat
    assert "STILL CLOSES its own named cell 29 of 30" in flat


def test_the_conviction_count_did_not_move():
    t = ensemble.narrowing_the_hole_closers_moved_the_conviction_count_by_nothing()
    flat = " ".join(t.split())
    assert "28 of 30 went 7-of-7 to **7-of-7**" in flat
    assert "One went 6-of-7 to 7-of-7 -- *stricter*" in flat
    assert "OVER-STRICTNESS IS NOT AN ACCRETION OF REMOVABLE EXTRAS" in flat


def test_the_rule_and_the_audit_agree_on_ninety_five():
    t = ensemble.narrowing_the_hole_closers_moved_the_conviction_count_by_nothing()
    flat = " ".join(t.split())
    assert "29 OF 30 CONVICT THE REFERENCE" in flat
    assert "agree on 95 of 95 checks authored at this residue" in flat
    assert "The rule is not discarding completeness. There is none to discard." in flat


def test_the_remaining_reading_is_the_specifications():
    t = ensemble.narrowing_the_hole_closers_moved_the_conviction_count_by_nothing()
    flat = " ".join(t.split())
    assert "violated by all seven independent implementations AND by the reference" in flat
    assert "the requirement text and the design disagreeing" in flat


def test_the_preregistered_band_is_honoured_and_the_route_closed():
    t = ensemble.narrowing_the_hole_closers_moved_the_conviction_count_by_nothing()
    flat = " ".join(t.split())
    assert "`<= 1` BAND: 0.00% IS NOT A FLOOR, IT IS CLOSE TO THE TRUTH" in flat
    assert "selection, authoring, narrowing -- and all three are now closed" in flat
    assert "a decision on the underdetermined cells from outside" in flat


def test_one_set_is_complete_on_some_testpoints_and_blind_on_others():
    t = ensemble.blindness_is_a_property_of_the_stimulus_too_and_it_predicts()
    flat = " ".join(t.split())
    assert "PERFECTLY COMPLETE ON 61 TESTPOINTS AND PERFECTLY BLIND ON 70" in flat
    assert "property of the (check set, stimulus) PAIR" in flat
    assert "every figure on this plan has attributed it to the set alone" in flat


def test_the_golden_free_class_predicts_the_grade():
    t = ensemble.blindness_is_a_property_of_the_stimulus_too_and_it_predicts()
    flat = " ".join(t.split())
    assert "MONOTONE ACROSS ALL FOUR CLASSES, 1% TO 86%, AND 3.5x BETWEEN THE EXTREMES" in flat
    assert "135 of the 151 differing testpoints -- 89% -- are partly or fully blind" in flat


def test_the_consensus_accuracy_reproduces_per_testpoint():
    t = ensemble.blindness_is_a_property_of_the_stimulus_too_and_it_predicts()
    flat = " ".join(t.split())
    assert "matches the reference on 90 of 91 testpoints" in flat
    assert "arriving again per TESTPOINT from a different direction" in flat


def test_the_metric_gaming_route_is_forbidden_explicitly():
    t = ensemble.blindness_is_a_property_of_the_stimulus_too_and_it_predicts()
    flat = " ".join(t.split())
    assert "does NOT license adding easy testpoints to move the ratio" in flat
    assert "which is metric gaming and would be caught by the absolute count" in flat


def test_the_closed_levers_are_reframed_not_reopened():
    t = ensemble.blindness_is_a_property_of_the_stimulus_too_and_it_predicts()
    flat = " ".join(t.split())
    assert "95 of 95 attempts convict the reference. That stands." in flat
    assert "nothing has tested whether another stimulus produces better ones" in flat


def test_the_same_ports_appear_in_both_classes():
    t = ensemble.the_blind_testpoints_differ_from_the_caught_ones_by_scenario_not_only_port()
    flat = " ".join(t.split())
    assert "**0.372**" in flat
    assert "8 of the 10 ports carry more than 2% in BOTH classes" in flat
    assert "IT IS BOTH, AND THE SCENARIO HALF IS THE LARGER ONE" in flat


def test_biu_write_is_named_as_the_port_component():
    t = ensemble.the_blind_testpoints_differ_from_the_caught_ones_by_scenario_not_only_port()
    flat = " ".join(t.split())
    assert "40.5% of blind disagreements against 8.0% of caught ones" in flat
    assert "the store write-through path is where it collects" in flat


def test_the_earlier_stimulus_sizing_is_distinguished_not_contradicted():
    t = ensemble.the_blind_testpoints_differ_from_the_caught_ones_by_scenario_not_only_port()
    flat = " ".join(t.split())
    assert "the stimulus loop is worth 3 checks of 50" in flat
    assert "That answer stands and does not bear on this" in flat


def test_the_sizing_does_not_claim_the_experiment():
    t = ensemble.the_blind_testpoints_differ_from_the_caught_ones_by_scenario_not_only_port()
    flat = " ".join(t.split())
    assert "does NOT mean a stimulus author can reach the caught kind on demand" in flat
    assert "That is not run here" in flat
    assert "the concentration is a co-occurrence, not a cause".upper() in flat.upper()


def test_the_stimulus_round_lands_in_the_closing_band():
    t = ensemble.a_different_route_to_the_same_scenario_is_blinder_not_clearer()
    flat = " ".join(t.split())
    assert "**fully caught, of the 20 that disagree : 1 = 5%**" in flat
    assert "`< 15%` BAND: THE STIMULUS LOOP IS CLOSED AS A LEVER ON BLINDNESS" in flat


def test_the_new_testpoints_are_blinder_than_the_old_suite():
    t = ensemble.a_different_route_to_the_same_scenario_is_blinder_not_clearer()
    flat = " ".join(t.split())
    assert "**326 of 386 = 84.5%**" in flat
    assert "The blindness travels with the scenario, not with the route" in flat


def test_no_new_testpoint_was_inert():
    t = ensemble.a_different_route_to_the_same_scenario_is_blinder_not_clearer()
    flat = " ".join(t.split())
    assert "**INERT: 0 of 20**" in flat
    assert "was the pre-registered failure mode and did not occur" in flat


def test_all_four_levers_are_closed_by_measurement():
    t = ensemble.a_different_route_to_the_same_scenario_is_blinder_not_clearer()
    flat = " ".join(t.split())
    assert ("selection over the corpus, authoring at named holes, narrowing the "
            "over-strict closers, and the stimulus") in flat
    assert "closed by measurement rather than by a budget running out" in flat


def test_the_sample_selection_effect_is_stated():
    t = ensemble.a_different_route_to_the_same_scenario_is_blinder_not_clearer()
    flat = " ".join(t.split())
    assert "chosen deliberately as the WORST scenarios" in flat
    assert "this does not measure that" in flat


def test_the_ratio_was_not_allowed_to_be_the_headline():
    t = ensemble.a_different_route_to_the_same_scenario_is_blinder_not_clearer()
    flat = " ".join(t.split())
    assert "these add 326 more" in flat
    assert "a suite can always be made to look less blind by adding testpoints it happens to catch" in flat


def test_the_population_vote_points_the_wrong_way_on_the_named_cells():
    t = ensemble.the_population_vote_is_inverted_on_one_port_and_perfect_on_another()
    flat = " ".join(t.split())
    assert "**20 times = 33%**" in flat
    assert "the vote there points the WRONG WAY" in flat


def test_the_blindness_version_of_the_effect_is_refused_as_confounded():
    """The tidy 33%-against-95% headline is port composition. If this text ever
    stops saying so, the finding has become the overclaim it was written to
    avoid."""
    t = ensemble.the_population_vote_is_inverted_on_one_port_and_perfect_on_another()
    flat = " ".join(t.split())
    assert "**That 62-point separation is PORT COMPOSITION and must not be quoted" in flat
    assert "130 of 187 `burst`, whose majority is right 130 of 130" in flat


def test_the_effect_reverses_between_two_ports():
    t = ensemble.the_population_vote_is_inverted_on_one_port_and_perfect_on_another()
    flat = " ".join(t.split())
    assert "**3/47 =  6%**" in " ".join(t.split("\n"))  # table row, spacing kept
    assert "6%" in flat and "100%" in flat
    assert "SWINGS FROM 6% TO 100% BETWEEN TWO PORTS AT THE SAME MARGIN" in flat
    assert "Blindness is not that feature" in flat


def test_the_margin_does_not_rescue_the_vote():
    t = ensemble.the_population_vote_is_inverted_on_one_port_and_perfect_on_another()
    flat = " ".join(t.split())
    assert "at a majority of 8 of 9 the blind cells read 34% and the others 97%" in flat


def test_the_decode_integrity_check_travels_with_the_six_percent():
    """A port-specific decode defect produces exactly this shape, so the figure
    is not quotable without the unanimity check beside it."""
    t = ensemble.the_population_vote_is_inverted_on_one_port_and_perfect_on_another()
    flat = " ".join(t.split())
    assert "NOT A DECODE DEFECT ON ONE PORT" in flat
    assert "**97.63%**" in flat
    assert "the 6% is the population being wrong" in flat


def test_the_disagreement_itself_is_not_written_off():
    t = ensemble.the_population_vote_is_inverted_on_one_port_and_perfect_on_another()
    flat = " ".join(t.split())
    assert "at most one side of a split can be right" in flat
    assert "It says the COUNTS cannot pick the side" in flat


def test_the_sixth_graded_run_lands_in_the_variance_band():
    t = ensemble.the_disagreement_report_did_not_move_the_cells_it_named()
    flat = " ".join(t.split())
    assert "**146 of 348**" in flat
    assert "PRE-REGISTERED `121-160` BAND: NO EFFECT DISTINGUISHABLE FROM RUN-TO-RUN VARIANCE" in flat


def test_the_named_cells_got_worse_not_better():
    """The whole point of the arm. If this ever reads as a gain, the finding has
    been inverted."""
    t = ensemble.the_disagreement_report_did_not_move_the_cells_it_named()
    flat = " ".join(t.split())
    assert "**54/60 = 90%** **+1 WORSE**" in flat
    assert "THE AGGREGATE GAIN IS ENTIRELY OUTSIDE THE REPORT" in flat


def test_the_undersized_control_is_not_quoted():
    t = ensemble.the_disagreement_report_did_not_move_the_cells_it_named()
    flat = " ".join(t.split())
    assert "difference-in-differences is not quoted, as registered" in flat
    assert "the NAMED group carries it at n = 60" in flat


def test_the_editors_reading_is_confirmed_and_its_conclusion_refuted():
    t = ensemble.the_disagreement_report_did_not_move_the_cells_it_named()
    flat = " ".join(t.split())
    assert "**59 of 60 already matched its design's behaviour" in flat
    assert "was wrong 90% of the time" in flat
    assert "**16 trials unspent**" in flat


def test_the_shared_misreading_is_not_a_shortage_of_context():
    t = ensemble.the_disagreement_report_did_not_move_the_cells_it_named()
    flat = " ".join(t.split())
    assert "reproduced the population's wrong answer 7 times in 9" in flat
    assert "adding the disagreement did not decorrelate it" in flat


def test_the_disagreement_is_still_evidence_even_though_the_lever_is_closed():
    t = ensemble.the_disagreement_report_did_not_move_the_cells_it_named()
    flat = " ".join(t.split())
    assert "What is NOT closed is that the disagreement is evidence" in flat
    assert "What is refuted is that handing that split to a spec-reading editor resolves it" in flat


def test_the_oscillation_is_recorded_with_the_rejected_commits():
    t = ensemble.the_disagreement_report_did_not_move_the_cells_it_named()
    assert "**27**" in t and "**rejected**" in t
    assert "1**           2,840        latched" in t


def test_the_monotone_four_class_predictor_is_withdrawn():
    t = ensemble.the_monotone_predictor_is_a_two_point_instrument()
    flat = " ".join(t.split())
    assert "THE MONOTONE ORDERING DOES NOT HOLD OUT OF SAMPLE" in flat
    assert "**The four-point predictor is withdrawn.**" in flat


def test_the_two_endpoints_survive_out_of_sample():
    t = ensemble.the_monotone_predictor_is_a_two_point_instrument()
    flat = " ".join(t.split())
    assert "**1% in both runs**" in flat
    assert "**86% and 87%**" in flat
    assert "a two-point instrument, not a ranking" in flat


def test_caught_does_not_mean_the_set_catches_this_designs_errors():
    t = ensemble.the_monotone_predictor_is_a_two_point_instrument()
    flat = " ".join(t.split())
    assert "differs from the reference on **29**" in flat
    assert "**ONE objection in the entire suite**" in flat
    assert "It says nothing about whether it catches the errors of the design under test" in flat


def test_the_fitted_finding_carries_its_own_refutation():
    """A correction that lives only in the correcting function is a correction a
    reader of the original will never see."""
    t = ensemble.blindness_is_a_property_of_the_stimulus_too_and_it_predicts()
    flat = " ".join(t.split())
    assert "CORRECTED OUT OF SAMPLE, AND THE MONOTONE SHAPE DOES NOT SURVIVE" in flat
    assert "the_monotone_predictor_is_a_two_point_instrument" in flat
    assert "Quote the endpoints; do not quote the ranking" in flat


def test_the_middle_inversion_is_not_sold_as_a_mechanism():
    t = ensemble.the_monotone_predictor_is_a_two_point_instrument()
    flat = " ".join(t.split())
    assert "Two runs is not enough to call that a trade" in flat


def test_the_population_is_five_opinions_not_nine():
    t = ensemble.the_population_is_five_opinions_not_nine_and_dedup_recovers_the_vote()
    flat = " ".join(t.split())
    assert "DESIGNS B, D, E, F AND H PRODUCE IDENTICAL VALUES" in flat
    assert "**FIVE distinct opinions**" in flat


def test_the_majority_is_structurally_the_bloc():
    t = ensemble.the_population_is_five_opinions_not_nine_and_dedup_recovers_the_vote()
    flat = " ".join(t.split())
    assert "A MAJORITY OVER NINE IS STRUCTURALLY THE BLOC'S ANSWER, ALWAYS" in flat
    assert "Adding a tenth design drawn from the same distribution makes it worse" in flat


def test_dedup_is_golden_free_and_unfitted():
    t = ensemble.the_population_is_five_opinions_not_nine_and_dedup_recovers_the_vote()
    flat = " ".join(t.split())
    assert "DEDUP IS GOLDEN-FREE AND HAS NO FITTED PARAMETER" in flat
    assert "**56% -> 73%**" in flat
    assert "4% of its decisions are ties broken by order" in flat


def test_least_k_is_labelled_a_calibration_not_a_score():
    """k was chosen by reading the audit. If this ever reads as golden-free, the
    distinction rule C carries has been lost."""
    t = ensemble.the_population_is_five_opinions_not_nine_and_dedup_recovers_the_vote()
    flat = " ".join(t.split())
    assert "it is a CALIBRATION exactly as rule C's threshold at two is, not a score" in flat


def test_nothing_helps_on_the_first_split_cells():
    t = ensemble.the_population_is_five_opinions_not_nine_and_dedup_recovers_the_vote()
    flat = " ".join(t.split())
    assert "EVERY RULE TIES AT 38%, INCLUDING THE CEILING" in flat
    assert "the report was drawn from the one sample on which no rule over this population beats any other" in flat


def test_independently_written_is_priced():
    t = ensemble.the_population_is_five_opinions_not_nine_and_dedup_recovers_the_vote()
    flat = " ".join(t.split())
    assert "produced five opinions where the checks are blind" in flat
    assert "a bloc of five wearing the authority of nine" in flat


def test_the_seventh_run_drove_the_design_away():
    t = ensemble.unscored_evidence_does_not_move_an_editor()
    flat = " ".join(t.split())
    assert "**214 of 348**" in flat
    assert "PRE-REGISTERED `> 160` BAND: THE RUN DROVE THE DESIGN AWAY" in flat


def test_the_editor_did_not_use_the_corrected_report():
    t = ensemble.unscored_evidence_does_not_move_an_editor()
    flat = " ".join(t.split())
    assert "**ADOPTED the leading reading at 1**" in flat
    assert "**KEPT its own value at 96**" in flat
    assert "it is the editor's check-driven structural edits, with the report inert" in flat


def test_the_over_claim_is_retracted_in_the_finding_itself():
    """I called 91-of-97 the strongest lever on the plan before running it. If
    this text ever stops saying that was an over-claim, the retraction is lost."""
    t = ensemble.unscored_evidence_does_not_move_an_editor()
    flat = " ".join(t.split())
    assert "**That was an over-claim.**" in flat
    assert "an editor cannot change a cell" in flat.lower()


def test_the_better_report_was_used_less_not_more():
    t = ensemble.unscored_evidence_does_not_move_an_editor()
    flat = " ".join(t.split())
    assert "the report built to fix run 6's defects was used LESS, not more" in flat
    assert "An editor optimises what is scored" in flat


def test_the_untested_option_is_named_without_being_claimed():
    t = ensemble.unscored_evidence_does_not_move_an_editor()
    flat = " ".join(t.split())
    assert "putting the de-duplicated disagreement IN THE LATCH" in flat
    assert "This finding does not claim that would work" in flat


def test_the_perfect_golden_free_score_produced_the_worst_design():
    t = ensemble.a_criterion_cannot_take_a_design_past_its_own_accuracy()
    flat = " ".join(t.split())
    assert "DRIVEN TO A PERFECT SCORE AND THE DESIGN IS THE WORST OF THE EIGHT RUNS" in flat
    assert "**221 of 348**" in flat


def test_the_scored_region_itself_got_worse():
    t = ensemble.a_criterion_cannot_take_a_design_past_its_own_accuracy()
    flat = " ".join(t.split())
    assert "IT GOT WORSE ON EXACTLY THE REGION IT SCORES" in flat
    assert "**61 -> 66 differing**" in flat
    assert "worse than the run with no such latch at all" in flat


def test_the_design_inherits_the_readings_error_rate_exactly():
    t = ensemble.a_criterion_cannot_take_a_design_past_its_own_accuracy()
    flat = " ".join(t.split())
    assert "**2,070 = 54%**" in flat and "**2,209 = 58%**" in flat
    assert "accuracy equals the reading's TO THE CELL" in flat
    assert "the accepted design is right at **0**" in flat


def test_the_coordinate_system_defect_is_owned():
    """The 73% that motivated the arm was on transactional rows; the latch used
    raw edges, where the same reading is 54%. If this stops being stated, the
    run reads as an unlucky negative rather than a predictable one."""
    t = ensemble.a_criterion_cannot_take_a_design_past_its_own_accuracy()
    flat = " ".join(t.split())
    assert "measured on TRANSACTIONAL ROWS; the latch was built on RAW EDGES" in flat
    assert "knowable before the run from data already on disk" in flat


def test_the_population_ceiling_is_stated_as_a_number():
    t = ensemble.a_criterion_cannot_take_a_design_past_its_own_accuracy()
    flat = " ".join(t.split())
    assert "54% accurate where the checks are blind" in flat
    assert "no criterion built from it can certify a design better than that" in flat


def test_the_dedup_reversal_is_stated_in_both_denominators():
    t = ensemble.whether_dedup_helps_the_vote_depends_entirely_on_the_denominator()
    flat = " ".join(t.split())
    assert "**82%**" in flat and "**54%**" in flat
    assert "HELPS by 17 points in one weighting and HURTS by 28 in the other" in flat
    assert "neither figure is quotable without its denominator" in flat.lower()


def test_the_bloc_is_the_most_accurate_group_not_a_defect():
    t = ensemble.whether_dedup_helps_the_vote_depends_entirely_on_the_denominator()
    flat = " ".join(t.split())
    assert "**G 20%**" in flat
    assert "the most accurate group in the population" in flat
    assert "its multiplicity is exactly what made the plain majority good" in flat


def test_the_structural_claim_survives_and_the_fix_claim_does_not():
    t = ensemble.whether_dedup_helps_the_vote_depends_entirely_on_the_denominator()
    flat = " ".join(t.split())
    assert "The structural observation stands" in flat
    assert "What is withdrawn is that correcting for it improves the reading" in flat


def test_the_dedup_finding_carries_its_own_correction():
    """A correction that lives only in the correcting function is one the
    original's reader never sees."""
    t = ensemble.the_population_is_five_opinions_not_nine_and_dedup_recovers_the_vote()
    flat = " ".join(t.split())
    assert "WHETHER DE-DUPLICATION HELPS DEPENDS ENTIRELY ON THE DENOMINATOR" in flat
    assert "is WITHDRAWN" in flat
    assert "whether_dedup_helps_the_vote_depends_entirely_on_the_denominator" in flat


def test_the_eighth_run_is_explained_by_the_wrong_reading():
    t = ensemble.whether_dedup_helps_the_vote_depends_entirely_on_the_denominator()
    flat = " ".join(t.split())
    assert "I chose the one reading below the design's own accuracy" in flat
    assert "confirmed and was applied to the wrong reading" in flat


def test_the_ninth_run_is_the_worst_of_the_nine():
    t = ensemble.a_proxys_aggregate_accuracy_is_not_its_effective_accuracy()
    flat = " ".join(t.split())
    assert "**271 of 348 testpoints differing**" in flat
    assert "the route is closed on both" in flat


def test_the_mechanism_check_failed_informatively():
    t = ensemble.a_proxys_aggregate_accuracy_is_not_its_effective_accuracy()
    flat = " ".join(t.split())
    assert "**FELL, 58% -> 53%**" in flat
    assert "improving substantially while its own region gets less accurate" in flat


def test_the_editor_repaired_the_units_where_the_reading_is_worst():
    t = ensemble.a_proxys_aggregate_accuracy_is_not_its_effective_accuracy()
    flat = " ".join(t.split())
    assert "REPAIRED EXACTLY THE UNITS WHERE THE READING IS WORST" in flat
    assert "17% against 94%" in flat


def test_the_general_law_is_stated_with_its_mechanism():
    t = ensemble.a_proxys_aggregate_accuracy_is_not_its_effective_accuracy()
    flat = " ".join(t.split())
    assert "AGGREGATE ACCURACY IS NOT ITS EFFECTIVE ACCURACY" in flat
    assert "accuracy on the subset an optimiser can actually MOVE" in flat
    assert "easiest to satisfy exactly where it is most wrong" in flat


def test_the_three_pricing_errors_are_owned_as_one():
    t = ensemble.a_proxys_aggregate_accuracy_is_not_its_effective_accuracy()
    flat = " ".join(t.split())
    assert "the same one three times" in flat.lower()
    assert "a statement about cells that ignored what an optimiser does with them" in flat


def test_the_stimulus_opportunity_is_zero_on_three_designs():
    t = ensemble.the_stimulus_loop_has_zero_opportunity_and_the_editor_consumes_the_strength()
    flat = " ".join(t.split())
    assert "THE STIMULUS OPPORTUNITY IS ZERO ON ALL THREE" in flat
    assert "0 of 146, 0 of 151 and 0 of 279" in flat


def test_the_fourth_class_is_zero_too():
    """`no check watches a wrong port` being zero is what makes the claim total
    rather than partial."""
    t = ensemble.the_stimulus_loop_has_zero_opportunity_and_the_editor_consumes_the_strength()
    flat = " ".join(t.split())
    assert "no check watches a wrong port at all -- is **also zero**" in flat


def test_the_editor_consumes_the_discriminating_power():
    t = ensemble.the_stimulus_loop_has_zero_opportunity_and_the_editor_consumes_the_strength()
    flat = " ".join(t.split())
    assert "**6.4% -> 0.4% -> 0.0%**" in flat
    assert "THE EDITOR CONSUMES THE SET'S DISCRIMINATING POWER" in flat


def test_the_residue_is_named_as_strength_alone():
    t = ensemble.the_stimulus_loop_has_zero_opportunity_and_the_editor_consumes_the_strength()
    flat = " ".join(t.split())
    assert "The residue is check STRENGTH and only check strength" in flat
    assert "0.4% of 4,529 exposed decisions" in flat


def test_strength_is_shown_to_cost_soundness():
    t = ensemble.the_stimulus_loop_has_zero_opportunity_and_the_editor_consumes_the_strength()
    flat = " ".join(t.split())
    assert "**23 of 34 began convicting the reference**" in flat
    assert "**0 of 34**" in flat


def test_the_claim_is_bounded_to_this_set():
    t = ensemble.the_stimulus_loop_has_zero_opportunity_and_the_editor_consumes_the_strength()
    flat = " ".join(t.split())
    assert "does NOT claim is that stimulus is worthless in general" in flat


def test_no_sound_corpus_check_is_missing_from_the_set():
    t = ensemble.the_set_is_complete_over_the_corpus_and_the_corpus_is_the_limit()
    flat = " ".join(t.split())
    assert "NOT ONE SOUND CHECK IN 640 CORPUS BODIES IS MISSING FROM THE SET" in flat
    assert "Selection is exhausted -- provably, not by inference" in flat


def test_the_corpus_sees_the_design_but_cannot_say_it_soundly():
    t = ensemble.the_set_is_complete_over_the_corpus_and_the_corpus_is_the_limit()
    flat = " ".join(t.split())
    assert "**301 of those 302 buy the catch by also convicting the reference.**" in flat
    assert "three hundred ways and can say so soundly in exactly one" in flat


def test_the_sound_catch_count_collapses_as_the_editor_works():
    t = ensemble.the_set_is_complete_over_the_corpus_and_the_corpus_is_the_limit()
    flat = " ".join(t.split())
    assert "THE SOUND COLUMN FALLS AS THE EDITOR WORKS: 24 -> 1 -> 0" in flat
    assert "consumes the corpus's soundly-expressible discriminating power" in flat


def test_both_legs_of_the_closure_are_exhaustive():
    t = ensemble.the_set_is_complete_over_the_corpus_and_the_corpus_is_the_limit()
    flat = " ".join(t.split())
    assert "0 of 640 sound bodies missing, on three designs" in flat
    assert "neither selectable nor soundly authorable" in flat


def test_the_closure_does_not_overclaim_impossibility():
    """The reference satisfies the spec, so a sound check is possible in
    principle. The claim is about what 640 authored attempts produced."""
    t = ensemble.the_set_is_complete_over_the_corpus_and_the_corpus_is_the_limit()
    flat = " ".join(t.split())
    assert "Not that no sound check exists" in flat
    assert "no author working from this specification produced one in 640 attempts" in flat


def test_no_declared_output_is_dark_to_the_requirements():
    """The lever needed a port the specification failed to reach. There is
    none, and that alone closes it."""
    t = ensemble.requirement_extraction_is_not_the_limit_and_activity_is_the_predictor()
    flat = " ".join(t.split())
    assert "**NO PORT IS DARK, AND THAT ALONE CLOSES THE LEVER.**" in flat
    assert "declared by between 3 and 16" in flat
    assert "read by between 17 and 51" in flat
    assert "re-extracting S1 to cover where the divergence lives has NO TARGET" in flat


def test_the_coverage_correlation_runs_the_wrong_way_for_the_lever():
    t = ensemble.requirement_extraction_is_not_the_limit_and_activity_is_the_predictor()
    flat = " ".join(t.split())
    assert "requirement count **+0.52 to +0.93**" in flat
    assert "check count **+0.36 to +0.54**" in flat
    assert "MORE wrong, not less" in flat


def test_the_width_control_is_stated_and_it_changes_the_reading():
    """saved_addr and dc_addr are 32 bits; a correlation across all ten ports is
    confounded, and controlling it moves the check reading from +0.01 to +0.45."""
    t = ensemble.requirement_extraction_is_not_the_limit_and_activity_is_the_predictor()
    flat = " ".join(t.split())
    assert "confounded by width" in flat
    assert "+0.01 uncontrolled and +0.45" in flat


def test_activity_is_the_predictor_and_check_count_is_a_restatement_of_it():
    t = ensemble.requirement_extraction_is_not_the_limit_and_activity_is_the_predictor()
    flat = " ".join(t.split())
    assert "CHECK COUNT CARRIES NO INFORMATION ONCE ACTIVITY IS HELD FIXED" in flat
    assert "Spearman(checks reading a port, golden transitions) = +0.857" in flat
    assert "activity wearing coverage's name" in flat


def test_the_requirement_correlation_is_reported_as_not_robust():
    """It survives one activity control and collapses under the other on three
    designs of five. The weak statement is the one the data supports."""
    t = ensemble.requirement_extraction_is_not_the_limit_and_activity_is_the_predictor()
    flat = " ".join(t.split())
    assert "**THE REQUIREMENT CORRELATION IS NOT ROBUST EITHER.**" in flat
    assert "may not predict it at all" in flat


def test_the_loader_defect_is_recorded_in_the_docstring():
    """The first run loaded zero requirements and printed a clean table saying
    every port was uncovered. A finding that would have been reported as the
    lever's confirmation is recorded as the ninth counting-shaped defect."""
    d = ensemble.requirement_extraction_is_not_the_limit_and_activity_is_the_predictor.__doc__
    flat = " ".join((d or "").split())
    assert "loaded ZERO of them" in flat
    assert "ninth counting-shaped defect" in flat
    assert "REFUSES on a short set" in flat


def test_the_extraction_closure_names_its_own_limits():
    t = ensemble.requirement_extraction_is_not_the_limit_and_activity_is_the_predictor()
    flat = " ".join(t.split())
    assert "no single coefficient here is significant and none is offered as one" in flat
    assert "first_miss_err" in flat


def test_the_extraction_closure_is_named_in_the_module_docstring():
    flat = " ".join((ensemble.__doc__ or "").split())
    assert "requirement_extraction_is_not_the_limit_and_activity_is_the_predictor" in flat
    assert "no port is dark and the lever has no target" in flat


def test_no_graded_run_reached_its_trial_budget():
    """`give the editor more trials` is closed for nothing: the editor already
    declines the budget it has, in four runs of four."""
    t = ensemble.the_editor_declines_its_budget_and_stops_past_its_own_best()
    flat = " ".join(t.split())
    assert "**NOT ONE OF THE FOUR REACHED ITS BUDGET.**" in flat
    assert "6 to 16 of 21 trials unspent" in flat
    assert "the editor already declines the budget it has" in flat


def test_every_run_stopped_past_its_own_best_and_the_latch_decides_what_ships():
    """Where a run stopped is not what it shipped: the latch decides that, and
    the finding must not conflate the two."""
    t = ensemble.the_editor_declines_its_budget_and_stops_past_its_own_best()
    flat = " ".join(t.split())
    assert "4 OF 4 STOPPED ON A TRIAL WORSE THAN THEIR OWN BEST" in flat
    assert "0 OF 4 STOPPED AT THEIR BEST" in flat
    assert "what each run SHIPS is decided by the latch rather than by where it stopped" in flat


def test_the_oscillation_is_quantified_as_the_goal_asks():
    t = ensemble.the_editor_declines_its_budget_and_stops_past_its_own_best()
    flat = " ".join(t.split())
    assert "OSCILLATION IS BETWEEN A QUARTER AND A HALF OF ALL TRIALS" in flat
    assert "1 of 4, 3 of 11, 7 of 13 and 4 of 14" in flat


def test_the_trials_confound_is_stated_and_called_inseparable():
    """Trials are an output of the criterion, not an independent variable, so
    the +1.000 must not be read as `editing more makes it worse` on its own."""
    t = ensemble.the_editor_declines_its_budget_and_stops_past_its_own_best()
    flat = " ".join(t.split())
    assert "SPEARMAN +1.000 ON n = 4" in flat
    assert "confound is stated and is not separable" in flat
    assert "trials are an OUTPUT of the criterion" in flat


def test_the_positive_ordering_is_bounded_to_designs_the_set_drove():
    t = ensemble.the_editor_declines_its_budget_and_stops_past_its_own_best()
    flat = " ".join(t.split())
    assert "+0.949" in flat
    assert "ordering designs it itself drove" in flat
    assert "rank designs it did not drive" in flat


def test_the_trial_counter_source_is_recorded_in_the_docstring():
    """Counting tracker lines would over-report three of four runs by one,
    because three log an init reading at trial 0 and one does not."""
    d = ensemble.the_editor_declines_its_budget_and_stops_past_its_own_best.__doc__
    flat = " ".join((d or "").split())
    assert "`action_calls`, not from the tracker's line count" in flat
    assert "over-report three runs by one" in flat


def test_the_budget_closure_is_named_in_the_module_docstring():
    flat = " ".join((ensemble.__doc__ or "").split())
    assert "the_editor_declines_its_budget_and_stops_past_its_own_best" in flat
    assert "stopped voluntarily with 6 to 16 trials unspent" in flat


def test_the_ratchet_claim_carries_its_own_correction():
    """The first version of this finding said the ratchet preserved every grade.
    It preserved three; run 9's latch chose against the checks."""
    t = ensemble.the_editor_declines_its_budget_and_stops_past_its_own_best()
    flat = " ".join(t.split())
    assert "CORRECTS A SENTENCE THAT STOOD HERE" in flat
    assert "I wrote that the ratchet preserved every grade reported here. It preserved three." in flat


def test_the_proxy_outvoted_the_checks_in_the_latch():
    t = ensemble.the_editor_declines_its_budget_and_stops_past_its_own_best()
    flat = " ".join(t.split())
    assert "RUN 9's LATCH REJECTED THE STATE WITH THE FEWEST CHECK OBJECTIONS" in flat
    assert "the proxy outvoted the checks 48 to 5" in flat
    assert "its proxy units reached zero at trial 10 and stopped voting" in flat


def test_the_prescription_separates_informing_from_deciding():
    t = ensemble.the_editor_declines_its_budget_and_stops_past_its_own_best()
    flat = " ".join(t.split())
    assert ("A proxy may inform an editor and must not enter the criterion "
            "that decides which design is kept.") in flat


def test_the_latch_reconstruction_is_pinned_against_the_grader():
    """A reconstruction that did not reproduce the grader would not be quotable."""
    d = ensemble.the_editor_declines_its_budget_and_stops_past_its_own_best.__doc__
    flat = " ".join((d or "").split())
    assert "It reproduces the grader 4 of 4" in flat
    assert "had it not, none of it would be quotable" in flat


def test_the_strength_collapse_is_nine_ports_of_ten_going_silent():
    t = ensemble.the_strength_collapse_is_port_by_port_not_a_uniform_dimming()
    flat = " ".join(t.split())
    assert "THE COLLAPSE IS NOT A UNIFORM DIMMING" in flat
    assert "SILENT ON NINE PORTS OF TEN" in flat
    assert "zero in 5,283 decisions between them" in flat


def test_the_most_watched_port_is_the_blindest():
    t = ensemble.the_strength_collapse_is_port_by_port_not_a_uniform_dimming()
    flat = " ".join(t.split())
    assert "51 CHECKS READ IT" in flat
    assert "OBJECT ZERO TIMES" in flat
    assert "most-watched port in the set is the one it cannot see at all" in flat


def test_strength_is_a_rate_so_fewer_wrong_ports_does_not_explain_it():
    t = ensemble.the_strength_collapse_is_port_by_port_not_a_uniform_dimming()
    flat = " ".join(t.split())
    assert "Strength is a RATE" in flat
    assert "not an artifact of the design having fewer wrong ports" in flat


def test_the_worst_run_stopped_while_the_checks_were_still_talking():
    """It ties the per-port reading to the latch finding: run 9's proxy picked a
    design the checks still objected to on all ten ports."""
    t = ensemble.the_strength_collapse_is_port_by_port_not_a_uniform_dimming()
    flat = " ".join(t.split())
    assert "objections on ALL TEN ports" in flat
    assert "it picked one the checks were still objecting to" in flat


def test_the_port_target_is_not_claimed_as_a_new_lever():
    """The corpus closure already answers it: 302 bodies object to that design,
    one is sound, and it is already in the set."""
    t = ensemble.the_strength_collapse_is_port_by_port_not_a_uniform_dimming()
    flat = " ".join(t.split())
    assert "It is not a new lever" in flat
    assert "640 attempts did not produce" in flat


def test_the_port_decomposition_is_named_in_the_module_docstring():
    flat = " ".join((ensemble.__doc__ or "").split())
    assert "the_strength_collapse_is_port_by_port_not_a_uniform_dimming" in flat
    assert "COMPLETELY SILENT on nine ports of ten" in flat


def test_the_two_per_port_instruments_agree_only_on_narrow_ports():
    t = ensemble.set_blindness_is_dominated_by_port_width_and_inverts_there()
    flat = " ".join(t.split())
    assert "SPEARMAN +0.200" in flat
    assert "26 OF 45 PORT PAIRS = 58% ORDERED THE SAME WAY" in flat
    assert "Restricted to the seven ONE-BIT ports it is **+0.714**" in flat


def test_the_widest_port_sits_at_opposite_ends_of_the_two_rankings():
    t = ensemble.set_blindness_is_dominated_by_port_width_and_inverts_there()
    flat = " ".join(t.split())
    assert ("`saved_addr` is the WORST port of ten on the golden-free reading "
            "and the SECOND BEST on the golden one") in flat


def test_the_mechanism_is_the_denominator_not_the_checks():
    t = ensemble.set_blindness_is_dominated_by_port_width_and_inverts_there()
    flat = " ".join(t.split())
    assert "The golden-free denominator explodes with width and the golden one does not" in flat


def test_the_headline_blindness_is_dominated_by_the_inverting_half():
    t = ensemble.set_blindness_is_dominated_by_port_width_and_inverts_there()
    flat = " ".join(t.split())
    assert "82.6%" in flat and "76.7%" in flat and "93.1%" in flat
    assert "41% of every blind cell in the set sits on three ports of ten" in flat


def test_the_prescription_is_to_stratify_by_width():
    t = ensemble.set_blindness_is_dominated_by_port_width_and_inverts_there()
    flat = " ".join(t.split())
    assert "STRATIFY SET BLINDNESS BY PORT WIDTH, OR DO NOT QUOTE IT" in flat
    assert "Every blindness figure on this plan is over mixed widths" in flat


def test_the_width_finding_does_not_overclaim_significance():
    t = ensemble.set_blindness_is_dominated_by_port_width_and_inverts_there()
    flat = " ".join(t.split())
    assert "is not offered as significant" in flat
    assert "barely above chance" in flat


def test_the_width_inversion_is_named_in_the_module_docstring():
    flat = " ".join((ensemble.__doc__ or "").split())
    assert "set_blindness_is_dominated_by_port_width_and_inverts_there" in flat
    assert "Stratify set blindness by port width, or do not quote it" in flat


def test_the_corrected_ranking_keeps_almost_the_same_checks():
    t = ensemble.the_width_correction_changes_reporting_and_not_selection()
    flat = " ".join(t.split())
    assert "+0.613" in flat
    assert "overlap 59 = 80%" in flat and "overlap 99 = 89%" in flat


def test_the_tightest_cut_is_refused_as_tie_dominated():
    """The 35% overlap reads as the correction being decisive where selection
    bites. It is sort order inside 38 tied values."""
    t = ensemble.the_width_correction_changes_reporting_and_not_selection()
    flat = " ".join(t.split())
    assert "NOT COMPARABLE" in flat
    d = ensemble.the_width_correction_changes_reporting_and_not_selection.__doc__
    dflat = " ".join((d or "").split())
    assert "which 37 is sort order" in dflat
    assert "The figure is withdrawn" in dflat


def test_the_clean_population_is_smaller_not_larger():
    t = ensemble.the_width_correction_changes_reporting_and_not_selection()
    flat = " ".join(t.split())
    assert "8 = 5 + 3, and all five are mixed-clean" in flat
    assert "SMALLER than the mixed one, not 4.75x larger" in flat


def test_the_vacuity_trap_is_named_in_the_docstring():
    d = ensemble.the_width_correction_changes_reporting_and_not_selection.__doc__
    flat = " ".join((d or "").split())
    assert "scores clean BY CONSTRUCTION" in flat
    assert "`stage_unexercised`'s own conflation in a new place" in flat


def test_the_audit_is_reported_beside_every_blindness_row():
    t = ensemble.the_width_correction_changes_reporting_and_not_selection()
    flat = " ".join(t.split())
    assert "AND THE AUDIT IS ZERO IN EVERY ROW" in flat
    assert "a blindness figure without its audit is not quotable" in flat


def test_the_sweeps_are_explicitly_not_invalidated():
    t = ensemble.the_width_correction_changes_reporting_and_not_selection()
    flat = " ".join(t.split())
    assert "The selection sweeps on this plan are not invalidated by it" in flat


def test_the_reach_bound_is_named_in_the_module_docstring():
    flat = " ".join((ensemble.__doc__ or "").split())
    assert "the_width_correction_changes_reporting_and_not_selection" in flat
    assert "the selection sweeps here are not invalidated" in flat


def test_the_generation_baseline_is_drawn_and_has_a_spread():
    t = ensemble.the_loops_best_output_beats_every_independent_draw()
    flat = " ".join(t.split())
    assert "SEVEN INDEPENDENT DRAWS FROM ONE SPECIFICATION SPAN 151 TO 230" in flat
    assert "MEAN 185, SD 23" in flat


def test_the_loop_took_the_worst_start_and_beat_the_best_draw():
    t = ensemble.the_loops_best_output_beats_every_independent_draw()
    flat = " ".join(t.split())
    assert "THE LOOP TOOK THE WORST START AND BEAT THE BEST DRAW" in flat
    assert "drove it to 146, past C's 151" in flat


def test_the_positive_is_stated_with_the_bar_it_misses():
    """A loop that beats one-shot generation and does not reach equivalence is a
    useful loop and an unmet goal, and both halves have to be said together."""
    t = ensemble.the_loops_best_output_beats_every_independent_draw()
    flat = " ".join(t.split())
    assert "AND IT IS NOT EQUIVALENCE, WHICH IS THE BAR" in flat
    assert "reporting the first without the second is the defect" in flat


def test_the_other_three_runs_did_not_beat_one_shot_generation():
    t = ensemble.the_loops_best_output_beats_every_independent_draw()
    flat = " ".join(t.split())
    assert "214, 221 and 271 are inside or above the population's range" in flat
    assert "did not improve on one-shot generation at all" in flat


def test_the_baseline_sizes_the_replicate_question():
    t = ensemble.the_loops_best_output_beats_every_independent_draw()
    flat = " ".join(t.split())
    assert "makes a 60-testpoint gap between two runs unremarkable" in flat
    assert "roughly ONE generation sd" in flat


def test_the_baseline_is_named_in_the_module_docstring():
    flat = " ".join((ensemble.__doc__ or "").split())
    assert "the_loops_best_output_beats_every_independent_draw" in flat
    assert "**better than all seven**" in flat
