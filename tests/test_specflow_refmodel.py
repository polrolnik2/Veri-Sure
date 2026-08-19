"""M4: G4, tested in both directions.

A gate that never rejects rubber-stamps, and one that rejects everything stalls
the node -- so each check has a passing case and a failing case.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from specflow.refmodel.agent import RefModelOutput, parse_response
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

#: A model shaped the way the design is, not the way the document is: one
#: dispatch the generator wrote itself, with a helper it chose to factor out.
GOOD_SOURCE = (
    "def _half_add(self, a, b):\n"
    "    return (a ^ b) & 1, (a & b) & 1\n"
    "\n"
    "def evaluate(self, i):\n"
    "    o = {p: None for p in self.OUTPUT_PORTS}\n"
    "    o['sum'], o['cout'] = self._half_add(i['a'], i['b'])\n"
    "    return o\n"
)
GOOD_COVERS = {"REQ-0000": ["_half_add", "evaluate"], "REQ-0001": ["_half_add"]}


def out(source=GOOD_SOURCE, covers=None, base="evaluate") -> RefModelOutput:
    return RefModelOutput(
        reasoning="r",
        base=base,
        source=source,
        covers=GOOD_COVERS if covers is None else covers,
    )


GOOD = out()


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


def test_a_requirement_absent_from_the_coverage_map_blocks(tmp_path):
    """This replaces "every requirement has a `_req_NNNN` method".

    That check bought traceability by forcing the model's *shape*, and the shape
    was the problem. The map carries the link instead, so the model can be
    shaped by the design -- but the map must be complete or the link is a
    fiction.
    """
    res, _ = run(out(covers={"REQ-0000": ["evaluate"]}), tmp_path)
    assert not res.ok
    assert any(i.kind == "uncovered" and "REQ-0001" in i.message for i in res.issues)


def test_a_coverage_map_naming_a_method_that_does_not_exist_blocks(tmp_path):
    res, _ = run(out(covers={"REQ-0000": ["evaluate"], "REQ-0001": ["_nope"]}), tmp_path)
    assert not res.ok
    assert any("no such method exists" in i.message for i in res.issues)


def test_a_map_pointing_everything_at_one_method_is_allowed_by_the_script(tmp_path):
    """Pinned deliberately, so the division of labour is explicit.

    Claiming one method implements every requirement is exactly the degenerate
    answer the judge exists to catch -- and a script cannot tell it from a
    genuinely cohesive dispatch without reading meaning. So the script accepts
    it and the judge is what convicts.
    """
    res, _ = run(out(covers={"REQ-0000": ["evaluate"], "REQ-0001": ["evaluate"]}), tmp_path)
    assert res.ok, [i.message for i in res.issues]


def test_unwritten_output_port_blocks(tmp_path):
    # Output determination: a port the model never writes is a port it does not
    # determine. Bormann's criterion in miniature, and a property of the
    # assembled model rather than of any one method -- which is why it survives
    # the move to a design-shaped model unchanged.
    only_sum = (
        "def evaluate(self, i):\n"
        "    o = {p: None for p in self.OUTPUT_PORTS}\n"
        "    o['sum'] = (i['a'] ^ i['b']) & 1\n"
        "    return o\n"
    )
    res, _ = run(out(only_sum, covers={"REQ-0000": ["evaluate"], "REQ-0001": ["evaluate"]}),
                 tmp_path)
    assert not res.ok
    assert any("unwritten" in i.message and "cout" in i.message for i in res.issues)


def test_nondeterministic_model_blocks(tmp_path):
    flaky = (
        "def evaluate(self, i):\n"
        "    o = {p: None for p in self.OUTPUT_PORTS}\n"
        "    o['sum'] = (i['a'] ^ i['b']) & 1\n"
        "    self._n = getattr(self, '_n', 0) + 1\n"
        "    o['cout'] = self._n & 1\n"
        "    return o\n"
    )
    # Hidden state across calls on ONE instance would be missed by comparing two
    # calls to the same object, which is why G4 re-instantiates.
    res, _ = run(out(flaky, covers={"REQ-0000": ["evaluate"], "REQ-0001": ["evaluate"]}),
                 tmp_path)
    assert not res.ok


def test_rtl_reading_model_blocks(tmp_path):
    peeks = GOOD_SOURCE.replace("return o", "o['cout'] = len('rtl.sv') & 1\n    return o")
    res, _ = run(out(peeks), tmp_path)
    assert not res.ok
    assert any("must not read the design" in i.message for i in res.issues)


def test_forbidden_import_blocks(tmp_path):
    res, _ = run(out("import os\n" + GOOD_SOURCE), tmp_path)
    assert not res.ok
    assert any("must be pure" in i.message for i in res.issues)


def test_wrong_dispatch_name_blocks(tmp_path):
    res, _ = run(out(base="step"), tmp_path)
    assert not res.ok
    assert any("refmodel.base" in i.path for i in res.issues)


def test_raising_model_blocks(tmp_path):
    # Writes an output statically, then raises at run time. A fragment that only
    # raised would now be caught by the writes-no-output static check instead,
    # which is correct but would leave this test exercising the wrong gate.
    boom = GOOD_SOURCE.replace("return o", "o['cout'] = 1 // 0\n    return o")
    res, _ = run(out(boom), tmp_path)
    assert not res.ok
    assert any("raised on inputs" in i.message for i in res.issues)


def test_syntax_error_blocks_before_execution(tmp_path):
    res, _ = run(out("def evaluate(self, i:\n    pass\n"), tmp_path)
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
    port = ScriptedPort([as_reply(out(covers={"REQ-0000": ["evaluate"]})), as_reply(GOOD)])
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


# The dispatch synthesiser and its tests are gone. It called one method per
# requirement in declaration order, which was coherent only while the model was
# required to be one-method-per-requirement -- and that requirement is what left
# the generator unable to express execution order, where reset priority lives.
# The generator writes `evaluate`/`step` itself now, so there is nothing to
# synthesise and nothing to duplicate.


def test_an_honest_underdetermined_question_does_not_discard_the_model():
    """The schema penalised exactly the behaviour the prompt asks for.

    The prompt says to record "the question you would ask" when the spec does
    not pin a behaviour down, because an honest "the spec does not say" is worth
    more than a guess -- a guess becomes a wrong oracle that fails correct
    designs. A model answering a question-shaped field with a question, i.e. a
    string, was then rejected by a dict-only type, and the *whole response* went
    with it: fragments included.

    Measured live on `i2c_master_bit_ctrl`: 27 of 60 reference-model calls were
    re-asked for this and nothing else, which read as the model failing at the
    modelling task when it was doing the right thing.
    """
    from specflow.refmodel.agent import parse_response

    raw = json.dumps({
        "base": "evaluate",
        "source": "def evaluate(self, i):\n    return {'sum': 1}\n",
        "covers": {"REQ-0036": ["evaluate"]},
        "underdetermined": ["Which clock edge samples SDA during the READ phase?"],
    })
    out = parse_response(raw)
    assert not out.reasoning.startswith("Parse Error"), out.reasoning
    assert out.source, "the model source was discarded along with the question"
    assert out.underdetermined[0]["question"].startswith("Which clock edge")


def test_the_dict_shape_still_works():
    """Both shapes carry the same information; neither may be rejected."""
    from specflow.refmodel.agent import parse_response

    out = parse_response(json.dumps({
        "base": "evaluate", "source": "", "covers": {},
        "underdetermined": [{"req_uid": "REQ-0001", "question": "What on overflow?"}],
    }))
    assert not out.reasoning.startswith("Parse Error")
    assert out.underdetermined[0]["req_uid"] == "REQ-0001"
