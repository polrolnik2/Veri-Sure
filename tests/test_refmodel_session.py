"""The debug session: editing a model against a frozen set of oracles.

Everything the loop guarantees is decidable here, without a model call. The
guarantees worth pinning are the ones a repair loop breaks silently: that a
turn cannot end worse than it started, that an edit which fails the mechanical
checks is reverted rather than scored, and that a BROKEN oracle never makes the
session chase a defect in the oracle by editing the model.
"""

from __future__ import annotations

from specflow.refmodel.oracles import RequirementOracle
from specflow.refmodel.session import DebugSession

CONTRACT = {
    "io": [
        {"name": "clk", "dir": "input", "width": 1, "role": "clock"},
        {"name": "rst_n", "dir": "input", "width": 1, "role": "reset"},
        {"name": "a", "dir": "input", "width": 4},
        {"name": "q", "dir": "output", "width": 8},
        {"name": "ack", "dir": "output", "width": 1},
    ]
}
STIM = {"TP-0000": [{"inputs": {"a": 3}, "hold": 8}]}

WORKING = '''from specflow.refmodel.base import RefModel


class Model(RefModel):
    OUTPUT_PORTS = ["q", "ack"]

    def reset(self):
        self.n = 0
        self.k = 0

    def step(self, i):
        if not hasattr(self, "n"):
            self.reset()
        self.n = self.mask(self.n + i.get("a", 0), 8)
        self.k = self.k + 1
        return {"q": self.n, "ack": 1 if self.k == 3 else 0}
'''

#: The same model with the acknowledge removed -- one clause broken, the rest fine.
BROKEN = WORKING.replace("1 if self.k == 3 else 0", "0")

ACK = '''
def decide(trace):
    for row in trace:
        if row["outputs"]["ack"] == 1:
            return (True, row["edge"], "ack pulsed")
    return (False, None, "ack never pulsed")
'''

GOOD_STEP = '''def step(self, i):
    if not hasattr(self, "n"):
        self.reset()
    self.n = self.mask(self.n + i.get("a", 0), 8)
    self.k = self.k + 1
    return {"q": self.n, "ack": 1 if self.k == 3 else 0}'''


def _oracle(source=ACK, uid="REQ-0000") -> RequirementOracle:
    return RequirementOracle(req_uid=uid, tp_uids=["TP-0000"],
                             clause="ack pulses once", source=source)


def _session(model=BROKEN, oracles=None, **kw) -> DebugSession:
    return DebugSession(
        model, CONTRACT, STIM, oracles or [_oracle()], base="step",
        requirements=[{"uid": "REQ-0000", "text": "ack must pulse",
                       "spec_spans": [{"quote": "the core acknowledges"}]}],
        verdicts={"REQ-0000": "not_met"},
        reasons={"REQ-0000": {"reason": "ack is hardwired to 0"}},
        covers={"REQ-0000": ["step"]},
        **kw,
    )


# --------------------------------------------------------------- editing


def test_an_edit_that_satisfies_the_oracle_is_accepted():
    s = _session()
    assert [r.req_uid for r in s.failing()] == ["REQ-0000"]
    out = s.replace_method("step", GOOD_STEP)
    assert out["accepted"] and out["failing_after"] == 0
    assert s.all_met()


def test_an_edit_that_does_not_parse_is_rejected_without_being_scored():
    s = _session()
    out = s.replace_method("step", "def step(self, i):\n    return {")
    assert not out["accepted"] and "does not parse" in out["reason"]
    assert s.source == BROKEN, "the model must be untouched"


def test_an_edit_failing_the_mechanical_checks_is_reverted():
    """Leaving a declared output unwritten is a defect in the EDIT.

    Scoring it would let a bad splice look like evidence about the model.
    """
    s = _session()
    out = s.replace_method("step", 'def step(self, i):\n    return {"q": 0}')
    assert not out["accepted"] and "mechanical checks" in out["reason"]
    assert s.source == BROKEN


def test_replacing_an_unknown_method_lists_what_exists():
    s = _session()
    out = s.replace_method("nope", GOOD_STEP)
    assert not out["accepted"]
    assert "step" in out["reason"] and "reset" in out["reason"]


def test_a_replacement_that_renames_the_method_is_rejected():
    """Otherwise the splice silently deletes the method it was addressing."""
    s = _session()
    out = s.replace_method("step", 'def other(self, i):\n    return {"q": 0, "ack": 0}')
    assert not out["accepted"] and "no method named 'step'" in out["reason"]


def test_a_method_handed_back_at_column_zero_is_reindented():
    """The common case; it must not become a syntax error inside the class."""
    s = _session()
    assert s.replace_method("step", GOOD_STEP)["accepted"]


# ------------------------------------------------------------ best-so-far


