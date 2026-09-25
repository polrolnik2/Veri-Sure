"""A check that indexes the trace writes its own `after`, and escapes its rules.

`Window.extent`, `governed` and `body` fix where a window's boundaries fall.
A check that scans `range()` over trace indices is not subject to any of them,
and a later correction to them will not reach it either.

Measured on the frozen i2c set: 17 of 122 checks do this without ever calling
`after` -- 14% of the set outside every window rule the module enforces. Two
are among the ten that convict a known-good design.

REQ-0135 is what that costs when one gets it wrong. It sets `end` to the first
row where `start_sequence` is false, then searches `range(scl_low, end)` for
`idle`, which excludes that row -- and the two being mutually exclusive, `idle`
first becomes true exactly there. Over every START window in the suite, `idle`
was found inside the search range 0 times and only at the excluded row 184 of
184 on one design and 236 of 236 on another.
"""
from specflow.refmodel.temporal import hand_rolled_window

USES_AFTER = """
def decide(trace):
    from specflow.refmodel.temporal import after, throughout, worst
    windows = after(trace, lambda r: r["outputs"]["a"] == 1,
                    until=lambda r: r["outputs"]["b"] == 1)
    return worst([throughout(w, lambda r: r["outputs"]["c"] == 1)
                  for w in windows])
"""

HAND_ROLLED = """
def decide(trace):
    end = len(trace)
    for k in range(0, len(trace)):
        if trace[k]["outputs"]["a"] != 1:
            end = k
            break
    for j in range(0, end):
        if trace[j]["outputs"]["c"] == 1:
            return (True, trace[j]["edge"], "found")
    return (False, None, "never")
"""

COMPREHENSION = """
def decide(trace):
    end = len(trace)
    if any(trace[j]["outputs"]["a"] == 1 for j in range(0, end)):
        return (True, None, "found")
    return (False, None, "never")
"""

BOTH = """
def decide(trace):
    from specflow.refmodel.temporal import after, worst
    windows = after(trace, lambda r: r["outputs"]["a"] == 1, until=None)
    for w in windows:
        for j in range(0, len(w.rows)):
            pass
    return worst([])
"""


def test_a_check_using_after_is_not_flagged():
    assert hand_rolled_window(USES_AFTER) is False


def test_a_range_scan_is_flagged():
    assert hand_rolled_window(HAND_ROLLED) is True


def test_a_comprehension_scan_is_flagged_too():
    """A COMPREHENSION IS A LOOP, and checking only `ast.For` missed one.

    REQ-0150 scans with `any(f(trace[j]) for j in range(start, end))` and uses
    `range(start, end + 1)` elsewhere in the same body -- its author managing
    the boundary by hand in two directions. The first version of this detector
    reported 16 where a regex reported 17, and the regex was right.
    """
    assert hand_rolled_window(COMPREHENSION) is True


def test_a_check_that_also_calls_after_is_not_flagged():
    """Indexing INSIDE a window `after` built is not building your own."""
    assert hand_rolled_window(BOTH) is False


def test_a_non_compiling_body_is_left_to_the_other_gate():
    assert hand_rolled_window("def decide(trace)\n    return True") is False


def test_a_loop_that_is_not_over_range_is_not_a_scan():
    src = """
def decide(trace):
    for row in trace:
        if row["outputs"]["a"] == 1:
            return (True, row["edge"], "found")
    return (False, None, "never")
"""
    assert hand_rolled_window(src) is False, (
        "iterating the trace directly has no index arithmetic to get wrong; "
        "the hazard is a computed boundary, not a loop")


def test_enumerate_is_not_a_range_scan():
    """`enumerate(trace)` walks the trace; it does not compute a boundary.

    The hazard is index arithmetic against a computed endpoint -- `range(a, b)`
    where `b` was derived and may be off by one. Iterating with `enumerate` has
    no endpoint to get wrong, and flagging every loop over any call would
    report most of the set.
    """
    src = """
def decide(trace):
    for i, row in enumerate(trace):
        if row["outputs"]["a"] == 1:
            return (True, row["edge"], "found")
    return (False, None, "never")
"""
    assert hand_rolled_window(src) is False


def test_zip_over_neighbouring_rows_is_not_a_range_scan():
    src = """
def decide(trace):
    for prev, row in zip(trace, trace[1:]):
        if prev["outputs"]["a"] == 0 and row["outputs"]["a"] == 1:
            return (True, row["edge"], "rose")
    return (False, None, "never")
"""
    assert hand_rolled_window(src) is False


def test_the_oracle_stage_records_it():
    """A SOURCE-LEVEL PIN: the stage cannot run in a unit test.

    `run_oracle_stage` needs a model port, so nothing behavioural notices this
    field disappearing -- and a call site inside that function has twice been
    deleted on this branch without failing a test.
    """
    import inspect

    from specflow import oracles_stage

    src = inspect.getsource(oracles_stage)
    assert '"hand_rolled_windows"' in src, (
        "the artifact must carry it, or the measurement exists only in a doc")
    assert "hand_rolled_window(getattr(o, \"source\", \"\")" in src
    assert "for o in (trusted or ())" in src, (
        "it must be measured over the ACCEPTED checks -- reporting it for "
        "bodies that were discarded says nothing about what shipped")
