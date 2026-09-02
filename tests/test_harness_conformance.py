"""The harness itself, against known-correct (RTL, model) pairs.

Every other simulator-backed test in this repo drives ONE fixture: a
combinational half-adder. With `LATENCY_CYCLES = 0`, `Env.settle`'s
`max(1, latency + 1)` is 1 and the design has no reset port at all, so the
multi-edge branch of `settle` and the whole of `Env.reset` were never executed by
the test suite. Three alignment bugs lived there undetected, and were found only
by transliterating a golden RTL by hand and noticing that a *faithful* oracle
scored 77 of 168.

These pairs are written to agree by construction. Any failure is a defect in the
harness -- in how it clocks, resets, samples, or bundles inputs -- never in the
fixture. That is what makes this the precondition for the rest of the timing
work: without it, a change to `runtime.py` can only be evaluated against a live
design whose own correctness is unknown.

Deliberately repo assets rather than per-design golden RTL, because production
has no golden to compare against and a conformance suite that only works on a
benchmark is not a conformance suite.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from specflow.run import run_suite
from specflow.tb import runtime
from specflow.tb.render import render_suite

REPO = Path(__file__).resolve().parents[1]
FIXTURES = REPO / "tests" / "fixtures" / "harness"

needs_verilator = pytest.mark.skipif(
    not shutil.which("verilator"), reason="verilator not installed"
)

#: What each fixture is here to pin. A name alone does not say why it exists.
CASES = {
    "comb_adder": "the shape already covered -- the control, not the point",
    "reg1": "one registered output; the simplest sequential path",
    "pipe3": "three registers in series; latency_cycles 3, where settle's "
             "multi-edge branch first matters",
    "prescaled_fsm": "a 5-phase FSM advancing one phase per clk_en tick, two of "
                     "whose phases drive identical outputs -- the i2c shape in "
                     "miniature",
    "activelow_io": "an active-low input and an open-drain output, for which 0 "
                    "is not idle",
    "clock_named_clock": "reg1 with the clock port named `clock`; runtime.py "
                         "hardcodes getattr(dut, 'clk') at three sites",
    "unreset_reg": "a register the design never resets -- the shape of golden "
                   "i2c's `dout`, and the one place a previous testpoint's "
                   "state can survive into the next",
}


#: Stimulus per fixture. Only the prescaled FSM needs one: the harness no longer
#: guesses how long to hold a vector from `LATENCY_CYCLES`, so a design that
#: takes many clocks per phase has to say so. That is the point of Phase 3 --
#: duration is a property of the test, not of a port's latency figure.
STIMULUS = {
    "prescaled_fsm": [
        {"inputs": {"ena": 1, "prescale": 2, "go": 0}, "hold": 4},
        # Drive the command and wait for the design to acknowledge it, rather
        # than guessing an edge count. At prescale=2 one phase takes 3 clocks
        # and the sequence is 5 phases, but the test does not need to know that.
        {"inputs": {"ena": 1, "prescale": 2, "go": 1},
         "until": {"port": "done", "value": 1}, "timeout": 200},
        {"inputs": {"ena": 1, "prescale": 2, "go": 0}, "hold": 4},
    ],
}


def _plan(contract: dict) -> tuple[list[dict], list[dict], list[dict]]:
    """One testpoint, one bin, one check over every declared output.

    Hand-written rather than run through S1-S3: the agent chain is not what is
    under test here, and replaying it would make a harness failure look like a
    generation failure.
    """
    outs = [p["name"] for p in contract["io"] if p.get("dir") == "output"]
    tp = {
        "uid": "TP-0000", "rev": 1, "covers": ["REQ-0000@1"],
        "dimension": "D2_control_flow",
        "stimulus": "exercise every declared input",
        "expected_response": "outputs match the reference model",
        "check_method": "compare against the reference model",
    }
    return (
        [tp],
        [{"uid": "BIN-0000", "rev": 1, "covers": ["TP-0000@1"], "condition": "any"}],
        [{"uid": "CHK-0000", "rev": 1, "covers": ["TP-0000@1"],
          "expr": "outputs match the reference model", "signals": outs}],
    )


def _build(name: str, tmp_path: Path):
    src = FIXTURES / name
    contract = json.loads((src / "contract.json").read_text(encoding="utf-8"))
    testplan, bins, checks = _plan(contract)
    suite = tmp_path / "suite"
    stim = STIMULUS.get(name)
    manifest = render_suite(
        testplan=testplan, bins=bins, checks=checks, contract=contract,
        out_dir=suite,
        stimulus_by_tp={"TP-0000": stim} if stim else None,
    )
    return src, contract, suite, manifest


@needs_verilator
@pytest.mark.parametrize("name", sorted(CASES))
def test_harness_agrees_with_a_correct_pair(name, tmp_path):
    """A hand-matched RTL and model must agree at every checked point."""
    src, contract, suite, manifest = _build(name, tmp_path)
    outcome = run_suite(
        rtl_path=src / "dut.sv",
        hdl_toplevel=contract["module_name"],
        suite_dir=suite,
        refmodel_path=src / "ref_model.py",
        coverage=False,
        trace=False,
    )
    assert outcome.build_ok, f"{name}: {outcome.build_log}"
    assert len(outcome.results) == len(manifest.testpoints), (
        f"{name}: a testpoint produced no record"
    )
    failing = [
        (u, r.mismatches) for u, r in outcome.results.items() if r.status != "PASS"
    ]
    assert not failing, (
        f"{name} ({CASES[name]}) disagreed. The pair is correct by construction, "
        f"so this is a harness defect: {failing}"
    )


@needs_verilator
@pytest.mark.parametrize("name", sorted(CASES))
def test_every_case_rejects_a_tied_off_dut(name, tmp_path):
    """Agreement is only evidence if disagreement was possible.

    This is the half that matters. `clock_named_clock` passed the test above
    while proving nothing: `runtime.py` looks up the clock as
    `getattr(dut, "clk")`, finds nothing on a port named `clock`, and therefore
    `Env.start` never calls `reset()`. Nothing drives `rst_n`, it reads 0, the
    DUT sits in reset at q=0 -- and `_bundle` reads that same `rst_n=0` off the
    DUT, so the model resets too. Both sides say 0 for the whole run and agree
    for entirely the wrong reason.

    A tied-off DUT catches exactly that: if the harness cannot tell a correct
    design from a constant one, the case is vacuous no matter what it scored.
    """
    src, contract, suite, _ = _build(name, tmp_path)
    outs = [
        (p["name"], int(p.get("width") or 1))
        for p in contract["io"] if p.get("dir") == "output"
    ]
    text = (src / "dut.sv").read_text(encoding="utf-8")
    head = text.split(");", 1)[0].replace("output reg", "output")
    body = "\n".join(f"  assign {n} = {w}'d0;" for n, w in outs)
    broken = tmp_path / "broken.sv"
    broken.write_text(f"{head});\n{body}\nendmodule\n", encoding="utf-8")

    outcome = run_suite(
        rtl_path=broken, hdl_toplevel=contract["module_name"], suite_dir=suite,
        refmodel_path=src / "ref_model.py", coverage=False, trace=False,
    )
    assert outcome.build_ok, f"{name}: {outcome.build_log}"
    assert outcome.failing, (
        f"{name} ({CASES[name]}): a tied-off DUT passed. The harness cannot "
        f"distinguish this design from a constant, so the case above proves "
        f"nothing."
    )


# --------------------------------------------------------------- reach (Phase 3)


_LATE_BUG_MODEL = '''
"""Correct until the very last phase, where `done` is dropped.

