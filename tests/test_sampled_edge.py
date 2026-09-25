"""The sampled-edge form: a row is one clock edge as an assertion samples it.

`RefModel.outputs` reads the edge, `RefModel.advance` takes it, and the base
class drives the two in that order -- so a model cannot answer "which side of
the edge are my outputs on" differently from the recording. These pin the
Python half; `test_harness_conformance` pins that the simulator records the
same rows.
"""
from __future__ import annotations

from specflow import cover
from specflow.refmodel import oracle_gen
from specflow.refmodel.base import RefModel, probe_values, samples_before_edge
from specflow.refmodel.oracle_gen import RequirementOracle
from specflow.refmodel.oracles import replay

CONTRACT = {
    "io": [
        {"name": "clk", "dir": "input", "width": 1},
        {"name": "go", "dir": "input", "width": 1},
        {"name": "done_i", "dir": "input", "width": 1},
        {"name": "busy", "dir": "output", "width": 1},
        {"name": "ack", "dir": "output", "width": 1},
        {"name": "in_busy", "dir": "probe", "width": 1},
        {"name": "hist", "dir": "probe", "width": 3},
    ],
    "clocking": {"is_sequential": True},
}

SAMPLED = '''
from specflow.refmodel.base import RefModel


class Model(RefModel):
    OUTPUT_PORTS = ["busy", "ack"]
    PROBE_PORTS = ["in_busy", "hist"]
    PROBE_WIDTHS = {"in_busy": 1, "hist": 3}

    def reset(self):
        self.state = 0
        self.h = 0

    def outputs(self, i):
        if not hasattr(self, "state"):
            self.reset()
        self.in_busy = self.state
        self.hist = self.h
        return {"busy": self.state, "ack": int(bool(self.state and i["done_i"]))}

    def advance(self, i):
        self.h = ((self.h << 1) | i["done_i"]) & 7
        if not self.state:
            self.state = int(bool(i["go"]))
        elif i["done_i"]:
            self.state = 0
'''


class _Split(RefModel):
    OUTPUT_PORTS = ["q"]
    PROBE_PORTS = ["p"]
    PROBE_WIDTHS = {"p": 8}

    def __init__(self):
        self.q = 0
        self.p = 0

    def outputs(self, i):
        self.p = self.q
        return {"q": self.q}

    def advance(self, i):
        self.q = i["d"]
        self.p = 99      # what an attribute read AFTER the edge would see


class _Legacy(RefModel):
    OUTPUT_PORTS = ["q"]

    def step(self, i):
        return {"q": i["d"]}


def test_the_form_is_decided_by_what_the_class_implements():
    assert samples_before_edge(_Split())
    assert not samples_before_edge(_Legacy())
    assert not samples_before_edge(RefModel())


def test_step_reads_the_edge_then_takes_it_and_the_probe_is_the_edge_s_value():
    m = _Split()
    assert m.step({"d": 5}) == {"q": 0}, "outputs() comes BEFORE advance()"
    assert m.step({"d": 7}) == {"q": 5}, "the edge's load shows in the next row"
    assert m.p == 99
    assert probe_values(m, ["p"]) == {"p": 5}, (
        "the probe must be the value captured at the edge, not the attribute "
        "the edge overwrote")


def test_a_WIDE_probe_is_a_value_not_a_flag():
    class M(RefModel):
        PROBE_PORTS = ["hist", "flag"]
        PROBE_WIDTHS = {"hist": 3, "flag": 1}
        hist = 6
        flag = 6
    assert probe_values(M(), ["hist", "flag"]) == {"hist": 6, "flag": 1}


