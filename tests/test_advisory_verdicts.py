"""A build may proceed with UNOBSERVABLE itemised, and with nothing else.

Measured on s-i2c: the reference-model gate failed with 34 issues of which only
9 (VIOLATES) were anything the debug loop could clear. Seven were UNOBSERVABLE,
and no turn of any loop ever clears one -- `ROUTE` sends it to spec authoring,
which is outside the pipeline. So a spec containing one internal-mechanism
sentence halts the build permanently, and that is not a rare spec: this one has
8 of 77.

The downgrade does not hide anything. The requirement stays in `dispositions`,
stays undischarged, and still renders on the gate. The plan objects to SILENT
omission; an itemised warning naming the requirement and the reason is the
opposite of silent.
"""

from __future__ import annotations

from specflow.refmodel import verdict as V
from specflow.schema import has_errors

ADVISORY = frozenset({"UNOBSERVABLE"})


def test_unobservable_downgrades_and_the_build_proceeds():
    issues = V.issues({"REQ-0001": "UNOBSERVABLE"}, advisory=ADVISORY)
    assert [i.severity for i in issues] == ["warning"]
    assert not has_errors(issues), "the gate stops failing on it"


def test_the_requirement_is_still_reported():
    """Downgraded is not dropped -- that is the whole distinction."""
    issues = V.issues({"REQ-0001": "UNOBSERVABLE"},
                      {"REQ-0001": "counter is internal"}, advisory=ADVISORY)
    assert len(issues) == 1
    assert "REQ-0001" in issues[0].path
    assert "return to spec authoring" in issues[0].message, "the route survives"
    assert "counter is internal" in issues[0].message


def test_nothing_else_can_be_downgraded_even_if_asked():
    """Every other blocking verdict accuses someone who can act.

    Downgrading one would let a build pass with work outstanding that something
    in this pipeline was about to do, which is a different thing entirely from
    a route that leaves the pipeline.
    """
    every = {f"REQ-{i:04d}": v for i, v in enumerate(sorted(V.BLOCKING))}
    issues = V.issues(every, advisory=frozenset(V.BLOCKING))
    downgraded = {i.path.rsplit(".", 1)[-1] for i in issues
                  if i.severity == "warning"}
    assert downgraded == {"unobservable", "abandoned"}
    assert has_errors(issues), "everything else still fails the gate"


def test_off_by_default():
    assert [i.severity for i in V.issues({"R": "UNOBSERVABLE"})] == ["error"]
    assert V.DOWNGRADABLE == frozenset({"ABANDONED", "UNOBSERVABLE"})


def test_an_earned_give_up_is_the_other_downgradable_verdict():
    """`ABANDONED` says a bounded attempt RAN and ran out, and carries the
    record proving it, so it cannot be reached by skipping the work."""
    issues = V.issues({"REQ-0001": "ABANDONED"},
                      {"REQ-0001": "never reached"},
                      advisory=frozenset({"ABANDONED"}))
    assert [i.severity for i in issues] == ["warning"]
    assert not has_errors(issues)
    assert "never reached" in issues[0].message


def test_unobservable_leaves_this_set_when_it_gains_a_route():
    """THE PAIRING, pinned so the two halves cannot drift apart.

    `UNOBSERVABLE` should mean "the resolution pass did not run" -- a harness
    defect, and blocking. It is downgradable only because that pass does not
    exist yet: removing it first would enforce no principle and merely halt
    builds on requirements nothing can yet resolve, which is the s-i2c failure
    this downgrade was added to fix.

    When `NormalizedRequirement` gains `observed_via`, this test fails, and the
    fix is to drop UNOBSERVABLE from DOWNGRADABLE in the same change.
    """
    from specflow.normalize import NormalizedRequirement

    has_route = "observed_via" in NormalizedRequirement.model_fields
    assert has_route == ("UNOBSERVABLE" not in V.DOWNGRADABLE), (
        "a requirement may only be blocked for skipping a pass that exists")


def test_conforms_is_still_not_an_issue_either_way():
    assert V.issues({"R": "CONFORMS"}, advisory=ADVISORY) == []


def test_the_switch_reaches_the_command_line():
    """EVERY link, not the two ends.

    Checking `build_artifacts` and the argparse flag left a hole in the middle:
    `top_agent` calls `run_specflow_node`, which did not take the argument, and
    the run died at startup with `unexpected keyword argument`. The signature
    chain has to be walked, because a switch is only as threaded as its weakest
    link and both ends looked right.
    """
    import inspect

    from eda_agent.specflow_node import run_specflow_node
    from eda_agent.top_agent import __file__ as top
    from specflow import integration
    from specflow.refmodel import compose

    chain = (run_specflow_node, integration.build_artifacts,
             compose.run_refmodel, compose._closed_loop, compose._debug_turns)
    for fn in chain:
        assert "advisory_verdicts" in inspect.signature(fn).parameters, fn

    # `reconsider_rounds` stops at `_closed_loop`, which is the only place that
    # counts rounds -- `_debug_turns` runs one turn set and has no use for it.
    for fn in chain[:-1]:
        assert "reconsider_rounds" in inspect.signature(fn).parameters, fn

    assert "specflow_advisory_verdicts" in open(top).read()
    assert "--advisory-unobservable" in open(
        "benchmarks/run_chipverilog.py").read()
