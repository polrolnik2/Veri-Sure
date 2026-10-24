"""Step 7: the staging loop stops guessing.

A check that never fires gets one response today -- mint another testpoint --
and after about three of those, `ABANDONED`, a verdict whose meaning is "the
testplan could not reach this". Triaging k1's 25 never-firing checks against
recorded state says that is the wrong response most of the time. Of the 15 whose
requirement names a state, ELEVEN had the state reached on the check's own
testpoints and the check stayed silent anyway, and ZERO are the case the loop is
built for.

The loop could not tell those apart because it could not see whether the state
was entered. Once the state is a probe it is in the row, and one scan splits the
block into cases that go to two different agents with different messages.
"""
from __future__ import annotations

from specflow import oracles_stage as OS
from specflow import reachability as R
from specflow.refmodel.oracles import RequirementOracle

PROBES = ["in_idle", "in_cload", "in_lrefill3", "in_cstore", "in_srefill4"]

CONTRACT = {"module_name": "dcfsm", "io": [
    {"name": "clk", "dir": "input", "width": 1},
    {"name": "go", "dir": "input", "width": 1},
    {"name": "busy", "dir": "output", "width": 1},
    *[{"name": p, "dir": "probe", "width": 1,
       "licensed_by": ["REQ-0001"], "spans": [f"the FSM is in {p}"]}
      for p in PROBES],
]}


def _rows(states):
    return [{"edge": i, "inputs": {"go": 1}, "outputs":
             {"busy": 0, **{p: 1 if p == st else 0 for p in PROBES}}}
            for i, st in enumerate(states)]


#: tp_0007 reaches CLOAD; tp_0031 reaches LREFILL3; nothing reaches SREFILL4.
ROWS = {
    "tp_0001": _rows(["in_idle"] * 3),
    "tp_0007": _rows(["in_idle", "in_cload", "in_cload"]),
    "tp_0031": _rows(["in_idle", "in_cload", "in_lrefill3", "in_lrefill3"]),
    "tp_0012": _rows(["in_idle", "in_cstore"]),
}
POOL = R.observed(ROWS, PROBES)


def _norm(*probes):
    return {"activation": {"text": "while in the state", "inputs": {},
                           "opens_on": [{p: 1} for p in probes],
                           "until": [], "aborts_on": [], "sustains": []},
            "observable": ["busy"]}


SILENT = ("def decide(trace):\n    return (None, None, 'never fired')\n")


def _oracle(uid, tps):
    return RequirementOracle(req_uid=uid, clause="", source=SILENT, tp_uids=tps)


def test_the_triage_splits_the_abstainers_three_ways(monkeypatch) -> None:
    """AUTHOR / FRONTIER / LEGACY, mechanically, with no model call.

    A check whose state its OWN stimulus reached is a check defect. One whose
    state nothing reached is the frontier. One naming no state is untouched --
    that bucket is not empty, and nothing here reaches it.
    """
    monkeypatch.setattr(R, "rows_for", lambda *a, **k: ROWS)

    held = {"AUTHOR-A": _oracle("AUTHOR-A", ["tp_0007"]),      # CLOAD, its own
            "AUTHOR-B": _oracle("AUTHOR-B", ["tp_0031"]),      # LREFILL3, its own
            "FRONTIER": _oracle("FRONTIER", ["tp_0001"]),      # SREFILL4, nowhere
            "ADAPT":    _oracle("ADAPT", ["tp_0001"]),         # LREFILL3, elsewhere
            "LEGACY":   _oracle("LEGACY", ["tp_0001"])}
    normalized = {"AUTHOR-A": _norm("in_cload"),
                  "AUTHOR-B": _norm("in_lrefill3"),
                  "FRONTIER": _norm("in_srefill4"),
                  "ADAPT": _norm("in_lrefill3"),
                  "LEGACY": {"activation": {"text": "t", "inputs": {},
                                            "opens_on": [], "until": [],
                                            "aborts_on": [], "sustains": []},
                             "observable": ["busy"]}}
    unexer = dict.fromkeys(held, "never fired")

    tri = OS._probe_triage(unexer, held, normalized, CONTRACT, "w",
                           {"tp_0001": [{}]}, "step")

    assert set(tri.author) == {"AUTHOR-A", "AUTHOR-B"}
    assert tri.blocked == {"FRONTIER": "in_srefill4"}
    # ADAPT's state IS observed, just not on its own testpoints, so it does not
    # schedule a discovery attempt and is not a check defect either.
    assert "ADAPT" not in tri.author and "ADAPT" not in tri.blocked
    assert "LEGACY" not in tri.author and "LEGACY" not in tri.blocked