def test_the_replay_row_is_the_edge_as_sampled():
    """ack answers the inputs of its own row; busy changes the row after."""
    steps = [{"inputs": {"go": 1, "done_i": 0}, "hold": 1},
             {"inputs": {"go": 0, "done_i": 0}, "hold": 1},
             {"inputs": {"go": 0, "done_i": 1}, "hold": 1},
             {"inputs": {"go": 0, "done_i": 0}, "hold": 1}]
    rep = replay(SAMPLED, CONTRACT, steps, base="step", settle_edges=0)
    assert not rep.error, rep.error
    busy = [r["outputs"]["busy"] for r in rep.rows]
    ack = [r["outputs"]["ack"] for r in rep.rows]
    assert busy == [0, 1, 1, 0]
    assert ack == [0, 0, 1, 0], "the ack is in the row that shows BUSY and done_i"
    assert [r["outputs"]["in_busy"] for r in rep.rows] == busy
    assert [r["outputs"]["hist"] for r in rep.rows] == [0, 0, 0, 1]


def test_an_UNTIL_on_a_combinational_ack_ends_on_the_edge_it_shows():
    steps = [{"inputs": {"go": 1, "done_i": 0}, "hold": 2},
             {"inputs": {"go": 0, "done_i": 1},
              "until": {"port": "ack", "value": 1}, "timeout": 9},
             {"inputs": {"go": 0, "done_i": 0}, "hold": 1}]
    rep = replay(SAMPLED, CONTRACT, steps, base="step", settle_edges=0)
    assert len(rep.rows) == 4, [r["outputs"] for r in rep.rows]
    assert rep.rows[2]["outputs"]["ack"] == 1
    assert rep.rows[3]["inputs"]["done_i"] == 0


def test_an_UNTIL_may_wait_on_a_probe():
    steps = [{"inputs": {"go": 1, "done_i": 0},
              "until": {"port": "in_busy", "value": 1}, "timeout": 9},
             {"inputs": {"go": 0, "done_i": 0}, "hold": 1}]
    rep = replay(SAMPLED, CONTRACT, steps, base="step", settle_edges=0)
    assert not rep.notes, rep.notes
    assert len(rep.rows) == 3


def test_the_author_is_told_the_convention_its_witness_was_written_in():
    assert oracle_gen.samples_before_edge_source(SAMPLED)
    assert not oracle_gen.samples_before_edge_source(
        "def step(self, i):\n    return {}\n")
    assert oracle_gen.samples_before_edge_source(""), (
        "a run with no witness yet writes it in the current form")
    pre = oracle_gen.shared_prefix("{}", CONTRACT, preponed=True)
    post = oracle_gen.shared_prefix("{}", CONTRACT, preponed=False)
    assert "BEFORE the edge takes effect" in pre
    assert "AFTER that same" in post and "BEFORE the edge takes effect" not in post


def _check(uid: str, src: str) -> RequirementOracle:
    return RequirementOracle(req_uid=uid, tp_uids=["TP-0"], clause="", source=src)


def test_the_cover_can_leave_out_every_body_the_population_refutes():
    """Two designs that differ on `busy` at the edge after `go`. The refuted
    body convicts both; excluded, it cannot ship even as its requirement's floor.
    """
    other = SAMPLED.replace("self.state = int(bool(i[\"go\"]))", "self.state = 0")
    population = [SAMPLED, other]
    steps = {"TP-0": [{"inputs": {"go": 1, "done_i": 0}, "hold": 3}]}
    held = {
        "R1": _check("R1", "def decide(trace):\n"
                           "    return (False, trace[0]['edge'], 'always')\n"),
        "R2": _check("R2", "def decide(trace):\n"
                           "    b = [r['outputs']['busy'] for r in trace]\n"
                           "    return (1 in b, None, str(b))\n"),
    }
    req_of = {"R1": "R1", "R2": "R2"}
    kept = cover.select(held, req_of, population, CONTRACT, steps, base="step")
    strict = cover.select(held, req_of, population, CONTRACT, steps, base="step",
                          exclude_refuted=True)
    assert kept is not None and strict is not None
    assert "R1" in kept.kept, "without the switch the floor keeps R1's only body"
    assert strict.refuted == ("R1",)
    assert "R1" not in strict.kept and "R2" in strict.kept


# ------------------------------------------------------- the settle tail


