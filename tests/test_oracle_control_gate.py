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



# The three tests that lived here screened the judge's oracles. Screening is
# `specflow/oracles_stage.py` now, and the property they protected -- that a
# gate which did not run is DISTINGUISHABLE from one that found nothing -- is
# `test_no_witness_is_reported_rather_than_assumed` in `test_oracles_stage.py`.
# What stays is the wiring, because a control on disk that nothing loads is the
# state this file was born in.


# --------------------------------------------------------- the gate is wired


def test_the_benchmark_runner_resolves_the_control_it_ships():
    """A control on disk that nothing loads is the state this file was born in."""
    from benchmarks.run_chipverilog import control_model

    found = control_model("i2c_master_bit_ctrl")
    assert found is not None, "the i2c control exists and must be found"
    assert Path(found).is_file()
    assert control_model("no_such_design_exists") is None


def test_the_control_is_threaded_through_every_layer_between_them():
    """Four signatures separate the runner from the gate that uses it.

    Each was individually reasonable and the parameter was dropped at the first
    of them, so the gate silently never ran. Asserting on the signatures keeps
    a later refactor from re-opening the same hole without touching this test.
    """
    from eda_agent.specflow_node import run_specflow_node
    from eda_agent.top_agent import TopAgentConfig
    from specflow.integration import build_artifacts
    from specflow.oracles_stage import run_oracle_stage

    assert "refmodel_control" in inspect.signature(run_specflow_node).parameters
    assert "refmodel_control" in inspect.signature(build_artifacts).parameters
    assert "control_source" in inspect.signature(run_oracle_stage).parameters
    assert "specflow_refmodel_control" in TopAgentConfig.__dataclass_fields__


def test_both_run_refmodel_call_sites_pass_the_control():
    """`integration.py` calls it twice -- generate, and re-validate-after-stale.

    Its own comment says the second must use "the SAME arguments"; a control
    passed to only one of them makes a `--reuse` run silently weaker than a
    fresh one, which is the defect that comment already records happening once.
    """
    import ast

    tree = ast.parse(Path("specflow/integration.py").read_text())
    calls = [n for n in ast.walk(tree)
             if isinstance(n, ast.Call)
             and getattr(n.func, "id", "") == "run_refmodel"]
    assert len(calls) == 2, "generate, and re-validate-after-stale"
    for call in calls:
        kw = {k.arg for k in call.keywords}
        assert "control_source" in kw
        # And the oracle set, or the model stage would generate its own oracles
        # after the model exists -- which is what having a stage removed.
        assert "oracle_set" in kw

    staged = [n for n in ast.walk(tree)
              if isinstance(n, ast.Call)
              and getattr(n.func, "id", "") == "run_oracle_stage"]
    assert len(staged) == 1
    assert "control_source" in {k.arg for k in staged[0].keywords}
