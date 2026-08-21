"""Gate 3 must actually run, and its absence must be legible.

This file exists because of a specific measured failure. The `a-i2c` run
reported `over_strict: 0` and that was read as "no oracle is over-strict". It
meant "no control was supplied, so the gate never ran". Scored afterwards by
hand against `benchmarks/controls/i2c_master_bit_ctrl/ref_model.py`, 22 of its
54 trusted oracles (41%) were failed by that known-good model, and 10 of the 18
oracles its debug agent could not discharge were in that set -- the agent spent
its attempts on demands no correct model can satisfy.

Two separate defects, so two groups of tests: the gate was not WIRED from the
benchmark runner, and a skipped gate was INDISTINGUISHABLE from a clean one.
"""

from __future__ import annotations

import inspect
from pathlib import Path

from specflow.refmodel import trust
from specflow.refmodel.oracles import RequirementOracle
from tests.test_refmodel_session import ACK, BROKEN, CONTRACT, STIM, WORKING

TESTPLAN = [{"uid": "TP-0000", "covers": ["REQ-0000"]}]


def _oracle(source=ACK, uid="REQ-0000"):
    return RequirementOracle(req_uid=uid, tp_uids=["TP-0000"],
                             clause="ack pulses once", source=source)


# ------------------------------------------------- a skipped gate is legible


def test_over_strict_is_none_not_zero_when_no_control_was_supplied():
    """The exact ambiguity that misread the a-i2c run.

    0 and None are both falsy, so anything summing or formatting these has to
    opt in to the distinction -- but nothing can opt in to a distinction the
    data does not carry.
    """
    screened = trust.screen([_oracle()], {"REQ-0000": "not_met"}, BROKEN,
                            CONTRACT, STIM, TESTPLAN, base="step")
    assert screened.rates()["over_strict"] is None
    assert screened.control_available is False


def test_over_strict_is_a_number_once_a_control_is_supplied():
    screened = trust.screen([_oracle()], {"REQ-0000": "not_met"}, BROKEN,
                            CONTRACT, STIM, TESTPLAN, base="step",
                            control_source=WORKING)
    assert screened.rates()["over_strict"] == 0
    assert screened.control_available is True


def test_a_control_that_fails_an_oracle_discards_it():
    """The oracle demands something the known-good model does not do.

    `WORKING` pulses ack; an oracle demanding ack NEVER pulse is satisfied by
    the broken model and rejected by the good one -- which is exactly the shape
    of the 22 over-strict oracles found on a-i2c.
    """
    never = ('\ndef decide(trace):\n'
             '    for row in trace:\n'
             '        if row["outputs"]["ack"] == 1:\n'
             '            return (False, row["edge"], "ack pulsed")\n'
             '    return (True, None, "ack stayed low")\n')
    screened = trust.screen([_oracle(source=never)], {"REQ-0000": "met"},
                            BROKEN, CONTRACT, STIM, TESTPLAN, base="step",
                            control_source=WORKING)
    assert screened.trusted == []
    assert "over-strict" in screened.discarded["REQ-0000"]
    assert screened.rates()["over_strict"] == 1


# --------------------------------------------------------- the gate is wired


def test_the_benchmark_runner_resolves_the_control_it_ships():
    """A control on disk that nothing loads is the state this file was born in."""
    from benchmarks.run_chipverilog import control_model

    found = control_model("i2c_master_bit_ctrl")
    assert found is not None, "the i2c control exists and must be found"
    assert Path(found).is_file()
    assert control_model("no_such_design_exists") is None


def test_the_control_is_threaded_through_every_layer_between_them():
    """Four signatures separate the runner from `trust.screen`.

    Each was individually reasonable and the parameter was dropped at the first
    of them, so the gate silently never ran. Asserting on the signatures keeps
    a later refactor from re-opening the same hole without touching this test.
    """
    from eda_agent.specflow_node import run_specflow_node
    from eda_agent.top_agent import TopAgentConfig
    from specflow.integration import build_artifacts
    from specflow.refmodel.compose import run_refmodel

    assert "refmodel_control" in inspect.signature(run_specflow_node).parameters
    assert "refmodel_control" in inspect.signature(build_artifacts).parameters
    assert "control_source" in inspect.signature(run_refmodel).parameters
    assert "specflow_refmodel_control" in TopAgentConfig.__dataclass_fields__


def test_both_run_refmodel_call_sites_pass_the_control():
    """`integration.py` calls it twice -- generate, and re-validate-after-stale.

    Its own comment says the second must use "the SAME arguments"; a control
    passed to only one of them makes a `--reuse` run silently weaker than a
    fresh one, which is the defect that comment already records happening once.
    """
    src = Path("specflow/integration.py").read_text()
    assert src.count("rm, source = run_refmodel(") == 2
    assert src.count("control_source=refmodel_control,") == 2
