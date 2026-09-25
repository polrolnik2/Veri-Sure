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
