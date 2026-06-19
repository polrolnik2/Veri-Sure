"""Contract-level regression: module parameters are a first-class contract field.

Previously the contract schema modelled only ports (`io`), so a spec parameter
like `MODE`/`WIDTH` was demoted to prose and dropped by the Coder. The contract
now carries a structured `parameters` list that flows downstream via
`model_dump_json`.
"""

from __future__ import annotations

import json

from eda_agent.architect_agent import ContractFormat, EXAMPLE_OUTPUT
from eda_agent.contract_linter import lint_contract_json


def test_contract_has_parameters_field_and_example_populates_it():
    c = ContractFormat.model_validate(EXAMPLE_OUTPUT)
    assert isinstance(c.parameters, list) and c.parameters
    assert c.parameters[0]["name"] == "WIDTH"
    # parameters survive serialization into the string handed to Coder/TB.
    dumped = json.loads(c.model_dump_json(exclude_none=True))
    assert any(p.get("name") == "WIDTH" for p in dumped["parameters"])


def test_contract_without_parameters_is_backward_compatible():
    old = {k: v for k, v in EXAMPLE_OUTPUT.items() if k != "parameters"}
    c = ContractFormat.model_validate(old)
    assert c.parameters == []


def test_linter_accepts_wellformed_parameters():
    issues, _ = lint_contract_json(json.dumps(EXAMPLE_OUTPUT))
    assert not [i for i in issues if i.path.startswith("parameters")]


def test_linter_flags_parameter_without_name():
    bad = dict(EXAMPLE_OUTPUT)
    bad["parameters"] = [{"default": "8"}]
    issues, _ = lint_contract_json(json.dumps(bad))
    assert [i for i in issues if i.path.startswith("parameters") and i.severity == "error"]