def _rows(tail_from: int, n: int, *, fire: int) -> list[dict]:
    """`n` rows; `a` rises at row `fire`; `b` never does; rows from
    `tail_from` on are settle rows."""
    out = []
    for k in range(n):
        r = {"edge": k, "inputs": {}, "outputs": {"a": int(k >= fire), "b": 0}}
        if k >= tail_from:
            r["tail"] = True
        out.append(r)
    return out


def test_NO_WINDOW_opens_in_the_tail_and_one_opened_before_it_is_judged_there():
    """The tail holds the last inputs so the design can answer them; a window
    opened on what that re-issues is a scenario no step wrote. One opened while
    the stimulus drove still runs into the tail and lapses there."""
    from specflow.refmodel import temporal as T

    def windows(rows):
        return T.after(rows, lambda r: r["outputs"]["a"] == 1, until=T.TO_END)

    assert windows(_rows(tail_from=6, n=10, fire=7)) == []
    ws = windows(_rows(tail_from=6, n=10, fire=3))
    assert len(ws) == 1
    w = ws[0]
    assert T.eventually(w, lambda r: r["outputs"]["b"] == 1, strong=True)[0] is False
    assert T.sequence(w, lambda r: r["outputs"]["a"] == 1,
                      lambda r: r["outputs"]["b"] == 1, strong=True)[0] is False


def test_a_hand_built_window_in_the_tail_is_still_cut_off_not_failed():
    """`Window.opened_in_tail` covers a window a check built without `after`."""
    from specflow.refmodel import temporal as T

    rows = _rows(tail_from=6, n=10, fire=7)
    w = T.Window(start=rows[7], rows=rows[7:], closed=False, prev=rows[6])
    assert T.eventually(w, lambda r: r["outputs"]["b"] == 1, strong=True)[0] is None


def test_a_state_is_a_tail_state_only_if_it_BEGINS_in_the_tail():
    from specflow.refmodel.oracles import transactional_view

    rows = _rows(tail_from=4, n=8, fire=6)
    view = transactional_view(rows)
    assert [bool(r.get("tail")) for r in view] == [False, True]
    assert view[1]["first_edge"] == 6


def test_the_replay_marks_exactly_the_settle_rows():
    steps = [{"inputs": {"go": 1, "done_i": 0}, "hold": 3}]
    rep = replay(SAMPLED, CONTRACT, steps, base="step", settle_edges=5)
    assert [bool(r.get("tail")) for r in rep.rows] == [False] * 3 + [True] * 5


def test_a_fresh_model_starts_in_its_RESET_state():
    """The replay and the gate drive a model without the simulator's reset;
    state kept only in `reset` must still be there on the first edge."""
    class M(RefModel):
        OUTPUT_PORTS = ["q"]

        def reset(self):
            self.q = 3

        def outputs(self, i):
            return {"q": self.q}

        def advance(self, i):
            self.q = i["d"]

    assert M().step({"d": 1}) == {"q": 3}


# ------------------------------------ evidence for a population-refuted check


_LATE_ACK = ("from specflow.refmodel.temporal import after, eventually\n"
             "def decide(trace):\n"
             "    ws = after(trace, lambda r: r['outputs']['busy'] == 1 and r['inputs']['done_i'] == 1,\n"
             "               until=lambda r: r['outputs']['busy'] == 0)\n"
             "    if not ws:\n"
             "        return (None, None, 'never')\n"
             "    return eventually(ws[0], lambda r: r['outputs']['ack'] == 1,\n"
             "                      strong=True, after_activation=True)\n")


def test_the_witness_rows_for_a_refuted_check_are_centred_on_ITS_failure():
    """The ack is in the row showing BUSY and done_i; a check demanding it on a
    later row fails there, and the author is shown that row, marked."""
    from specflow.oracles_stage import _witness_failure_rows

    steps = {"TP-1": [{"inputs": {"go": 1, "done_i": 0}, "hold": 2},
                      {"inputs": {"go": 0, "done_i": 1}, "hold": 1},
                      {"inputs": {"go": 0, "done_i": 0}, "hold": 3}]}
    ev = _witness_failure_rows(_check("R", _LATE_ACK), SAMPLED, ["TP-1"], CONTRACT,
                               steps, base="step", transactional=True)
    assert ev is not None and ev.origin == "witness"
    block = oracle_gen.witness_rows_block(ev)
    assert block.count('"your_check_failed_here": true') == 1
    assert "The witness is not the answer; the specification is." in block

    same_row = _LATE_ACK.replace("after_activation=True", "after_activation=False")
    assert _witness_failure_rows(_check("R", same_row), SAMPLED, ["TP-1"], CONTRACT,
                                 steps, base="step", transactional=True) is None, (
        "a check the witness satisfies gets no rows -- they would not show its failure")