def test_a_turn_cannot_end_worse_than_it_started():
    """The direct answer to a repair round that built on its own worst artifact."""
    s = _session(model=WORKING)
    assert s.all_met()
    s.replace_method("step", 'def step(self, i):\n    return {"q": 0, "ack": 0}')
    assert len(s.failing()) == 1, "the edit made it worse, and was allowed"
    assert s.best() == WORKING, "best() must return the good version"


def test_ties_do_not_overwrite_the_best():
    """`note_best`'s rule, unchanged from rtl_editor and pinned by its tests.

    A run wandering across a plateau returns where it first arrived.
    """
    s = _session(model=WORKING)
    first = s.best()
    s.replace_method("step", GOOD_STEP)      # equally good, different text
    assert s.best() == first


# --------------------------------------------------------- broken oracles


def test_a_broken_oracle_is_not_something_the_session_tries_to_fix():
    """Counting it would make the session edit the model to fix the ORACLE."""
    broken = _oracle(source="def decide(trace):\n    return trace['nope']\n")
    s = _session(model=WORKING, oracles=[broken])
    assert s.failing() == [], "a broken oracle decides nothing"
    assert s.all_met()
    assert s.run_all()["broken_oracles"] == ["REQ-0000"]


# ---------------------------------------------------------------- reading


def test_explain_joins_all_five_sources_in_one_call():
    out = _session().explain("REQ-0000")
    assert out["requirement"] == "ack must pulse"
    assert out["specification_quoted"] == ["the core acknowledges"]
    assert out["judge_reasoning"]["reason"] == "ack is hardwired to 0"
    assert out["oracle_source"].strip().startswith("def decide")
    assert out["stimulus"]["TP-0000"] == STIM["TP-0000"]
    assert out["methods_claimed_to_implement_it"] == ["step"]
    assert out["current"]["status"] == "NOT MET"


def test_explain_on_an_unknown_requirement_says_what_exists():
    out = _session().explain("REQ-9999")
    assert "error" in out and out["known"] == ["REQ-0000"]


def test_run_oracle_windows_the_trace_and_reports_the_whole_length():
    out = _session().run_oracle("REQ-0000", from_edge=2, rows=3)
    tp = out["testpoints"]["TP-0000"]
    assert tp["edges_total"] == 8
    assert [r["edge"] for r in tp["trace"]] == [2, 3, 4]
    assert out["verdict"]["status"] == "NOT MET"


def test_read_model_numbers_lines_from_the_real_offset():
    """An agent citing a line must cite the one the file has."""
    body = _session().read_model("step")
    first = body.splitlines()[0]
    assert "def step" in first
    number = int(first.split(":")[0])
    assert WORKING.splitlines()[number - 1].strip().startswith("def step")


def test_run_all_reports_the_inert_case_explicitly():
    inert = ('from specflow.refmodel.base import RefModel\n\n\n'
             'class Model(RefModel):\n'
             '    OUTPUT_PORTS = ["q", "ack"]\n\n'
             '    def step(self, i):\n        return {"q": 0, "ack": 0}\n')
    out = _session(model=inert).run_all()
    assert out["distinct_output_states"] == 1
    assert "NEVER MOVE" in out["liveness"]


def test_the_session_exposes_no_way_to_edit_an_oracle():
    """A loop able to weaken what measures it will do exactly that."""
    s = _session()
    assert not [n for n in dir(s)
                if "oracle" in n.lower() and n.startswith(("set_", "replace_",
                                                           "write_", "edit_"))]


# ------------------------------------------- what the debugger can actually see


def test_run_oracle_reports_activity_for_the_whole_replay_not_the_window():
    """The window defaults to 60 edges; the map must describe what it misses.

    Without this an agent reading a flat first-60 cannot tell "this testpoint
    exercises nothing" from "I did not look far enough", and those demand
    opposite responses.
    """
    late = ('from specflow.refmodel.base import RefModel\n\n\n'
            'class Model(RefModel):\n'
            '    OUTPUT_PORTS = ["q", "ack"]\n\n'
            '    def reset(self):\n        self.k = 0\n\n'
            '    def step(self, i):\n'
            '        if not hasattr(self, "k"):\n            self.reset()\n'
            '        self.k += 1\n'
            '        return {"q": 0, "ack": 1 if self.k > 70 else 0}\n')
    s = DebugSession(
        late, CONTRACT, {"TP-0000": [{"inputs": {"a": 1}, "hold": 90}]},
        [_oracle()], base="step",
        requirements=[{"uid": "REQ-0000", "text": "ack"}],
        verdicts={"REQ-0000": "met"}, covers={})
    tp = s.run_oracle("REQ-0000", from_edge=0, rows=60)["testpoints"]["TP-0000"]
    assert [r["edge"] for r in tp["trace"]][-1] == 59, "the window ends before it moves"
    act = tp["activity"]
    assert act["inert"] is False, "the run is NOT inert, and the window hides that"
    assert act["first_change"]["ack"] == 70, "it must point past the window"
    assert act["first_change"]["q"] is None, "a port that never moves says so"
    assert act["distinct_output_states"] == 2


