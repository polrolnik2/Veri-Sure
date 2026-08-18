"""M4: G4, tested in both directions.

A gate that never rejects rubber-stamps, and one that rejects everything stalls
the node -- so each check has a passing case and a failing case.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from specflow.refmodel.agent import Fragment, RefModelOutput, parse_response
from specflow.refmodel.base import RefModel
from specflow.refmodel.compose import choose_base, render, run_refmodel

CONTRACT_OBJ = {
    "module_name": "TopModule",
    "io": [
        {"name": "a", "dir": "input", "width": 1},
        {"name": "b", "dir": "input", "width": 1},
        {"name": "sum", "dir": "output", "width": 1},
        {"name": "cout", "dir": "output", "width": 1},
    ],
    "clocking": {"is_sequential": False},
    "timing": {"sum": {"latency_cycles": 0}, "cout": {"latency_cycles": 0}},
}
CONTRACT = json.dumps(CONTRACT_OBJ)
REQS = [
    {"uid": "REQ-0000", "rev": 1, "needs": ["testplan", "refmodel"]},
    {"uid": "REQ-0001", "rev": 1, "needs": ["testplan", "refmodel"]},
]

SUM = "def _req_0000(self, i, o):\n    o['sum'] = (i['a'] ^ i['b']) & 1\n"
COUT = "def _req_0001(self, i, o):\n    o['cout'] = (i['a'] & i['b']) & 1\n"
DISPATCH = (
    "def evaluate(self, i):\n"
    "    o = {}\n"
    "    self._req_0000(i, o)\n"
    "    self._req_0001(i, o)\n"
    "    return o\n"
)


def out(fragments: list[tuple[str, str]], helpers=DISPATCH, base="evaluate") -> RefModelOutput:
    return RefModelOutput(
        reasoning="r",
        base=base,
        helpers=helpers,
        fragments=[{"req_uid": u, "method_name": "", "code": c} for u, c in fragments],
    )


GOOD = out([("REQ-0000", SUM), ("REQ-0001", COUT)])


@dataclass
class ScriptedPort:
    replies: list[str]
    prompts: list[str] = field(default_factory=list)

    def complete(self, *, stage: str, round_: int, prompt: str) -> str:
        self.prompts.append(prompt)
        return self.replies[min(round_, len(self.replies) - 1)]


def as_reply(o: RefModelOutput) -> str:
    return json.dumps(o.model_dump())


def run(o: RefModelOutput, tmp_path, contract=CONTRACT, reqs=REQS, max_repairs=0):
    return run_refmodel(
        requirements=reqs,
        contract_json=contract,
        port=ScriptedPort([as_reply(o)]),
        workdir=tmp_path,
        max_repairs=max_repairs,
    )


# ---------------------------------------------------------------- base choice


def test_combinational_contract_chooses_evaluate():
    assert choose_base(CONTRACT_OBJ) == "evaluate"


def test_multicycle_contract_chooses_step():
    c = dict(CONTRACT_OBJ, clocking={"is_sequential": True},
             timing={"sum": {"latency_cycles": 4}})
    assert choose_base(c) == "step"


def test_handshake_contract_chooses_step():
    c = dict(
        CONTRACT_OBJ,
        clocking={"is_sequential": True},
        io=CONTRACT_OBJ["io"] + [{"name": "valid", "dir": "output", "width": 1}],
        timing={"sum": {"latency_cycles": 1}},
    )
    assert choose_base(c) == "step"


# ---------------------------------------------------------------- G4 passing


def test_correct_model_passes_and_computes(tmp_path):
    res, source = run(GOOD, tmp_path)
    assert res.ok, [i.message for i in res.issues]

    ns: dict = {}
    exec(compile(source, "ref_model.py", "exec"), ns)  # noqa: S102
    model = ns["Model"]()
    assert model.evaluate({"a": 1, "b": 1}) == {"sum": 0, "cout": 1}
    assert model.evaluate({"a": 1, "b": 0}) == {"sum": 1, "cout": 0}


# ---------------------------------------------------------------- G4 blocking


def test_missing_fragment_for_a_requirement_blocks(tmp_path):
    res, _ = run(out([("REQ-0000", SUM)]), tmp_path)
    assert not res.ok
    assert any(i.kind == "uncovered" for i in res.issues)


def test_unwritten_output_port_blocks(tmp_path):
    # Output determination: a port the model never writes is a port it does not
    # determine. Bormann's criterion in miniature.
    only_sum = "def evaluate(self, i):\n    o = {}\n    self._req_0000(i, o)\n    return o\n"
    res, _ = run(out([("REQ-0000", SUM), ("REQ-0001", COUT)], helpers=only_sum), tmp_path)
    assert not res.ok
    assert any("unwritten" in i.message and "cout" in i.message for i in res.issues)


def test_nondeterministic_model_blocks(tmp_path):
    flaky = (
        "def _req_0001(self, i, o):\n"
        "    self._n = getattr(self, '_n', 0) + 1\n"
        "    o['cout'] = self._n & 1\n"
    )
    # Hidden state across calls on ONE instance would be missed by comparing two
    # calls to the same object, which is why G4 re-instantiates.
    res, _ = run(out([("REQ-0000", SUM), ("REQ-0001", flaky)]), tmp_path)
    assert not res.ok


def test_rtl_reading_model_blocks(tmp_path):
    peeks = (
        "def _req_0001(self, i, o):\n"
        "    o['cout'] = len('rtl.sv') & 1\n"
    )
    res, _ = run(out([("REQ-0000", SUM), ("REQ-0001", peeks)]), tmp_path)
    assert not res.ok
    assert any("must not read the design" in i.message for i in res.issues)


def test_forbidden_import_blocks(tmp_path):
    res, _ = run(
        out([("REQ-0000", SUM), ("REQ-0001", COUT)], helpers="import os\n" + DISPATCH),
        tmp_path,
    )
    assert not res.ok
    assert any("must be pure" in i.message for i in res.issues)


def test_wrong_dispatch_name_blocks(tmp_path):
    res, _ = run(out([("REQ-0000", SUM), ("REQ-0001", COUT)], base="step"), tmp_path)
    assert not res.ok
    assert any("refmodel.base" in i.path for i in res.issues)


def test_raising_model_blocks(tmp_path):
    boom = "def _req_0001(self, i, o):\n    raise ValueError('nope')\n"
    res, _ = run(out([("REQ-0000", SUM), ("REQ-0001", boom)]), tmp_path)
    assert not res.ok
    assert any("raised on inputs" in i.message for i in res.issues)


def test_syntax_error_blocks_before_execution(tmp_path):
    res, _ = run(out([("REQ-0000", "def _req_0000(self, i, o:\n    pass\n")]), tmp_path)
    assert not res.ok
    assert any("does not parse" in i.message for i in res.issues)


def test_unparseable_response_blocks(tmp_path):
    res, _ = run_refmodel(
        requirements=REQS,
        contract_json=CONTRACT,
        port=ScriptedPort(["not json at all"]),
        workdir=tmp_path,
        max_repairs=0,
    )
    assert not res.ok


def test_repair_round_gets_the_defects(tmp_path):
    port = ScriptedPort([as_reply(out([("REQ-0000", SUM)])), as_reply(GOOD)])
    res, _ = run_refmodel(
        requirements=REQS, contract_json=CONTRACT, port=port,
        workdir=tmp_path, max_repairs=2,
    )
    assert res.ok and res.rounds == 2
    assert "gate_failures" in port.prompts[1]


# ---------------------------------------------------------------- base helpers


def test_mask_models_hardware_truncation():
    # The most common reference-model error is an unbounded Python int where the
    # hardware wraps, and it only shows at the boundary the spec cared about.
    assert RefModel.mask(0x1FF, 8) == 0xFF
    assert RefModel.mask(255 + 1, 8) == 0


def test_sign_extend_reads_twos_complement():
    assert RefModel.sign_extend(0xFF, 8) == -1
    assert RefModel.sign_extend(0x80, 8) == -128
    assert RefModel.sign_extend(0x7F, 8) == 127


def test_render_declares_ports_and_latency():
    src = render(GOOD, CONTRACT_OBJ)
    assert "OUTPUT_PORTS = ['sum', 'cout']" in src
    assert "class Model(RefModel)" in src
    assert "Do not edit" in src


def test_parse_response_never_raises():
    assert parse_response("garbage").reasoning.startswith("Parse Error: ")


# ------------------------------------------------- dispatch synthesis (live-run bug)


def _hadd_contract() -> dict:
    return {
        "module_name": "TopModule",
        "io": [
            {"name": "a", "dir": "input", "width": 1},
            {"name": "b", "dir": "input", "width": 1},
            {"name": "sum", "dir": "output", "width": 1},
            {"name": "cout", "dir": "output", "width": 1},
        ],
        "clocking": {"is_sequential": False},
        "timing": {"sum": {"latency_cycles": 0}, "cout": {"latency_cycles": 0}},
    }


def _fragments_without_dispatch() -> RefModelOutput:
    """The shape a live model actually returned: fragments, `helpers` empty.

    Reproduced from a gpt-5.6-luna run. The prompt asked for a dispatch while the
    response schema had nowhere to put it, so following the schema literally
    produced a class with no `evaluate` at all.
    """
    return RefModelOutput(
        base="evaluate",
        helpers="",
        fragments=[
            Fragment(req_uid="REQ-0000", method_name="_req_0000",
                     code="def _req_0000(self, i, o):\n    pass\n"),
            Fragment(req_uid="REQ-0005", method_name="_req_0005",
                     code="def _req_0005(self, i, o):\n    o['sum'] = (i['a'] ^ i['b']) & 1\n"),
            Fragment(req_uid="REQ-0006", method_name="_req_0006",
                     code="def _req_0006(self, i, o):\n    o['cout'] = (i['a'] & i['b']) & 1\n"),
        ],
    )


def test_dispatch_is_synthesised_when_the_agent_omits_it(tmp_path):
    """Without this the class inherits `RefModel.evaluate`, which raises.

    The live failure burned the full repair budget: G4 caught it only
    dynamically, as `NotImplementedError` on some input, and that issue text
    never named the missing dispatch -- so four rounds of repair could not
    converge on the actual defect.
    """
    src = render(_fragments_without_dispatch(), _hadd_contract())
    ns: dict = {}
    exec(compile(src, "ref_model.py", "exec"), ns)
    model = ns["Model"]()
    assert model.evaluate({"a": 1, "b": 1}) == {"sum": 0, "cout": 1}
    assert model.evaluate({"a": 1, "b": 0}) == {"sum": 1, "cout": 0}


def test_an_agent_supplied_dispatch_is_not_duplicated(tmp_path):
    """One model puts the dispatch in `helpers`. Emitting a second definition
    would shadow it, and which one wins would depend on emission order."""
    out = _fragments_without_dispatch()
    out.helpers = (
        "def evaluate(self, i):\n"
        "    o = {}\n"
        "    self._req_0005(i, o)\n"
        "    self._req_0006(i, o)\n"
        "    return o\n"
    )
    src = render(out, _hadd_contract())
    assert src.count("def evaluate(self, i):") == 1
    ns: dict = {}
    exec(compile(src, "ref_model.py", "exec"), ns)
    assert ns["Model"]().evaluate({"a": 1, "b": 1}) == {"sum": 0, "cout": 1}


def test_an_unwritten_output_survives_as_none_for_the_gate(tmp_path):
    """Seeding beats absence: a port nothing writes has to reach G4 as an
    undetermined output, not as a KeyError from whichever caller reads first."""
    out = _fragments_without_dispatch()
    out.fragments = [f for f in out.fragments if f.req_uid != "REQ-0006"]
    ns: dict = {}
    exec(compile(render(out, _hadd_contract()), "ref_model.py", "exec"), ns)
    assert ns["Model"]().evaluate({"a": 1, "b": 1}) == {"sum": 0, "cout": None}
