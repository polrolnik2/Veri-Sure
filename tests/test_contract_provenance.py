"""A contract may not state a latency or an encoding the specification does not.

Both measured on the luna6 contracts, both inherited by every stage below:
`fpu_exceptions` declared latency_cycles 1 on seven outputs of a multi-stage
block (37 convictions of golden), and `i2c_master_bit_ctrl` supplied
"conventional OpenCores command encodings" from memory with READ and WRITE
swapped.
"""
from __future__ import annotations

import json

from eda_agent.contract_linter import (invented_literals, lint_contract_json,
                                       unlicensed_latencies)

SPEC = (
    "The final output registers are updated on the rising edge of clk when "
    "enable is asserted. The output out receives the final selected result. "
    "The module asserts ack combinationally while in LOAD. When sel is high, "
    "done comes from a register. It is asserted in the cycle after the write. "
    "cmd is decoded as one of `CMD_START`, `CMD_STOP`, `CMD_READ` or `CMD_WRITE`. "
    "The flag resets to 4'b0011.")


def _timing(**lat):
    return {k: {"latency_cycles": v} for k, v in lat.items()}


def test_a_latency_no_sentence_states_is_refused():
    got = unlicensed_latencies(_timing(out=1), SPEC)
    assert [i.path for i in got] == ["timing.out.latency_cycles"]
    assert got[0].severity == "error"


def test_a_stated_count_or_a_combinational_path_licenses_it():
    # "combinationally" names ack; "in the cycle after" is the sentence after done's.
    assert unlicensed_latencies(_timing(ack=0, done=1), SPEC) == []


def test_an_omitted_latency_is_never_flagged():
    assert unlicensed_latencies({"out": {"notes": "registered stages"}}, SPEC) == []


def test_an_encoding_the_spec_does_not_give_is_refused():
    obj = {"functional_summary": ["Assume START=0001, STOP=0010, READ=0100, WRITE=1000."]}
    got = invented_literals(obj, SPEC)
    assert len(got) == 1 and "0100" in got[0].message and got[0].severity == "error"


def test_a_value_the_spec_states_passes_in_any_radix():
    obj = {"corner_cases": ["After reset the flag reads 4'h3."]}
    assert invented_literals(obj, SPEC) == []


def test_test_plan_stimulus_values_are_not_claims():
    obj = {"test_plan": ["Drive data bytes 0x00, 0x80 and 0xFF."]}
    assert invented_literals(obj, SPEC) == []


def test_lint_reports_both_when_given_the_spec():
    contract = {"module_name": "m",
                "io": [{"name": "clk", "dir": "input", "width": 1},
                       {"name": "cmd", "dir": "input", "width": 4},
                       {"name": "out", "dir": "output", "width": 1}],
                "timing": _timing(out=1),
                "functional_summary": ["Use READ=0100."]}
    issues, _ = lint_contract_json(json.dumps(contract), SPEC)
    paths = {i.path for i in issues if i.severity == "error"}
    assert "timing.out.latency_cycles" in paths
    assert "functional_summary[0]" in paths
    without, _ = lint_contract_json(json.dumps(contract))
    assert not {i.path for i in without} & paths, "no spec, no provenance claim"


# ------------------------------------------------ deleted, not regenerated

def test_unsourced_values_are_DELETED_and_the_rest_of_the_sentence_kept():
    from eda_agent.contract_linter import strip_unsourced
    obj = {"timing": _timing(out=1, ack=0),
           "functional_summary": [
               "Assume encodings: START=0001, READ=0100. Decode only when idle.",
               "WRITE=1000."],
           "test_plan": ["Drive 0x80."]}
    notes = strip_unsourced(obj, SPEC)
    assert "latency_cycles" not in obj["timing"]["out"], "an unstated latency is deleted"
    assert obj["timing"]["ack"]["latency_cycles"] == 0, "a stated one is kept"
    assert obj["functional_summary"] == ["Decode only when idle."]
    assert obj["test_plan"] == ["Drive 0x80."], "stimulus choices are not claims"
    assert len(notes) == 3
    assert invented_literals(obj, SPEC) == []
    assert unlicensed_latencies(obj["timing"], SPEC) == []


def test_both_contract_builders_delete_before_the_gate_and_import_only_defines():
    """SOURCE PINS: the deletion runs on every architect output before lint,
    so a generated value never reaches a repair round; the evidence driver
    imports the shared defines header and nothing else."""
    import inspect
    from pathlib import Path

    from eda_agent import top_agent
    build = inspect.getsource(top_agent.TopAgent._build_contract_json)
    assert build.count("_unsourced_deleted(") == 2
    assert build.index("_unsourced_deleted(") < build.index("lint_contract_json(contract_json")
    driver = (Path(__file__).resolve().parent.parent
              / "docs/evidence/e7_contract.py").read_text()
    assert "strip_unsourced(blob, spec)" in driver
    assert "encoding.find_defines(TASK)" in driver
