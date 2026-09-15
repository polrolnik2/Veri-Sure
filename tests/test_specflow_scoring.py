"""The scoring instruments, and the experiment findings that read the reference.

Everything here is computed LAST, over a set already built, and feeds nothing
back. The tests that matter most are the ones asserting a finding states its own
LIMIT -- a retraction that does not say what survives, or a negative that does
not say what it failed to cover, is a claim rather than a measurement.
"""
import ast
import inspect
from pathlib import Path

from specflow import scoring as S
from specflow.scoring import (
    claim_kinds_transfer_where_lint_patterns_did_not,
    corpus_size_buys_span_and_saturates_on_blindness,
    obligation_decomposition_is_untested_on_most_of_its_target,
    resampling_one_prompt_produces_copies_and_blunderbusses,
    the_zero_audit_belongs_to_one_design,
    weighting_the_population_is_decoration,
)


def test_the_retraction_states_what_falls_and_what_survives():
    text = the_zero_audit_belongs_to_one_design()
    #: the number that fires it, both sides
    assert "All 32 contain G" in text and "Zero of the 57" in text
    #: the mechanism, or it is an association rather than an explanation
    assert "78% of split cells" in text and "SINK" in text
    #: **and what survives**, or a retraction overstates itself
    assert "6.2%" in text and "64.4%" in text
    assert "WHAT SURVIVES" in text
    #: the consequence for B2 is a gate, not a note
    assert "is a GATE" in text


def test_the_weighting_finding_reports_the_direction_it_pushes():
    text = weighting_the_population_is_decoration()
    #: independence weighting weights the OUTLIER UP -- the opposite of
    #: dissent weighting, and the reader has to be told
    assert "weights G UP" in text and "opposite" in text
    #: the margin, and that it is inside the resolution
    assert "0.7 points" in text
    assert "neither was chosen by looking at the answer" in text


def test_the_size_finding_separates_the_axes_and_names_the_tautology():
    text = corpus_size_buys_span_and_saturates_on_blindness()
    assert "MONOTONE" in text and "saturates" in text
    #: audit is flat -- volume neither helps nor hurts soundness
    assert "21.6% to 18.9%" in text
    #: the span column is partly a subsampling artefact and says so
    assert "TAUTOLOGICAL" in text
    #: and the ceiling above the whole plan
    assert "83.9%" in text


def test_the_variance_finding_reports_the_conditioned_number_first():
    text = resampling_one_prompt_produces_copies_and_blunderbusses()
    #: 46% is the headline and 4% is the result
    assert "46% AND THE HONEST ONE IS 4%" in text
    assert "both SOUND" in text and "**69%**" in text
    #: the cache collapse that invalidates the volume round
    assert "byte-identical bodies" in text and "{stage}_r{round}" in text
    #: and the structural observation about the rule's own resolution
    assert "cannot see the difference that matters for closure" in text


def test_the_decomposition_finding_states_its_own_coverage():
    text = obligation_decomposition_is_untested_on_most_of_its_target()
    assert "1 of 38" in text and "only applies to 6" in text.lower()
    #: the untested majority, named
    assert "UNTESTED    20" in text
    #: the axis is NOT claimed refuted
    assert "is NOT" in text and "refuted" in text
    #: and the parser miss is recorded rather than quietly fixed
    assert "never scanned `orelse`" in text
    #: soundness by silence is excluded from the count
    assert "soundness by silence" in text


def test_the_licence_finding_splits_transfer_from_precision():
    text = claim_kinds_transfer_where_lint_patterns_did_not()
    #: the test that passes
    assert "Zero of six fire zero times" in text
    #: the test that fails, with the baseline it fails against
    assert "PRECISION TEST FAILS" in text and "1.40x" in text and "1.64x" in text
    #: 33 sound refused for 13 caught -- the trade stated as a trade
    assert "13 convict the reference and 33 are" in text
    #: the sample-size illusion named where it appears
    assert "4.95x on 2 checks" in text
    #: and that held-out FIRING is not held-out precision
    assert "FIRING IS NOT BEING RIGHT" in text


def test_every_finding_here_is_a_string_and_none_returns_a_bare_rate():
    """A finding that returned a float would be a number without its
    parameters, which is what the whole reporting discipline exists to stop."""
    findings = [
        v for k, v in vars(S).items()
        if callable(v) and not k.startswith("_")
        and inspect.isfunction(v) and not inspect.signature(v).parameters
    ]
    assert len(findings) >= 7
    for f in findings:
        assert isinstance(f(), str), f.__name__


def test_the_scoring_module_is_the_only_side_that_names_the_reference():
    """The separation is the import graph. `scoring` may import `population`;
    a reverse edge would be a cycle, so wiring the audit into the selector is
    an ImportError rather than a review comment."""
    tree = ast.parse(Path(S.__file__).read_text())
    modules = {(n.module or "") for n in ast.walk(tree)
               if isinstance(n, ast.ImportFrom)}
    assert "specflow.population" in modules
    pop = ast.parse(Path(
        Path(S.__file__).parent / "population.py").read_text())
    assert not any("scoring" in (n.module or "") for n in ast.walk(pop)
                   if isinstance(n, ast.ImportFrom))


def test_the_reconciliation_carries_both_populations_and_the_per_port_split():
    from specflow.scoring import (
        the_population_majority_is_right_less_than_half_the_time as f,
    )
    text = f()
    #: both figures, each with its population size
    assert "48.5%" in text and "60.9%" in text
    assert "seven designs" in text and "THIRTEEN" in text
    assert "NOT A CONTRADICTION" in text
    #: the unadjudicable cells are separated rather than folded in
    assert "no reference value to adjudicate" in text and "139" in text
    #: the per-port breakdown, which is what makes it a finding
    assert "38.1%" in text and "33.1%" in text
    #: and the scope limit -- this bounds the ensemble, not the rule
    assert "not the minority rule" in text


def test_the_pipeline_finding_separates_what_ran_from_what_did_not():
    from specflow.scoring import (
        the_packaged_pipeline_reproduces_every_recorded_figure as f,
    )
    text = f()
    assert "EVERY TARGET ROW MATCHES" in text
    #: the gate refusing its own motivating population is the point, not a bug
    assert "THE POPULATION GATE REFUSED" in text and "86%" in text
    assert "overridden EXPLICITLY" in text
    #: and the half that did NOT run is named rather than implied
    assert "STILL UNEXERCISED" in text and "has authored nothing" in text


def test_the_v1_finding_reports_the_bar_it_cleared_AND_why_that_is_not_a_win():
    from specflow.scoring import (
        elicited_alternative_readings_produce_strength_not_difference as f,
    )
    text = f()
    #: the controlled comparison is the headline: author fixed, prompt changed
    assert "HOLDING THE AUTHOR FIXED" in text
    assert "18.9%" in text and "75.0%" in text
    #: both arms, so the effect is not one model's
    assert "gpt-5.6-terra" in text and "gpt-5.6-luna" in text
    assert "0.319" in text and "0.401" in text
    #: the bar, and that it was cleared
    assert "+2,826" in text and "new set-level cells > 0" in text
    #: and immediately, why clearing it proves nothing
    assert "METRIC BREAKING, NOT THE EXPERIMENT SUCCEEDING" in text
    #: declines are reported as answers, not failures, for both arms
    assert "declined as single-reading" in text
    #: and the reason the second arm exists is named as my error
    assert "ms[:10]" in text and "index 10" in text