def test_an_inert_testpoint_is_named_as_such():
    """No edit can make its oracle pass; the agent must not spend attempts."""
    inert = ('from specflow.refmodel.base import RefModel\n\n\n'
             'class Model(RefModel):\n'
             '    OUTPUT_PORTS = ["q", "ack"]\n\n'
             '    def step(self, i):\n        return {"q": 0, "ack": 0}\n')
    s = _session(model=inert)
    tp = s.run_oracle("REQ-0000")["testpoints"]["TP-0000"]
    assert tp["activity"]["inert"] is True
    assert tp["activity"]["distinct_output_states"] == 1


def test_an_unexercised_oracle_is_not_reported_as_a_failing_model():
    """`explain` and `run_oracle` both said NOT MET, which is the conflation
    the tri-state exists to prevent -- in the two tools the agent uses most."""
    absent = RequirementOracle(
        req_uid="REQ-0000", tp_uids=["TP-0000"], clause="on reset, ack clears",
        source=("def decide(trace):\n"
                "    for row in trace:\n"
                "        if row['inputs'].get('rst_n') == 0:\n"
                "            return (row['outputs']['ack'] == 0, row['edge'], 'checked')\n"
                "    return (None, None, 'reset never asserted in this trace')\n"))
    s = _session(model=WORKING, oracles=[absent])
    assert s.explain("REQ-0000")["current"]["status"] == "NOT EXERCISED"
    assert s.run_oracle("REQ-0000")["verdict"]["status"] == "NOT EXERCISED"
    assert s.failing() == [], "and it is not something to chase"


# ----------------------------- findings with no oracle behind them


def _mixed_session():
    """One checked failure, one blocking verdict whose oracle was discarded."""
    return DebugSession(
        BROKEN, CONTRACT, STIM, [_oracle()], base="step",
        requirements=[{"uid": "REQ-0000", "text": "ack must pulse"},
                      {"uid": "REQ-0009", "text": "al rises on arbitration loss",
                       "spec_spans": [{"quote": "the master loses arbitration"}]}],
        verdicts={"REQ-0000": "not_met", "REQ-0009": "not_met",
                  "REQ-0010": "met"},
        reasons={"REQ-0009": {"reason": "al is never assigned"}},
        covers={"REQ-0009": ["_bus"]},
    )


def test_losing_an_oracle_does_not_hide_the_finding():
    """It used to vanish from the tool surface entirely.

    The verdict still blocks and it is still the judge's conclusion; all that
    changed is that nothing can decide it mechanically. An agent that cannot
    see it can neither act on it nor argue with it.
    """
    rows = {r["req_uid"]: r for r in _mixed_session().list_oracles()}
    assert set(rows) == {"REQ-0000", "REQ-0009"}, "the met one is not a finding"
    assert rows["REQ-0000"]["checked"] is True
    assert rows["REQ-0009"]["checked"] is False
    assert "NO EXECUTABLE CHECK" in rows["REQ-0009"]["detail"]


def test_the_verdict_itself_is_unchanged_by_the_loss_of_its_oracle():
    """Losing a check is not evidence about the model."""
    rows = {r["req_uid"]: r for r in _mixed_session().list_oracles()}
    assert rows["REQ-0009"]["status"] == "NOT MET"


def test_an_uncheckable_finding_still_carries_its_whole_provenance():
    out = _mixed_session().explain("REQ-0009")
    assert "error" not in out
    assert out["requirement"] == "al rises on arbitration loss"
    assert out["specification_quoted"] == ["the master loses arbitration"]
    assert out["judge_reasoning"]["reason"] == "al is never assigned"
    assert out["methods_claimed_to_implement_it"] == ["_bus"]
    assert out["oracle_source"] is None
    assert "never mechanically confirmed" in out["evidence_quality"]


def test_the_disclaimer_tells_the_agent_not_to_edit_on_an_unproven_lead():
    """Editing to satisfy an unverified opinion is how a correct model breaks."""
    out = _mixed_session().explain("REQ-0009")
    assert "lead, not a proven defect" in out["evidence_quality"]
    assert "leave the model alone" in out["evidence_quality"].lower()


def test_run_oracle_on_an_uncheckable_finding_says_so_rather_than_erroring():
    out = _mixed_session().run_oracle("REQ-0009")
    assert "error" not in out
    assert out["verdict"]["status"] == "NO EXECUTABLE CHECK"
    assert "explain" in out["next"]


def test_a_genuinely_unknown_uid_is_still_an_error():
    """The leniency must not swallow a typo."""
    assert "error" in _mixed_session().explain("REQ-9999")
    assert "error" in _mixed_session().run_oracle("REQ-9999")


def test_an_uncheckable_finding_is_not_counted_as_failing():
    """Nothing decided it, so it cannot score -- but it is still listed."""
    s = _mixed_session()
    assert [r.req_uid for r in s.failing()] == ["REQ-0000"]
