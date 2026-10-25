"""Coverage is not exercise, and nothing else in the pipeline tells them apart.

A requirement is covered when a testpoint names it and its check runs. That
says nothing about whether the testpoint drove the design into the situation
the requirement is about.

Measured on `i2c_master_bit_ctrl`: `clk_cnt` is the 16-bit prescale value
loaded into the divider that generates `clk_en`. The suite holds it at one
value on 480 of 482 testpoints and exercises 6 distinct values in total. On the
342 traces where it is 0 the divider reloads to zero, `clk_en` free-runs, and
the known-good design's `clk_en` is 100% high across 13,178 edges -- so a
requirement about PAUSING the timing counter cannot be told from its violation.
One such check convicts that design.
"""
from specflow.ports import stimulus_diversity

CONTRACT = {"io": [
    {"name": "clk", "dir": "input", "width": 1},
    {"name": "rst", "dir": "input", "width": 1},
    {"name": "clk_cnt", "dir": "input", "width": 16},
    {"name": "cmd", "dir": "input", "width": 4},
    {"name": "din", "dir": "input", "width": 1},
    {"name": "q", "dir": "output", "width": 1},
]}


def _suite(**per_port):
    """`n` testpoints, each driving every port from its own value list."""
    n = max(len(v) for v in per_port.values())
    return {f"TP-{i:04d}": [{p: v[i % len(v)] for p, v in per_port.items()}]
            for i in range(n)}


def test_a_wide_port_stuck_on_a_few_values_is_reported():
    got = stimulus_diversity(CONTRACT, _suite(
        clk_cnt=[0] * 40 + [1, 2], cmd=list(range(16)), din=[0, 1]))
    assert [i.path for i in got] == ["stimulus.clk_cnt"]
    assert "16 bits wide" in got[0].message
    assert got[0].severity == "warning", "reporting, never a gate"


def test_a_narrow_port_covering_its_whole_range_is_not_reported():
    """`cmd` is flat per testpoint and that is ORDINARY.

    A testpoint that issues one command drives `cmd` flat. On the real suite it
    is flat on 449 of 482 testpoints while the run exercises all 16 values of
    its 4-bit range. Flatness alone was the first version's test and it flagged
    exactly this; the discriminator is how many values the suite reached of
    what it COULD have reached.
    """
    got = stimulus_diversity(CONTRACT, _suite(
        clk_cnt=list(range(40)), cmd=list(range(16)), din=[0, 1]))
    assert [i.path for i in got] == [], [i.message for i in got]


def test_an_input_never_varied_at_all_is_reported_whatever_its_width():
    got = stimulus_diversity(CONTRACT, _suite(
        clk_cnt=list(range(40)), cmd=list(range(16)), din=[0] * 40))
    assert [i.path for i in got] == ["stimulus.din"]
    assert "single value" in got[0].message


def test_clocks_and_resets_are_not_reported():
    """`pinned_inputs` owns them and they are SUPPOSED to be held."""
    got = stimulus_diversity(CONTRACT, _suite(
        clk=[0] * 40, rst=[0] * 40, clk_cnt=list(range(40)),
        cmd=list(range(16)), din=[0, 1]))
    assert [i.path for i in got] == []


def test_no_stimulus_reports_nothing():
    assert stimulus_diversity(CONTRACT, {}) == []
    assert stimulus_diversity(CONTRACT, {"TP-0000": []}) == []


def test_the_reachable_bound_is_the_testpoint_count_not_the_width():
    """A 16-bit port cannot show 65536 values across 8 testpoints.

    Normalising by `2**width` alone would report every wide port in every small
    suite, which is a fact about the suite's size rather than about its
    stimulus.
    """
    got = stimulus_diversity(CONTRACT, _suite(
        clk_cnt=[0, 1, 2, 3, 4, 5, 6, 7], cmd=list(range(8)), din=[0, 1]))
    assert [i.path for i in got] == [], (
        "8 distinct values over 8 testpoints is everything it could reach")


def test_the_build_actually_calls_it():
    """A SOURCE-LEVEL PIN, because a behavioural one needs model calls.

    `build_artifacts` cannot run in a unit test -- it is the whole pipeline --
    so nothing behavioural would notice this call being deleted. A call site
    inside a stage has twice been removed on this branch without failing a
    single test, which is why the plan asks for a stage-level or source-level
    pin specifically.

    It must be called AFTER the oracle stage: `[O]`'s own staging loop appends
    testpoints to `stim_by_tp`, so measuring earlier describes a suite the run
    did not use.
    """
    import inspect

    from specflow import integration

    src = inspect.getsource(integration)
    assert "stimulus_diversity(contract, stim_by_tp" in src, (
        "the build must call it, or it is a library function nobody runs")
    called = src.index("stimulus_diversity(contract, stim_by_tp")
    staged = src.index("grown_before = (len(tps)")
    assert called > staged, (
        "it must run after [O] has finished appending testpoints, or it "
        "measures a suite the run did not use")
    assert "stim_issues.append(issue)" in src, (
        "the issues have to reach the artifact, not only the log")
