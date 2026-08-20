"""`latency_cycles` informs the RTL agent. It gates nothing.

The field was load-bearing in three places at once: it gated a reference-model
check (G4e), it set the testbench's stimulus hold length, and it picked the
reference model's dispatch. And it was a guess -- on `i2c_master_bit_ctrl` the
architect returned `cmd_ack: 3` in one run of the same specification and `1` in
the next, against a golden design that takes five `clk_en` phases. The phase
count appears nowhere in the 15,715 characters of that specification, because it
is an arbitrary-but-fixed choice of that particular core.

So the architect was being asked to invent a number in exactly the case where
nothing could check it -- the prompt said, in as many words, "choose 0 or 1" --
and three subsystems then treated the invention as a requirement. These cases
pin the field's new shape: optional, contained at the boundary, defined once.
"""

from __future__ import annotations

import json

from eda_agent.architect_agent import (
    CONTRACT_PROMPT,
    LATENCY_DEFINITION,
    ContractFormat,
)
from eda_agent.contract_linter import lint_contract_json

_BASE = dict(
    source_of_truth="spec",
    module_name="m",
    io=[{"name": "clk", "dir": "input", "width": 1},
        {"name": "a", "dir": "input", "width": 8},
        {"name": "out", "dir": "output", "width": 8}],
    clocking={"is_sequential": True, "clock": {"name": "clk", "edge": "posedge"}},
    functional_summary=[],
    corner_cases=[],
    test_plan=[],
    guidance={},
)


def _contract(timing) -> ContractFormat:
    return ContractFormat.model_validate(dict(_BASE, timing=timing))


# ------------------------------------------------------- an absent count


def test_an_omitted_latency_survives_as_omitted():
    """"The spec does not determine this" is now an answer, not a gap."""
    c = _contract({"out": {"notes": "the spec states no cycle count"}})
    assert c.timing["out"].latency_cycles is None
    dumped = json.loads(c.model_dump_json(exclude_none=True))
    assert "latency_cycles" not in dumped["timing"]["out"]


def test_the_linter_no_longer_demands_a_count_for_every_output():
    """The warning was pressure to invent one.

    A warning is fed back to the architect as something to fix, so "Missing
    latency_cycles" on every undeclared output pushed it to produce a figure
    whether or not the specification supported one -- which is where the 3-then-1
    instability came from.
    """
    text = _contract({"out": {"notes": "spec silent"}}).model_dump_json(exclude_none=True)
    issues, _ = lint_contract_json(text)
    assert not [i for i in issues if "latency_cycles" in i.path], [
        (i.severity, i.path, i.message) for i in issues
    ]


def test_an_output_with_no_timing_entry_at_all_is_not_flagged():
    issues, _ = lint_contract_json(_contract({}).model_dump_json(exclude_none=True))
    assert not [i for i in issues if i.path.startswith("timing")]


# ------------------------------------------------------- containment


def test_a_nonsense_count_costs_its_own_field_and_nothing_else():
    """Typing the field must not make a bad value cost MORE than it did.

    `ContractFormat.model_validate` raising anywhere means `parse_output`
    returns a stub with no io, no clocking and `timing={}` -- so a strictly
    typed field would let one nonsense latency take the whole interface down.
    """
    c = _contract({"out": {"latency_cycles": "fast", "notes": "kept"}})
    assert c.timing["out"].latency_cycles is None
    assert c.timing["out"].notes == "kept"
    assert [p["name"] for p in c.io] == ["clk", "a", "out"]


def test_a_negative_count_is_absent_rather_than_fatal():
    assert _contract({"out": {"latency_cycles": -2}}).timing["out"].latency_cycles is None


def test_a_nonsense_entry_costs_its_entry_and_nothing_else():
    c = _contract({"out": "fast", "other": {"latency_cycles": 2}})
    assert "out" not in c.timing
    assert c.timing["other"].latency_cycles == 2


def test_extra_keys_the_architect_writes_are_preserved():
    """`notes` and design-specific keys are read downstream; typing must not eat them."""
    c = _contract({"out": {"latency_cycles": 3, "minimum_clk_en_ticks": 3, "notes": "n"}})
    assert c.model_dump()["timing"]["out"]["minimum_clk_en_ticks"] == 3


def test_the_linter_still_rejects_an_invalid_count_on_a_contract_from_disk():
    """The boundary containment must not become a way to smuggle garbage past the lint.

    A contract read from disk never passes through `ContractFormat`, and the
    benchmark harness reads `contract.json` directly.
    """
    text = json.dumps(dict(_BASE, timing={"out": {"latency_cycles": "fast"}}))
    issues, _ = lint_contract_json(text)
    assert [i for i in issues if i.severity == "error" and "latency_cycles" in i.path]


# ------------------------------------------------------- one definition


def test_the_definition_is_quoted_into_the_prompt_not_paraphrased():
    """Four wordings across four files are four fields.

    `architect_agent`, `contract_linter`, `rtl_generator` and `refmodel/agent`
    each described `latency_cycles` in their own words, and they did not agree
    about whether the count was in clock edges or in enable ticks -- which on a
    prescaled design is the difference between 5 and 26.
    """
    rendered = CONTRACT_PROMPT.format(
        input_spec="S", golden_tb_block="", latency_definition=LATENCY_DEFINITION)
    assert LATENCY_DEFINITION in rendered
    assert "edges of the DECLARED CLOCK" in rendered
    assert "choose 0 or 1" not in rendered


def test_g4e_is_gone():
    """It was inert below `>= 2`, anchored to a number that was wrong, trivially
    satisfied by targeting the threshold, and it never fired in the one live run
    that could have used it."""
    from specflow.refmodel import validate

    assert not hasattr(validate, "_min_latency_checks")