A bug that only shows up when a sequence COMPLETES is exactly what a suite with
too few edges cannot see. That is not hypothetical: every testpoint on
i2c_master_bit_ctrl had three vectors, and 61 of 168 could not finish a single
command.
"""

from specflow.refmodel.base import RefModel


class Model(RefModel):
    OUTPUT_PORTS = ["busy", "done"]
    LATENCY_CYCLES = 5

    def reset(self):
        self.cnt = 0
        self.clk_en = 1
        self.state = 0
        self.busy = 0
        self.done = 0

    def step(self, i):
        if not hasattr(self, "state"):
            self.reset()
        if not i.get("rst_n", 1):
            self.reset()
            return {"busy": self.busy, "done": self.done}
        ena = i.get("ena", 0)
        o_cnt, o_clk_en, o_state = self.cnt, self.clk_en, self.state
        if o_cnt == 0 or not ena:
            self.cnt, self.clk_en = self.mask(i.get("prescale", 0), 4), 1
        else:
            self.cnt, self.clk_en = o_cnt - 1, 0
        self.done = 0
        if o_clk_en and ena:
            if o_state == 0:
                if i.get("go", 0):
                    self.state, self.busy = 1, 1
            elif o_state in (1, 2, 3):
                self.state = o_state + 1
            elif o_state == 4:
                # THE BUG: the sequence ends but `done` is never pulsed.
                self.state, self.busy = 0, 0
        return {"busy": self.busy, "done": self.done}
'''


@needs_verilator
@pytest.mark.parametrize(
    "stimulus,must_catch",
    [
        (STIMULUS["prescaled_fsm"], True),
        # The same test with every step held for a single edge -- what a bare
        # dict now means, and what the whole suite effectively had before a step
        # could state its own duration.
        ([{"inputs": s["inputs"], "hold": 1} for s in STIMULUS["prescaled_fsm"]],
         False),
    ],
    ids=["until-reaches-the-end", "one-edge-per-step-does-not"],
)
def test_a_late_bug_is_only_caught_if_the_sequence_completes(
    stimulus, must_catch, tmp_path
):
    """Reach is the point of `hold`/`until`, and this is what reach buys.

    The model is correct except that it drops `done` at the final phase. Waiting
    for the design to acknowledge finds it; giving every step one edge never
    gets there, and the suite reports a clean pass over a real disagreement.
    """
    src = FIXTURES / "prescaled_fsm"
    contract = json.loads((src / "contract.json").read_text(encoding="utf-8"))
    testplan, bins, checks = _plan(contract)
    suite = tmp_path / "suite"
    render_suite(testplan=testplan, bins=bins, checks=checks, contract=contract,
                 out_dir=suite, stimulus_by_tp={"TP-0000": stimulus})
    model = tmp_path / "late_bug.py"
    model.write_text(_LATE_BUG_MODEL, encoding="utf-8")

    outcome = run_suite(
        rtl_path=src / "dut.sv", hdl_toplevel=contract["module_name"],
        suite_dir=suite, refmodel_path=model, coverage=False, trace=False,
    )
    assert outcome.build_ok, outcome.build_log
    caught = bool(outcome.failing)
    assert caught is must_catch, (
        "waiting for the design to finish must catch a bug at the last phase, "
        "and one edge per step must not -- that difference is the whole reason "
        f"a step can state its own duration. caught={caught}"
    )


# --------------------------------------------------------- testpoint isolation


def _two_testpoints(contract: dict):
    """Two testpoints in one suite: the first LOADS, the second must not see it."""
    outs = [p["name"] for p in contract["io"] if p.get("dir") == "output"]
    tps, bins, checks = [], [], []
    for i in range(2):
        uid = f"TP-{i:04d}"
        tps.append({"uid": uid, "rev": 1, "covers": ["REQ-0000@1"],
                    "dimension": "D2_control_flow", "stimulus": "...",
                    "expected_response": "...", "check_method": "..."})
        bins.append({"uid": f"BIN-{i:04d}", "rev": 1, "covers": [f"{uid}@1"],
                     "condition": "any"})
        checks.append({"uid": f"CHK-{i:04d}", "rev": 1, "covers": [f"{uid}@1"],
                       "expr": "outputs match the reference model", "signals": outs})
    return tps, bins, checks


@needs_verilator
def test_a_testpoint_does_not_inherit_the_previous_one_s_state(tmp_path):
    """The defect this found, in the smallest design that can hold it.

    cocotb runs every test module in ONE simulator process by default, and the
    DUT is elaborated once -- so a register the design does not reset keeps
    whatever the previous testpoint left in it, and `Env.reset()` cannot clear
    it because there is no reset path to drive.

    Measured on the golden `i2c_master_bit_ctrl`, whose `dout` is exactly this
    shape: TP-0002 PASSES run alone and FAILS inside the 168-test suite, because
    two earlier testpoints left `dout` at 1 while the reference model -- a fresh
    `Model()` per test -- starts at 0. It accounted for 60 of the 99 testpoints a
    CORRECT design failed, and it made every verdict depend on test ORDER.

    Here TP-0000 loads a 1 into the unreset register and TP-0001 never loads at
    all, so TP-0001 can only pass if its DUT started fresh.
    """
    src = FIXTURES / "unreset_reg"
    contract = json.loads((src / "contract.json").read_text(encoding="utf-8"))
    testplan, bins, checks = _two_testpoints(contract)
    suite = tmp_path / "suite"
    render_suite(
        testplan=testplan, bins=bins, checks=checks, contract=contract,
        out_dir=suite,
        stimulus_by_tp={
            # Leaves `latched` at 1 in the DUT.
            "TP-0000": [{"inputs": {"load": 1, "d": 1}, "hold": 4}],
            # Never loads: `latched` must still read its power-on 0.
            "TP-0001": [{"inputs": {"load": 0, "d": 0}, "hold": 4},
                        {"inputs": {"load": 0, "d": 1}, "hold": 4}],
        },
    )
    outcome = run_suite(
        rtl_path=src / "dut.sv", hdl_toplevel=contract["module_name"],
        suite_dir=suite, refmodel_path=src / "ref_model.py",
        coverage=False, trace=False,
    )
    assert outcome.build_ok, outcome.build_log
    failing = [(u, r.mismatches) for u, r in outcome.results.items() if r.status != "PASS"]
    assert not failing, (
        "a testpoint inherited state from the one before it -- the DUT was not "
        f"re-elaborated: {failing}"
    )


def test_each_testpoint_gets_its_own_simulator_process(tmp_path, monkeypatch):
    """The mechanism, pinned without a simulator.

    Behavioural coverage above needs an unreset register to detect the leak at
    all. This asserts the property directly, so a future change that batches the
    modules back together is caught even on a design where nothing happens to
    carry over.
    """
    import specflow.run as run_module

    calls: list[list[str]] = []

    class _Runner:
        def build(self, **_):
            return None

        def test(self, *, test_module, **_):
            calls.append(list(test_module))

    monkeypatch.setattr(run_module, "get_runner", lambda _: _Runner(), raising=False)
    monkeypatch.setattr(
        "cocotb_tools.runner.get_runner", lambda _: _Runner(), raising=False)

    suite = tmp_path / "suite"
    (suite / "tests").mkdir(parents=True)
    (suite / "manifest.json").write_text(
        json.dumps({"modules": ["test_TP0000", "test_TP0001", "test_TP0002"]}),
        encoding="utf-8")
    model = tmp_path / "ref_model.py"
    model.write_text("class Model:\n    OUTPUT_PORTS = []\n", encoding="utf-8")

    run_suite(rtl_path=tmp_path / "dut.sv", hdl_toplevel="Dut", suite_dir=suite,
              refmodel_path=model, coverage=False, trace=False)

    assert calls == [["test_TP0000"], ["test_TP0001"], ["test_TP0002"]], calls


#: A model that reads one of its own registers a clock generation too early --
#: the defect class that produced BOTH bugs in the hand-written i2c control
#: oracle. `s2` takes the freshly computed `s1` instead of the previous one, so
#: the pipeline runs a stage short.
_EARLY_READ_MODEL = '''
from specflow.refmodel.base import RefModel


class Model(RefModel):
    OUTPUT_PORTS = ["q"]
    LATENCY_CYCLES = 3

    def reset(self):
        self.s1 = self.s2 = self.s3 = 0

    def step(self, i):
        if not hasattr(self, "s1"):
            self.reset()
        if not i.get("rst_n", 1):
            self.reset()
        else:
            prev2 = self.s2
            self.s1 = self.mask(i["d"] + 1, 8)
            self.s2 = self.s1          # BUG: the fresh s1, not the previous one
            self.s3 = prev2
        return {"q": self.s3}
'''


@needs_verilator
def test_the_internal_trace_localises_a_one_generation_early_read(tmp_path, monkeypatch):
    """The capability `benchmarks/divergence_trace.py` rests on.

    A reference-model defect is almost never visible where it happens. Both
    control-oracle bugs were "read a value from the wrong clock generation" and
    each surfaced many edges later, in a different signal. So the per-edge
    internal recording has to show the offending REGISTER diverging strictly
    before any output does -- otherwise the tool localises nothing and the
    analyst is back to reading the score.
    """
    monkeypatch.setenv("SPECFLOW_TRACE_INTERNALS", "s1,s2,s3")
    import importlib

    import specflow.tb.runtime as runtime
    importlib.reload(runtime)
    try:
        _src, _contract, suite, _manifest = _build("pipe3", tmp_path)
        model = tmp_path / "ref_model.py"
        model.write_text(_EARLY_READ_MODEL, encoding="utf-8")
        run_suite(
            rtl_path=FIXTURES / "pipe3" / "dut.sv", hdl_toplevel="Dut",
            suite_dir=suite, refmodel_path=model, iteration=0,
            coverage=False, trace=False,
        )
        dump = json.loads(
            (suite / "results" / "TP-0000.trace.json").read_text(encoding="utf-8")
        )
    finally:
        monkeypatch.delenv("SPECFLOW_TRACE_INTERNALS", raising=False)
        importlib.reload(runtime)

    def internals_differ(r):
        return any(r["dut_internal"][n] != r["model_internal"][n]
                   for n in ("s1", "s2", "s3"))

    def output_differs(r):
        return r["dut"]["q"] != r["model"]["q"]

    assert any(internals_differ(r) for r in dump["edges"]), \
        "the seeded defect produced no internal divergence at all"
    assert any(output_differs(r) for r in dump["edges"]), \
        "the seeded defect never reached an output; it would not be a defect"

    # The property that matters, and the one the whole tool rests on: an edge
    # where a REGISTER already disagrees while every OUTPUT still agrees. That
    # is the edge a score can never point at -- on the i2c control oracle the
    # equivalent edge was e7, `sto_condition` differing with `al` still matching
    # on both sides, one edge before the symptom appeared.
    #
    # Not "the first internal divergence strictly precedes the first output
    # one": `q` IS the register `s3` in this fixture, so the last stage and the
    # output necessarily move together, and the model has already been stepped
    # during `Env.reset` before edge 0 is recorded. Those are properties of the
    # fixture and the harness, not of the instrument.
    hidden = [r["edge"] for r in dump["edges"]
              if internals_differ(r) and not output_differs(r)]
    assert hidden, (
        "no edge shows an internal disagreement while the outputs agree, so the "
        "trace adds nothing a plain output comparison did not already give"
    )


def test_a_vacuous_testpoint_is_RECORDED_not_raised():
    """`Env.finish` must not assert, and the second assert is why this exists.

    `assert self.sb.invoked` raised on a testpoint no check fired on. That is
    the definition of UNCOVERED -- the record two lines above already calls it
    `NOT_EXERCISED` -- so raising turned the coverage measurement into a suite
    crash. It also made cover bins load-bearing for the RUNTIME long after they
    stopped being load-bearing for the METRIC, since coverage is now the
    oracles' own tri-state and nothing downstream of the suite reads a bin.

    With it gone a suite renders and runs with no checks and no bins, which is
    what lets the S3 stage be skipped -- 335 model calls on c1-i2c for an
    artifact the oracle stage never reads.

    A source pin rather than a behavioural one: `Env` needs a live cocotb
    simulation to instantiate, and the property being fixed is precisely that
    two lines of source are absent.
    """
    import inspect

    from specflow.tb.runtime import Env

    # COMMENTS STRIPPED FIRST. The removal is explained in a comment that
    # quotes the very line it removed, so a naive substring search finds the
    # explanation and reports the bug as unfixed.
    src = inspect.getsource(Env.finish)
    code = "\n".join(ln for ln in src.splitlines()
                     if not ln.lstrip().startswith("#"))
    assert "assert self.sb.invoked" not in code
    assert "assert not self.sb.failed" not in code
    # The tri-state the assert used to pre-empt is still computed and recorded.
    assert "NOT_EXERCISED" in code
    assert '"checks_invoked"' in code


@needs_verilator
def test_a_MID_SEQUENCE_reset_is_recorded_and_leaves_no_hole(tmp_path):
    """A reset step must appear in the trace, and must not break its continuity.

    `reset()` used to tick the clock without recording, with two consequences
    that no verdict could show.

    A reset-behaviour check could never fire. The stimulus asserts reset, the
    DUT sees it, and the recording contains NO ROW in which the reset port is
    active -- so an oracle whose activation is "reset is asserted" abstains on
    the scenario written to exercise it. Measured on one i2c run: the stimulus
    reset in 158 of 322 testpoints and every recorded trace showed reset in
    zero, which is 4 of that run's 53 abstentions attributable to the harness
    rather than the stimulus or the check.

    And the trace went DISCONTINUOUS: with a reset at step N, the row for step
    N-1 sat directly beside the row for step N+1. A check comparing row i with
    row i+1 -- which is what every skew and `nexttime` check does -- then saw a
    transition that never happened at that adjacency, and could convict a
    correct design for it.
    """
    src = FIXTURES / "reg1"
    contract = json.loads((src / "contract.json").read_text(encoding="utf-8"))
    testplan, bins, checks = _plan(contract)
    suite = tmp_path / "suite"
    steps = [{"inputs": {"d": 1}, "hold": 2},
             {"reset": True},
             {"inputs": {"d": 1}, "hold": 2}]
    render_suite(testplan=testplan, bins=bins, checks=checks, contract=contract,
                 out_dir=suite, stimulus_by_tp={"TP-0000": steps})
    outcome = run_suite(rtl_path=src / "dut.sv",
                        hdl_toplevel=contract["module_name"], suite_dir=suite,
                        refmodel_path=src / "ref_model.py",
                        coverage=False, trace=False)
    assert outcome.build_ok, outcome.build_log
    trace = json.loads((suite / "results" / "TP-0000.trace.json")
                       .read_text(encoding="utf-8"))
    edges = trace["edges"]

    steps_seen = sorted({e["step"] for e in edges})
    assert 1 in steps_seen, (
        f"the reset step left no row at all; steps recorded: {steps_seen}")
    assert steps_seen == list(range(steps_seen[0], steps_seen[-1] + 1)), (
        f"the recorded steps have a hole in them: {steps_seen}")

    reset_rows = [e for e in edges if e["step"] == 1]
    assert any(e["inputs"].get("rst_n") == 0 for e in reset_rows), (
        "no recorded row shows the reset asserted, so a reset-behaviour check "
        f"still cannot fire: {[e['inputs'] for e in reset_rows]}")


@needs_verilator
def test_a_trace_says_what_stimulus_it_is_a_recording_OF(tmp_path):
    """Without this a consumer can only match on `tp_uid`, which every run
    reuses -- see `stimulus_digest`."""
    from specflow.tb.runtime import stimulus_digest

    src = FIXTURES / "reg1"
    contract = json.loads((src / "contract.json").read_text(encoding="utf-8"))
    testplan, bins, checks = _plan(contract)
    suite = tmp_path / "suite"
    steps = [{"inputs": {"d": 1}, "hold": 2}, {"inputs": {"d": 0}, "hold": 2}]
    render_suite(testplan=testplan, bins=bins, checks=checks, contract=contract,
                 out_dir=suite, stimulus_by_tp={"TP-0000": steps})
    outcome = run_suite(rtl_path=src / "dut.sv",
                        hdl_toplevel=contract["module_name"], suite_dir=suite,
                        refmodel_path=src / "ref_model.py",
                        coverage=False, trace=False)
    assert outcome.build_ok, outcome.build_log
    trace = json.loads((suite / "results" / "TP-0000.trace.json")
                       .read_text(encoding="utf-8"))
    assert trace["stimulus_digest"] == stimulus_digest(steps)
    assert trace["stimulus_digest"] != stimulus_digest(steps[:1])


@needs_verilator
def test_an_open_drain_line_the_TESTBENCH_WIRES_reads_back_what_the_DUT_DRIVES(
        tmp_path):
    """The DUT must be able to observe the bus it is driving.

    WITHOUT THE WIRE the stimulus drives `bus_i` and the design drives
    `bus_oen` and nothing connects them. Measured on golden i2c across 322
    testpoints: the DUT pulled SCL low at 30,595 edges and `scl_i` read 0 at
    2,637 of them -- 8.6%, every one a coincidence of the stimulus. It drove a
    START itself 1,378 times and a START reached the pins it samples 121 times.

    An I2C specification is mostly about that bus, so a correct design fails
    every requirement written about it: six of one run's fifteen convictions of
    the GOLDEN RTL were this, one of them asserting the missing wire outright
    ("scl_oen=0 but scl_i=1, expected 0"). No repair round can fix those checks
    -- the check is right and the testbench is incomplete.

    Two halves, and the second is the one that bites. Driving the pin is not
    enough: `_bundle` builds a recorded row from the STIMULUS dict, so a wired
    line was driven correctly into the design -- its behaviour changed -- while
    the trace still reported the value the stimulus asked for. That is worse
    than the missing wire: an unwired testbench fails to exercise the bus, a
    miswired recording ASSERTS something false about it.
    """
    src = FIXTURES / "activelow_io"
    contract = json.loads((src / "contract.json").read_text(encoding="utf-8"))
    # NAMED EXPLICITLY, not derived. This fixture calls its enable `oen`
    # rather than `bus_oen`, so the `_i`/`_oen` convention finds nothing here
    # -- correctly, and `bus_lines_from` is unit-tested on its own. Deriving it
    # here would have wired NOTHING and let both of these tests pass vacuously.
    lines = [{"input": "bus_i", "oen": "oen"}]

    testplan, bins, checks = _plan(contract)
    steps = [{"inputs": {"req_n": 1, "bus_i": 1}, "hold": 4},
             {"inputs": {"req_n": 0, "bus_i": 1}, "hold": 8},
             {"inputs": {"req_n": 1, "bus_i": 1}, "hold": 4}]

    def rows(bus):
        out = tmp_path / ("wired" if bus else "open")
        render_suite(testplan=testplan, bins=bins, checks=checks,
                     contract=contract, out_dir=out / "suite",
                     stimulus_by_tp={"TP-0000": steps},
                     bus_lines=lines if bus else None)
        outcome = run_suite(rtl_path=src / "dut.sv",
                            hdl_toplevel=contract["module_name"],
                            suite_dir=out / "suite",
                            refmodel_path=src / "ref_model.py",
                            coverage=False, trace=False)
        assert outcome.build_ok, outcome.build_log
        return json.loads((out / "suite" / "results" / "TP-0000.trace.json")
                          .read_text(encoding="utf-8"))["edges"]

    def pulled_low_and_seen(edges):
        low = [e for e in edges if e["dut"].get("oen") == 0]
        return len(low), sum(1 for e in low if e["inputs"].get("bus_i") == 0)

    n_open, seen_open = pulled_low_and_seen(rows(False))
    n_wired, seen_wired = pulled_low_and_seen(rows(True))

    assert n_open and n_wired, "the design never pulled the line low at all"
    # The stimulus holds bus_i high throughout, so unwired it can NEVER read 0.
    assert seen_open == 0, (
        f"unwired, the line read low at {seen_open} of {n_open} edges -- this "
        f"test cannot tell the two apart")
    assert seen_wired == n_wired, (
        f"wired, the line read low at only {seen_wired} of {n_wired} edges the "
        f"DUT was pulling it low")


@needs_verilator
def test_the_wire_does_NOT_stop_an_external_device_holding_the_line(tmp_path):
    """Open-drain is a wired-AND, not a takeover.

    The stimulus half of the AND is how clock stretching and arbitration are
    expressed -- an external device holding the line low while the DUT has
    released it -- and if the wire overwrote the stimulus instead of ANDing
    with it, those would become untestable. A driver that clobbered
    `self._inputs` would pass the previous test and fail this one.
    """
    src = FIXTURES / "activelow_io"
    contract = json.loads((src / "contract.json").read_text(encoding="utf-8"))
    testplan, bins, checks = _plan(contract)
    suite = tmp_path / "suite"
    render_suite(testplan=testplan, bins=bins, checks=checks, contract=contract,
                 out_dir=suite,
                 stimulus_by_tp={"TP-0000": [
                     {"inputs": {"req_n": 1, "bus_i": 0}, "hold": 6}]},
                 bus_lines=[{"input": "bus_i", "oen": "oen"}])
    outcome = run_suite(rtl_path=src / "dut.sv",
                        hdl_toplevel=contract["module_name"], suite_dir=suite,
                        refmodel_path=src / "ref_model.py",
                        coverage=False, trace=False)
    assert outcome.build_ok, outcome.build_log
    edges = json.loads((suite / "results" / "TP-0000.trace.json")
                       .read_text(encoding="utf-8"))["edges"]
    held = [e for e in edges if e["step"] == 0 and e["dut"].get("oen") == 1]
    assert held, "the DUT never released the line, so this proves nothing"
    assert all(e["inputs"].get("bus_i") == 0 for e in held), (
        "the wire overwrote an external device holding the line low; clock "
        "stretching and arbitration would be untestable")


def test_the_bus_pairing_is_a_CONVENTION_that_is_returned_and_never_applied():
    """`bus_lines_from` pairs `<base>_i` with `<base>_oen` and hands the result
    back for a caller to pass explicitly.

    The contract states the relationship in PROSE -- "external open-drain SCL
    line input", "active-low SCL open-drain output enable: 0 pulls low, 1
    releases" -- with no structured field joining them. Rather than parse that,
    this pairs on the suffix. A design where the convention does not hold then
    gets a testbench that is merely UNWIRED, which is the existing behaviour,
    instead of one silently miswired.
    """
    c = {"io": [
        {"name": "scl_i", "dir": "input"}, {"name": "scl_oen", "dir": "output"},
        {"name": "sda_i", "dir": "input"}, {"name": "sda_oen", "dir": "output"},
        {"name": "ena", "dir": "input"}, {"name": "busy", "dir": "output"},
    ]}
    assert runtime.bus_lines_from(c) == [
        {"input": "scl_i", "oen": "scl_oen"},
        {"input": "sda_i", "oen": "sda_oen"}]
    # An `_i` with no matching enable is not a bus line.
    assert runtime.bus_lines_from(
        {"io": [{"name": "data_i", "dir": "input"}]}) == []
    # Nor is one whose "enable" is really an input.
    assert runtime.bus_lines_from(
        {"io": [{"name": "x_i", "dir": "input"},
                {"name": "x_oen", "dir": "input"}]}) == []
