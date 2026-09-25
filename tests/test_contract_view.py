"""Every stage gets the specification; the contract keeps only structured facts.

Measured on luna6: normalize, S2, S3, stimulus, the witness, the population,
the reference model and the check author saw requirements + contract, never the
specification, so the contract's model-written paraphrase was the specification
for everything that decides the checks.
"""
from __future__ import annotations

import inspect

from specflow import contract_view
from specflow.fanout import SPEC_AUTHORITY, spec_section

SPEC = """Ports:
    cmd[3:0]: Bit-level command. Decoded as `CMD_START` or `CMD_STOP`.
    busy: Bus busy indicator, set after START.

Behaviour follows.
"""

CONTRACT = {
    "source_of_truth": "spec", "module_name": "m",
    "parameters": [{"name": "W", "default": "8", "type": "int", "notes": "a paraphrase"}],
    "io": [
        {"name": "cmd", "dir": "input", "width": 4, "notes": "Paraphrased command.",
         "encoding": {"CMD_START": 1, "CMD_STOP": 2}, "encoding_complete": True},
        {"name": "busy", "dir": "output", "width": 1, "notes": "Paraphrase."},
        {"name": "clk", "dir": "input", "width": 1, "notes": "Clock."},
        {"name": "in_seq", "dir": "probe", "width": 1, "spec_term": "sequence"},
    ],
    "clocking": {"is_sequential": True, "clock": {"name": "clk", "edge": "posedge"},
                 "reset": {"name": "rst", "active": "high", "type": "synchronous",
                           "notes": "prose"}, "notes": "more prose"},
    "timing": {"busy": {"latency_cycles": 1, "notes": "why"},
               "other": {"notes": "unstated"}},
    "functional_summary": ["x"], "corner_cases": ["y"], "test_plan": ["z"],
    "guidance": {"coder": ["w"]},
}


def test_only_structured_facts_survive():
    s = contract_view.structured(CONTRACT, SPEC)
    for k in contract_view.PROSE:
        assert k not in s
    assert s["parameters"] == [{"name": "W", "default": "8", "type": "int"}]
    assert s["clocking"] == {"is_sequential": True,
                             "clock": {"name": "clk", "edge": "posedge"},
                             "reset": {"name": "rst", "active": "high", "type": "synchronous"}}
    assert s["timing"] == {"busy": {"latency_cycles": 1}}
    assert "functional_summary" in CONTRACT, "the input is not mutated"


def test_port_notes_are_the_specs_own_words_or_nothing():
    s = contract_view.structured(CONTRACT, SPEC)
    by = {p["name"]: p for p in s["io"]}
    assert by["cmd"]["notes"].startswith("Bit-level command.")
    assert by["cmd"]["encoding"] == {"CMD_START": 1, "CMD_STOP": 2}
    assert by["busy"]["notes"] == "Bus busy indicator, set after START."
    assert "notes" not in by["clk"], "no spec entry, no paraphrase"
    assert by["in_seq"] == CONTRACT["io"][3], "the probe table is kept whole"


def test_the_spec_section_says_the_spec_wins_and_is_empty_without_one():
    (tag, body), = spec_section("the text")
    assert tag == "specification" and body.startswith(SPEC_AUTHORITY)
    assert spec_section("") == ()


def test_build_artifacts_projects_the_contract_and_hands_every_stage_the_spec():
    """SOURCE PIN: each stage call site in `build_artifacts` passes `spec`."""
    from specflow import integration
    src = inspect.getsource(integration.build_artifacts)
    assert "contract_view.structured(contract, spec)" in src
    for call in ("run_normalize_fanout(", "resolve_indirect(", "run_s2_fanout(",
                 "run_s3_fanout(", "run_suite_stimulus_fanout(", "run_refmodel("):
        i = src.index(call)
        assert "spec=spec" in src[i:src.index(")", src.index("max_repairs", i)) + 40], call
    from specflow import oracles_stage
    stage = inspect.getsource(oracles_stage.run_oracle_stage)
    assert stage.count("spec=spec") >= 5