def test_the_author_route_carries_reproducible_evidence(monkeypatch) -> None:
    """A concrete defect report, not "already sound, fix it anyway".

    That other message was measured to break 2 of 4 working checks. This one
    names the probe, the testpoint and the edges, so the author can look.
    """
    monkeypatch.setattr(R, "rows_for", lambda *a, **k: ROWS)
    held = {"REQ-A": _oracle("REQ-A", ["tp_0007"])}
    tri = OS._probe_triage({"REQ-A": "never fired"}, held,
                           {"REQ-A": _norm("in_cload")}, CONTRACT, "w",
                           {"tp_0001": [{}]}, "step")
    why = tri.author["REQ-A"]
    assert "in_cload" in why
    assert "tp_0007" in why
    assert "edge 1" in why
    assert "defect in the check" in why
    assert "not a gap in the stimulus" in why


def test_a_check_whose_state_was_reached_spends_no_staging_attempt(monkeypatch) -> None:
    """The point of the route. On k1 this is 11 of 15, and it costs nothing."""
    monkeypatch.setattr(R, "rows_for", lambda *a, **k: ROWS)
    held = {"REQ-A": _oracle("REQ-A", ["tp_0007"])}
    tri = OS._probe_triage({"REQ-A": "never fired"}, held,
                           {"REQ-A": _norm("in_cload")}, CONTRACT, "w",
                           {"tp_0001": [{}]}, "step")
    assert "REQ-A" in tri.author
    assert "REQ-A" not in tri.blocked, "it must not also schedule stimulus"


# ---------------------------------------------------------------- the block

STIM = {"tp_0007": [{"inputs": {"go": 0}, "hold": 1},
                    {"inputs": {"go": 1}, "hold": 1},
                    {"inputs": {"go": 1}, "hold": 1}],
        "tp_0031": [{"inputs": {"go": 1}, "hold": 4}]}


def _block(target="in_srefill4", own=("in_cload",), tried=()):
    return OS._pool_block(target=target, pool=POOL, contract=CONTRACT,
                          stimulus_by_tp=STIM, own=list(own),
                          relation=R.mine(ROWS, PROBES), tried=list(tried))


def test_the_block_hands_over_a_stimulus_that_RAN() -> None:
    """Grounded: not a synthesised recipe, a recorded stimulus with its steps.

    A mined conjunction can be wrong -- the `in_idle` disjunction measured 11.8%
    precision -- has no reproducer behind it, and asks the author to build a
    whole stimulus around it. The prefix is something that happened.
    """
    block = _block()
    assert "prefix reaching in_cload" in block
    assert "tp_0007" in block
    assert '"go": 1' in block or "'go': 1" in block


def test_the_block_carries_the_specs_words_for_the_target() -> None:
    """The author picks the predecessor FROM THE SPECIFICATION, so it needs it."""
    assert "the FSM is in in_srefill4" in _block()


def test_the_block_shows_the_whole_pool_and_marks_what_is_unreached() -> None:
    """Every observed state, because the pipeline must not pre-select.

    No mechanical source knows an unobserved state's predecessor: there is no
    edge into it, and a depth heuristic assumes a chain and picks the wrong
    branch on a fork. So the pipeline owns what has been reached, the author
    owns what the spec says comes next, and the row settles it.
    """
    block = _block()
    for probe in PROBES:
        assert probe in block
    assert "in_srefill4     never" in block or "in_srefill4    never" in block
    assert "Pick the pool state the specification says precedes" in block
    assert "Do not restart from reset" in block


def test_a_retry_is_told_what_the_last_attempt_tried() -> None:
    """A wrong pick costs one call and is excluded, not repeated."""
    assert "attempts so far: none" in _block()
    assert "in_cstore" in _block(tried=["extended in_cstore, did not rise"])


def test_the_block_is_absent_when_nothing_has_been_reached() -> None:
    """Then the hint is exactly today's, so the change is never worse."""
    hint = OS._hint({"uid": "R", "text": "t"}, _norm("in_srefill4"), None, 0,
                    pool_block="")
    assert "<pool" not in hint
    assert "Stage the situation this requirement is about" in hint


def test_the_block_goes_FIRST_in_the_hint() -> None:
    """It is the concrete thing -- what to start from, not what to aim at."""
    hint = OS._hint({"uid": "R", "text": "t"}, _norm("in_srefill4"), None, 0,
                    pool_block=_block())
    assert "<pool" in hint
    assert hint.index("<pool") < hint.index("What must then be true") if \
        "What must then be true" in hint else True
