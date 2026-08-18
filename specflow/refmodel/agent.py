"""The one agent call that produces the reference model.

One call per node, not one per requirement: a node with 20 requirements makes a
single call whose response carries 20 fragment records, each tagged with the
`req_uid` it implements. Repair rounds re-ask only for the fragments that failed
the gate, so untouched fragments keep their identity -- wholesale regeneration
would churn every UID and mark every downstream cover `outdated`.

"Fragment record" is a term local to specflow, not a cocotb or Verilator
concept: one requirement's worth of generated Python plus its metadata.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from eda_agent.utils import extract_json_object, strip_markdown_code_fences


class Fragment(BaseModel):
    req_uid: str
    method_name: str = ""
    code: str = ""


class RefModelOutput(BaseModel):
    reasoning: str = ""
    #: Cross-checked against `compose.py`'s script-chosen base. A disagreement
    #: means the agent read the timing differently from the contract, which is
    #: worth surfacing rather than silently accepting either reading.
    base: str = "evaluate"
    helpers: str = ""
    fragments: list[Fragment] = Field(default_factory=list)
    #: Requirements the spec does not pin down. An honest "the spec does not
    #: say" is worth more than a confident guess: a guess becomes a wrong oracle
    #: that fails correct designs, whereas this is recorded, excluded from the
    #: accept criterion, and surfaced.
    underdetermined: list[dict] = Field(default_factory=list)


SYSTEM = """\
You write a Python reference model for a hardware module, from its
specification-derived requirements. This model is the ORACLE: the testbench
compares the design against it, so it must follow the specification and nothing
else.

You are NOT shown the RTL. That is deliberate and not an oversight -- at this
point in the pipeline no RTL exists. Model what the specification says the
design must do, not how you imagine it is built.

Emit ONE method per requirement, named `_req_NNNN` for `REQ-NNNN`. Each method
has the signature:

    def _req_0007(self, i, o):
        ...

where `i` is a dict of input port values (plain ints) and `o` is the output dict
you write into. Methods mutate `o`; they return nothing.

Do NOT write the dispatch (`evaluate` or `step`). It is generated for you: your
methods are called in the order you list them, and the output dict is seeded
before the first call. Emit the `_req_NNNN` methods and nothing else.

Rules the gate enforces mechanically:
  * every requirement gets exactly one `_req_NNNN` method
  * every output port declared in the contract is written by some method
  * the model is deterministic: no randomness, no time, no I/O, no global state
  * import nothing. `self.mask(value, width)` and `self.sign_extend(value, width)`
    are available from the base class

On widths: Python ints are unbounded and hardware ports are not. If a value can
exceed its port width, wrap it with `self.mask(...)`. Modelling an unbounded int
where the hardware truncates is the most common way this file goes wrong, and it
only shows up at the boundary the specification cared about.

If a requirement is not pinned down by the specification, still emit a method
for it implementing your best reading, and record the ambiguity in
`underdetermined` with the question you would ask.

Reply with ONE JSON object and nothing else:

{
  "reasoning": "...",
  "base": "evaluate",
  "helpers": "",
  "fragments": [
    {"req_uid": "REQ-0000", "method_name": "_req_0000",
     "code": "def _req_0000(self, i, o):\\n    o['sum'] = (i['a'] ^ i['b']) & 1\\n"}
  ],
  "underdetermined": []
}

`code` is the complete method source at module indentation level zero -- it will
be re-indented into the class body. Include the `def` line.
"""


def parse_response(text: str) -> RefModelOutput:
    try:
        obj = extract_json_object(strip_markdown_code_fences(text))
        return RefModelOutput.model_validate(obj)
    except Exception as exc:  # noqa: BLE001
        return RefModelOutput(reasoning=f"Parse Error: {exc}")