def test_the_refutation_message_states_the_consequence_only_when_it_is_real():
    from specflow.oracles_stage import _refuted_everywhere

    told = _refuted_everywhere(7, [("TP-1", "")], shown=True, excluded=True)
    assert "NOT SHIPPED" in told and "rows there are shown below" in told
    assert "NOT SHIPPED" not in _refuted_everywhere(7, [("TP-1", "")])


def test_the_repair_round_PASSES_the_rows_and_the_build_passes_the_switch():
    """Source pins: a call site inside `run_oracle_stage` has been deleted on
    this branch without failing a behavioural test."""
    import inspect

    from specflow import integration, oracles_stage

    stage = inspect.getsource(oracles_stage.run_oracle_stage)
    assert "rows={u: r for u, r in refuted_rows.items() if u in ask} or None" in stage
    assert "_witness_failure_rows(" in stage
    build = inspect.getsource(integration.build_artifacts)
    assert "refuted_excluded=bool(ship_cover and admit_pool and exclude_refuted)" in build


def test_a_cell_only_a_REFUTED_body_separates_is_a_target_when_refuted_bodies_do_not_ship():
    """Two designs differ on `busy` after `go`. The only held check passes one
    design on that testpoint and fails both elsewhere -- it separates the cell
    while being refuted. A run that will not ship it must still author there."""
    import inspect

    from specflow import oracles_stage

    other = SAMPLED.replace('self.state = int(bool(i["go"]))', "self.state = 0")
    population = [SAMPLED, other]
    stim = {"TP-0": [{"inputs": {"go": 1, "done_i": 0}, "hold": 3}],
            "TP-1": [{"inputs": {"go": 0, "done_i": 0}, "hold": 2}]}
    src = ("def decide(trace):\n"
           "    b = [r['outputs']['busy'] for r in trace]\n"
           "    if any(r['inputs']['go'] for r in trace):\n"
           "        return (1 in b, None, str(b))\n"
           "    return (False, trace[0]['edge'], 'no request')\n")
    held = {"R1": RequirementOracle(req_uid="R1", tp_uids=["TP-0", "TP-1"],
                                    clause="", source=src)}
    plan = [{"uid": "TP-0", "covers": ["R2@1"]}, {"uid": "TP-1", "covers": ["R2@1"]}]
    by_uid = {"R2": {"uid": "R2", "text": "busy rises after go"}}
    kw = dict(population=population, held=held, contract=CONTRACT,
              stimulus_by_tp=stim, testplan=plan, by_uid=by_uid, normalized={},
              budget=4, base="step", transactional=True)
    seen, _ = oracles_stage._cell_targets(**kw)
    told, _ = oracles_stage._cell_targets(**kw, ignore_refuted=True)
    assert seen == [], "R1 separates the cell, so without the switch it is not blind"
    assert [t["requirement"]["uid"] for t in told] == ["R2"]
    assert "ignore_refuted=refuted_excluded" in inspect.getsource(oracles_stage.run_oracle_stage)


def test_refutation_LEADS_an_advisory_latency_finding():
    """A check both latency-fragile and population-refuted must be told it is
    refuted (and shown the witness failing it); the latency note rides after."""
    import inspect

    from specflow import oracles_stage

    src = inspect.getsource(oracles_stage.run_oracle_stage)
    assert "if uid in rejected or (prior and not prior.startswith(_latency.PREFIX)):" in src
    assert 'why += "\\n\\nSeparately -- " + prior' in src
