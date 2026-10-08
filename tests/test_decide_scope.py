"""ONE SCOPE, IN THE SCREEN AND IN THE SUITE THAT SHIPS.

The oracle stage screens a check by replaying it wherever the stimulus goes: a
cell at TP-0400 can only be separated by a check replayed at TP-0400, and at the
narrow scope -- median `tp_uids` of **2 of 499** -- blindness reads 97% by
construction. Widening the screen alone is not a fix, it is a discrepancy, and
it is dangerous in both directions:

  screened wide, shipped narrow   the stage rejects checks as over-strict for
                                  firing where the product never asks them.
                                  Span paid for a number the product does not
                                  have.
  screened narrow, shipped wide   a check convicts a correct design somewhere
                                  nothing looked. That is the audit failure this
                                  pipeline exists to avoid.

So these pin both ends together.
"""
from __future__ import annotations

from specflow.refmodel.oracle_gen import RequirementOracle
from specflow.refmodel.oracles import decide_all
from specflow.refmodel.rtl_trace import decide_rtl

CONTRACT = {
    "module_name": "m",
    "io": [{"name": "a", "dir": "input", "width": 2},
           {"name": "q", "dir": "output", "width": 2}],
    "clocking": {"is_sequential": True},
}
MODEL = (
    "class Model:\n"
    "    OUTPUT_PORTS = ['q']\n"
    "    PROBE_PORTS = []\n"
    "    def reset(self):\n        pass\n"
    "    def step(self, i):\n        return {'q': i['a']}\n")

#: Fires only where `a == 3`, and convicts there.
BODY = (
    "def decide(trace):\n"
    "    for row in trace:\n"
    "        if row['inputs'].get('a') == 3:\n"
    "            return (False, row['edge'], 'a was 3')\n"
    "    return (None, None, 'never saw a == 3')\n")


def _oracle(tps):
    return RequirementOracle(req_uid="REQ-1", tp_uids=list(tps), clause="c",
                             source=BODY)


def test_the_model_screen_replays_where_the_STIMULUS_goes():
    """`decide_all` looped over `oracle.tp_uids`. The check below names only
    TP-0000, where nothing triggers it; the trigger is at TP-0001."""
    stim = {"TP-0000": [{"inputs": {"a": 0}, "hold": 2}],
            "TP-0001": [{"inputs": {"a": 3}, "hold": 2}]}
    got = decide_all([_oracle(("TP-0000",))], MODEL, CONTRACT, stim,
                     base="step")
    assert got[0].ok is False, (
        "the check fired at a testpoint it does not name, and the screen must "
        "see that or it screens something the suite will not do")
    assert got[0].tp_uid == "TP-0001", got[0]


def test_a_named_testpoint_with_no_stimulus_is_still_reported():
    """Kept, and kept SEPARATE from the scope: `render_suite` attaches the
    check to that testpoint, so the suite would emit a test with nothing to
    drive it. That is an inconsistency between two artifacts and stays
    reportable however wide the replay gets."""
    stim = {"TP-0000": [{"inputs": {"a": 0}, "hold": 2}]}
    got = decide_all([_oracle(("TP-0000", "TP-MISSING"))], MODEL, CONTRACT,
                     stim, base="step")
    assert got[0].broken and "no stimulus recorded for TP-MISSING" in got[0].broken


def _trace(tp, rows):
    return {"tp_uid": tp, "rows": rows,
            "states": [{"index": i, "held": 1, "edge": i,
                        "inputs": r["inputs"], "dut": r["outputs"],
                        "ref": r["outputs"]}
                       for i, r in enumerate(rows)]}


def test_the_suite_that_ships_decides_at_the_SAME_scope_as_the_screen():
    """`decide_rtl` looped over `oracle.tp_uids` too. A check screened at 499
    testpoints and shipped at 2 is a different check in production than the one
    the stage accepted."""
    import inspect

    src = inspect.getsource(decide_rtl)
    assert "scope = sorted(traces_by_tp)" in src, (
        "the shipped suite narrowed back to tp_uids while the screen stayed "
        "wide -- the two have to move together")
    #: And the per-named-testpoint hole report survives the widening.
    assert "produced no trace, so it decided nothing" in src
    assert "for tp in oracle.tp_uids:" in src


def test_both_scopes_are_stated_in_the_same_terms():
    """A discrepancy between these two is invisible in any single test, so the
    reason lives in both docstrings and this pins that it does."""
    import inspect

    from specflow.refmodel import rtl_trace

    assert "EVERY TESTPOINT THE STIMULUS HAS" in inspect.getdoc(decide_all)
    assert "EVERY RECORDED TRACE" in inspect.getsource(rtl_trace.decide_rtl)
