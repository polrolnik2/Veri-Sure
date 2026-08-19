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

from pydantic import BaseModel, Field, field_validator

from eda_agent.utils import extract_json_object, strip_markdown_code_fences

from ..schema import Underdetermined


class RefModelOutput(BaseModel):
    reasoning: str = ""
    #: Cross-checked against `compose.py`'s script-chosen base. A disagreement
    #: means the agent read the timing differently from the contract, which is
    #: worth surfacing rather than silently accepting either reading.
    base: str = "evaluate"
    #: The whole class body, written by the generator: helpers, state, and the
    #: dispatch. Previously the harness synthesised the dispatch by calling one
    #: method per requirement in list order, which meant the generator could not
    #: express execution order at all -- and execution order is where reset
    #: priority lives.
    source: str = ""
    #: The generator's own claim about where each requirement is implemented:
    #: `{"REQ-0031": ["_fsm", "_ack_pulse"]}`. Many-to-many on purpose. This
    #: carries traceability so the *structure* no longer has to, which is what
    #: frees the model to be shaped by the design instead of by the
    #: specification's sentence order.
    covers: dict[str, list[str]] = Field(default_factory=dict)
    #: Requirements the spec does not pin down. An honest "the spec does not
    #: say" is worth more than a confident guess: a guess becomes a wrong oracle
    #: that fails correct designs, whereas this is recorded, excluded from the
    #: accept criterion, and surfaced.
    underdetermined: list[dict] = Field(default_factory=list)

    @field_validator("underdetermined", mode="before")
    @classmethod
    def _accept_bare_questions(cls, v):
        """A model answering "the question you would ask" with a question -- a
        string -- is following the prompt. See `schema.Underdetermined.coerce`."""
        if isinstance(v, list):
            return [Underdetermined.coerce(x) for x in v]
        return v


SYSTEM = """\
You write a Python reference model for a hardware module, from its
specification-derived requirements. This model is the ORACLE: the testbench
compares the design against it, so it must follow the specification and nothing
else.

You are NOT shown the RTL. That is deliberate and not an oversight -- at this
point in the pipeline no RTL exists. Model what the specification says the
design must do, not how you imagine it is built.

Write ONE coherent model, structured the way the DESIGN is structured -- a
synchroniser, a filter, a divider, an FSM, whatever this design actually is.
Do NOT structure it around the requirement list. A requirement is a sentence
from a document; it is not a unit of hardware, and shaping the model around
sentences leaves nowhere to put execution order, reset priority, or the state
that several requirements share.

You write the whole class body, including the dispatch:

    def step(self, i):       # or evaluate(self, i) -- see `base` below
        o = {p: None for p in self.OUTPUT_PORTS}
        ...
        return o

`i` is a dict of input port values (plain ints); return the output dict. You own
the order things happen in, which is the point.

Then declare `covers`: for each requirement uid, the method names that implement
it. A requirement may map to several methods and a method may serve several
requirements. This is how the requirement -> code link is checked, so it must be
accurate: a judge reads your model against one requirement at a time and asks
whether the methods you named actually satisfy it.

Rules the gate enforces mechanically:
  * every requirement appears in `covers`, and every method named there exists
  * every output port declared in the contract is written on every call
  * the model is deterministic: no randomness, no time, no I/O, no global state
  * import nothing. `self.mask(value, width)` and `self.sign_extend(value, width)`
    are available from the base class

On widths: Python ints are unbounded and hardware ports are not. If a value can
exceed its port width, wrap it with `self.mask(...)`. Modelling an unbounded int
where the hardware truncates is the most common way this file goes wrong, and it
only shows up at the boundary the specification cared about.

If a requirement is not pinned down by the SPECIFICATION, still implement your
best reading, and record the ambiguity in `underdetermined` with the question you
would ask. That field is about the spec being silent -- it is not the place for
"my code is unclear".

Reply with ONE JSON object and nothing else:

{
  "reasoning": "...",
  "base": "evaluate",
  "source": "def evaluate(self, i):\\n    o = {p: None for p in self.OUTPUT_PORTS}\\n    o['sum'] = (i['a'] ^ i['b']) & 1\\n    o['cout'] = (i['a'] & i['b']) & 1\\n    return o\\n",
  "covers": {"REQ-0000": ["evaluate"], "REQ-0001": ["evaluate"]},
  "underdetermined": []
}

`source` is the complete class body at module indentation level zero -- every
method including the dispatch, which will be re-indented into the class. Do not
emit the `class` line; the harness writes that, with `OUTPUT_PORTS` and
`LATENCY_CYCLES` set from the contract.
"""


def parse_response(text: str) -> RefModelOutput:
    try:
        obj = extract_json_object(strip_markdown_code_fences(text))
        return RefModelOutput.model_validate(obj)
    except Exception as exc:  # noqa: BLE001
        return RefModelOutput(reasoning=f"Parse Error: {exc}")
