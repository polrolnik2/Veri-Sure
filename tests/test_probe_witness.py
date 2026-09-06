"""The witness exposes probes as ATTRIBUTES, and nothing keyed on outputs moves.

A probe reaches `decide()` by one of two routes. Putting probes in
`OUTPUT_PORTS` is free plumbing and drags in, at once, `validate`'s
every-output-written-every-call rule, the bidirectional OUTPUT_PORTS check,
`_ports_agree`, `compose.output_ports`, `variants._widths` and
`liveness._widths`. That is the shape an earlier experiment refuted, under a new
name.

A separate `PROBE_PORTS` list leaves every one of those untouched. These tests
pin that separation, because it is invisible in the diff and expensive to lose.
"""
from __future__ import annotations

from specflow.refmodel.agent import RefModelOutput
from specflow.refmodel.compose import output_ports, probe_ports, render
from specflow.refmodel.validate import validate_source

CONTRACT = {
    "source_of_truth": "spec",
    "module_name": "dcfsm",
    "io": [
        {"name": "clk", "dir": "input", "width": 1},
        {"name": "go", "dir": "input", "width": 1},
        {"name": "busy", "dir": "output", "width": 1},
        {"name": "in_idle", "dir": "probe", "width": 1,
         "notes": "the FSM is in the state the specification calls IDLE"},
        {"name": "in_run", "dir": "probe", "width": 1,
         "notes": "the FSM is in the state the specification calls RUN"},
    ],
    "clocking": {"is_sequential": True,
                 "clock": {"name": "clk", "edge": "posedge"}},
}

CONTROL = {**CONTRACT,
           "io": [p for p in CONTRACT["io"] if p.get("dir") != "probe"]}

#: A witness that maintains its probes the way the prompt asks: as boolean
#: attributes, NOT as entries in the returned output dict.
BODY = """
def __init__(self):
    self.state = 'IDLE'
    self.in_idle = True
    self.in_run = False

def reset(self):
    self.state = 'IDLE'
    self.in_idle = True
    self.in_run = False

def step(self, inputs):
    if inputs.get('go'):
        self.state = 'RUN'
    else:
        self.state = 'IDLE'
    self.in_idle = self.state == 'IDLE'
    self.in_run = self.state == 'RUN'
    return {'busy': 1 if self.state == 'RUN' else 0}
"""


def _model(contract: dict, body: str = BODY):
    src = render(RefModelOutput(source=body, base="step"), contract)
    ns: dict = {}
    exec(compile(src, "<witness>", "exec"), ns)  # noqa: S102
    return src, ns["Model"]


def test_the_witness_maintains_its_probes_as_readable_attributes() -> None:
    """The obligation is PRESENCE, and it is what `replay()` will sample."""
    _, cls = _model(CONTRACT)
    m = cls()
    assert m.step({"go": 1}) == {"busy": 1}
    assert [getattr(m, n) for n in cls.PROBE_PORTS] == [False, True]
    assert m.step({"go": 0}) == {"busy": 0}
    assert [getattr(m, n) for n in cls.PROBE_PORTS] == [True, False]


def test_probes_do_not_leak_into_output_ports() -> None:
    """The split at `compose.output_ports`, pinned.

    If this ever fails, every OUTPUT_PORTS-keyed gate is now seeing probes and
    the design has silently become the refuted one.
    """
    _, cls = _model(CONTRACT)
    assert cls.OUTPUT_PORTS == ["busy"] == output_ports(CONTRACT)
    assert cls.PROBE_PORTS == ["in_idle", "in_run"] == probe_ports(CONTRACT)
    assert set(cls.OUTPUT_PORTS).isdisjoint(cls.PROBE_PORTS)


def test_a_probe_that_is_false_most_of_the_time_is_accepted(tmp_path) -> None:
    """NOT the every-output-written rule. A state predicate is usually False.

    `in_run` is False on the vast majority of edges. Under check 3a that would
    be a port the model fails to determine, and generation would be rejected
    outright on every design whose states are not all simultaneously true.
    """
    src, _ = _model(CONTRACT)
    issues = validate_source(source=src, requirements=[], contract=CONTRACT,
                             expected_base="step", workdir=tmp_path)
    assert [i.message for i in issues if i.severity == "error"] == []


def test_a_declared_probe_the_model_never_defines_fails_loudly(tmp_path) -> None:
    """The silent failure this check exists to make loud.

    `replay()` samples a probe with `getattr(model, name, None)`, so an undefined
    probe is sampled as `None`, lands in the row as `None`, and every check
    reading it quietly never fires. That is exactly the defect that made E0's
    first scoring read +5 with zero probe-using passes.
    """
    body = BODY.replace("self.in_run = self.state == 'RUN'\n    return", "return")
    body = body.replace("    self.in_run = False\n", "")
    src, _ = _model(CONTRACT, body)
    issues = validate_source(source=src, requirements=[], contract=CONTRACT,
                             expected_base="step", workdir=tmp_path)
    named = [i for i in issues if i.severity == "error" and "in_run" in i.message]
    assert named, [i.message for i in issues]
    assert "silently never fires" in named[0].message


def test_a_contract_with_no_probes_validates_exactly_as_before(tmp_path) -> None:
    """Zero behaviour change where no probe is declared.

    The control for the whole step: a run that declares no probe must reach the
    identical set of issues, so nothing here can be paying a cost on the designs
    that do not use the feature.
    """
    body = BODY
    for line in ("self.in_idle = True", "self.in_run = False",
                 "self.in_idle = self.state == 'IDLE'",
                 "self.in_run = self.state == 'RUN'"):
        body = body.replace(f"    {line}\n", "")
    src, cls = _model(CONTROL, body)
    assert cls.PROBE_PORTS == []
    assert "PROBE_PORTS = []" in src
    issues = validate_source(source=src, requirements=[], contract=CONTROL,
                             expected_base="step", workdir=tmp_path)
    assert [i.message for i in issues if i.severity == "error"] == []


def test_the_prompt_names_every_probe_and_its_meaning() -> None:
    """The witness author cannot maintain a probe it was never told about.

    And the failure is silent: an undeclared attribute is sampled as `None`, so
    every check reading that probe never fires and the run looks merely
    under-covered rather than broken.
    """
    from specflow.refmodel.compose import probe_block

    block = probe_block(CONTRACT, "step")
    for name in ("in_idle", "in_run"):
        assert f"`{name}`" in block, f"{name} missing from the witness prompt"
    assert "the specification calls IDLE" in block
    assert "BOOLEAN ATTRIBUTE" in block
    # The obligation must be stated as an attribute and explicitly NOT as an
    # output, or the model returns its probes and they enter the output dict.
    assert "Do NOT return them from `step`" in block

    assert probe_block(CONTROL, "step") == ""
