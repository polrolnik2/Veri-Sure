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
