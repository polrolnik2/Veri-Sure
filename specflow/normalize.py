"""S1b: one requirement -> the three fields everything downstream keys on.

A requirement as S1 writes it is one sentence of prose. Three different stages
then each re-read that sentence and each infer their own answer to a different
question: the stimulus stage infers what to drive, the oracle infers what to
check, and screening infers whether the scenario ever occurred. Nothing writes
those answers down, so nothing can disagree with them, and a requirement whose
behaviour is not visible at the boundary at all is discovered three stages later
as an oracle reporting that it cannot see its own scenario.

So the sentence is normalised ONCE, into:

  activation   the trigger or precondition under which the requirement applies
  observable   the declared OUTPUT ports the behaviour is visible on
  expectation  the predicate over that observable

`observable` is the load-bearing one and it is deliberately a list of PORT
NAMES rather than prose, because that is what makes the boundary question
decidable by a script instead of by another model. A requirement with no
boundary observable is `UNOBSERVABLE`: a defect in the specification, to be
returned to spec authoring rather than worked around downstream. Measured on
`f-i2c`, three requirements are in exactly that state -- they are about
`div_cnt`, `clk_en` and `scl_sync`, none of which is a port -- and today they
block forever, because no stimulus can reach them and no oracle can decide them.

**The gate distinguishes a mistake from a finding, and that distinction is the
whole reason this can be trusted.** Naming a signal that is not a declared
output is an ERROR and buys a repair round: the model may simply have written
the wrong name. Declaring `observable: []` WITH a reason is not an error -- it
is the model committing to a claim about the specification, which is exactly
what `UNOBSERVABLE` records. Without the split, a typo and a spec defect would
be the same event.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field

from eda_agent.utils import extract_json_object, strip_markdown_code_fences

from .fanout import compose, json_block, shared_block
from .model_io import ModelPort
from .schema import Issue
from .stage import StageResult, run_fanout, run_stage

STAGE = "normalize"

#: House convention: a `reasoning` starting with this is a parse failure, not a
#: conclusion (`s1_requirements.py:145-153`, `judge.py:242`).
PARSE_ERROR = "Parse Error: "


class Activation(BaseModel):
    """When the requirement applies.

    `text` is always present. `inputs` is present only when the condition can be
    stated as input values -- "cmd is WRITE and ena is 1" can, "while the FSM is
    in idle" cannot. The distinction is not a quality judgement about the
    requirement: it decides where the condition can be CHECKED. An input-only
    activation is readable straight off a stimulus step list with no model at
    all; a state-dependent one needs something to run.
    """

    text: str = ""
    #: input port -> the value that must hold. Includes reset ports: "while
    #: reset is asserted" is a real precondition and the runtime has a reset
    #: step that reaches it, even though reset is not a *drivable* input.
    inputs: dict[str, int] = Field(default_factory=dict)

    @property
    def input_only(self) -> bool:
        return bool(self.inputs)


class NormalizedRequirement(BaseModel):
    req_uid: str = ""
    activation: Activation = Field(default_factory=Activation)
    #: Declared OUTPUT ports the behaviour is visible on. Outputs only: inputs
    #: are what a test DRIVES, never what it observes.
    observable: list[str] = Field(default_factory=list)
    #: Why there is none, set if and only if `observable` is empty. This is the
    #: model committing to a claim about the spec, and it is what separates
    #: UNOBSERVABLE from a mistyped port name.
    unobservable_reason: str = ""
    expectation: str = ""

    @property
    def unobservable(self) -> bool:
        return not self.observable


class NormalizeOutput(BaseModel):
    reasoning: str = ""
    normalized: list[NormalizedRequirement] = Field(default_factory=list)


SYSTEM = """\
You restate ONE requirement in three fields, so that later stages stop each
inferring their own version of it.

  activation   WHEN the requirement applies -- the trigger or precondition.
  observable   WHERE the behaviour is visible: declared OUTPUT port names.
  expectation  WHAT must then be true of those outputs.

You are not judging the requirement, rewriting it, or deciding whether a design
meets it. You are saying what it is about, in a form a script can check.

ACTIVATION. Give `text` always: the precondition in one clause. Additionally
give `inputs` -- a map of input port name to the value that must hold -- WHEN
AND ONLY WHEN the condition can be stated that way. "cmd is WRITE and ena is 1"
can; "while the state machine is idle" and "after arbitration has been lost"
cannot, because they are about internal state rather than about what is driven.
Leave `inputs` empty in those cases. An empty `inputs` is not a worse answer, it
is a different and equally correct one -- inventing input values that do not
actually determine the precondition is far worse, because a later stage will
drive them and conclude the scenario was staged when it was not. Reset ports may
appear in `inputs`: "while reset is asserted" is a genuine precondition.

OBSERVABLE. List the declared OUTPUT ports whose values the requirement
constrains. Outputs only -- an input is what a test drives, never what it
observes. Use the port names exactly as the contract declares them.

ASK ABOUT THE EFFECT, NOT THE MECHANISM. Most requirements describe internal
machinery on the way to describing a result -- "the filter suppresses a glitch
so no START is detected", "the FSM leaves idle and runs the command", "the
counter reloads and the tick advances the sequence". The filter, the FSM state
and the counter are internal. The RESULT is usually not: no START detected means
`busy` does not rise, running the command means `cmd_ack` eventually pulses.
Name the ports the EFFECT appears on.

A requirement is only unobservable when it has no boundary effect AT ALL -- when
you cannot complete the sentence "...and therefore, at the interface, <port>
does <thing>". "The divider counter reloads from clk_cnt" on its own has no such
ending: nothing at the interface distinguishes a reload from no reload except
through timing the specification does not pin down. That one is unobservable.
"The filter suppresses a glitch" does have an ending, and it is `busy`.

When it genuinely has none, give `observable: []` and say so in
`unobservable_reason`. That is a real and useful answer: the specification asks
for behaviour nobody can verify at the interface, which is a defect in the
specification and gets returned to whoever wrote it.

Both mistakes cost something, and they cost different things. Reaching for the
nearest output port to avoid an empty list produces a check that fails correct
designs -- a requirement about `div_cnt` reloading is not a requirement about
`scl_o`. But calling a requirement unobservable because its SENTENCE mentions an
internal signal writes off behaviour that is perfectly checkable, and stops
anyone ever verifying it. Measured on one design: 10 requirements called
unobservable this way already had working checks against real output ports.

Naming a signal that is not a declared output is a different thing entirely and
will be rejected: either the name is wrong, or there is no observable and you
should say there is none.

EXPECTATION. What must hold of those outputs when the activation occurs, in one
clause. If `observable` is empty, still state the expectation in terms of the
internal thing -- it records what could not be checked.

Reply with ONE JSON object and nothing else:

{
  "reasoning": "...",
  "normalized": [
    {
      "activation": {
        "text": "a START command is issued while the core is enabled",
        "inputs": {"cmd": 1, "ena": 1}
      },
      "observable": ["cmd_ack", "busy"],
      "unobservable_reason": "",
      "expectation": "cmd_ack pulses high for exactly one clock and busy rises"
    }
  ]
}
"""


def shared_prefix(contract_json: str, contract: dict) -> str:
    """Byte-identical across every requirement of one node.

    The OUTPUT ports are listed here rather than left to be inferred from the
    contract JSON, for the reason `suite_shared_prefix` (`testcase_agent.py:665`)
    learned the hard way: the gate validates against a list, and a model that was
    never shown the list guesses names out of prose that describes internal
    signals. On i2c that cost 12 repair rounds in 41 testpoints.
    """
    outputs = [
        {"name": p.get("name"), "width": p.get("width", 1)}
        for p in (contract.get("io") or [])
        if p.get("dir") == "output" and p.get("name")
    ]
    inputs = [
        {"name": p.get("name"), "width": p.get("width", 1)}
        for p in (contract.get("io") or [])
        if p.get("dir") == "input" and p.get("name")
    ]
    return shared_block(
        ("system", SYSTEM),
        ("contract_json", contract_json),
        ("output_ports",
         json.dumps(outputs, indent=2)
         + "\n\nThese are the ONLY names `observable` may contain. Anything else "
           "named in the requirement is internal to the design; if the "
           "requirement is about one of those, `observable` is empty."),
        ("input_ports", json.dumps(inputs, indent=2)
         + "\n\nThese are the only names `activation.inputs` may contain."),
    )


def build_prompt_one(
    requirement: dict,
    contract_json: str,
    contract: dict,
    issues: list[Issue] | None = None,
    previous: str | None = None,
) -> str:
    return compose(
        shared_prefix(contract_json, contract),
        json_block("requirement", requirement),
        issues=issues,
        previous=previous,
    )


def parse_response(text: str) -> NormalizeOutput:
    try:
        obj = extract_json_object(strip_markdown_code_fences(text))
        return NormalizeOutput.model_validate(obj)
    except Exception as exc:  # noqa: BLE001
        return NormalizeOutput(reasoning=f"{PARSE_ERROR}{exc}")


def _ports(contract: dict, direction: str) -> dict[str, int]:
    return {
        str(p.get("name")): int(p.get("width") or 1)
        for p in (contract.get("io") or [])
        if p.get("dir") == direction and p.get("name")
    }


def gate_one(
    requirement: dict, out: NormalizeOutput, contract: dict
) -> list[Issue]:
    """Pure code. The one judgement it refuses to make is the interesting one.

    An empty `observable` WITH a reason passes. That is not leniency: it is the
    only way a requirement can honestly report that the specification asks for
    something invisible at the interface, and rejecting it would force the model
    to name a port it knows is wrong -- producing an oracle that fails correct
    designs, which is the failure this pipeline exists to prevent.

    An empty `observable` WITHOUT a reason does not pass, because that is a
    model declining to commit rather than a claim about the spec.
    """
    uid = str(requirement.get("uid") or "")
    if out.reasoning.startswith(PARSE_ERROR):
        return [Issue("error", f"normalize.{uid}.response", out.reasoning)]

    if not out.normalized:
        return [Issue("error", f"normalize.{uid}", "no normalization produced")]
    if len(out.normalized) > 1:
        return [Issue("error", f"normalize.{uid}",
                      f"{len(out.normalized)} normalizations for one requirement; "
                      f"a requirement has exactly one activation, observable and "
                      f"expectation -- if it seems to have two, it is two "
                      f"requirements and that is S1's problem, not yours")]

    norm = out.normalized[0]
    issues: list[Issue] = []
    outputs = _ports(contract, "output")
    inputs = _ports(contract, "input")

    for name in norm.observable:
        if name not in outputs:
            issues.append(Issue(
                "error", f"normalize.{uid}.observable",
                f"{name!r} is not a declared output port (declared: "
                f"{sorted(outputs)}). Either the name is wrong, or the "
                f"requirement is not observable at the boundary -- in which "
                f"case give an empty list and an unobservable_reason"))

    if not norm.observable and not norm.unobservable_reason.strip():
        issues.append(Issue(
            "error", f"normalize.{uid}.observable",
            "no observable and no unobservable_reason; say which output ports "
            "the behaviour is visible on, or state that none exists and why"))

    if norm.observable and norm.unobservable_reason.strip():
        issues.append(Issue(
            "error", f"normalize.{uid}.unobservable_reason",
            f"names {sorted(norm.observable)} as observable AND gives an "
            f"unobservable_reason; these contradict"))

    for name, value in (norm.activation.inputs or {}).items():
        path = f"normalize.{uid}.activation.inputs"
        if name not in inputs:
            issues.append(Issue("error", path,
                                f"{name!r} is not a declared input port"))
            continue
        try:
            as_int = int(value)
        except Exception:  # noqa: BLE001
            issues.append(Issue("error", path, f"{name}={value!r} is not an integer"))
            continue
        if not (0 <= as_int < (1 << inputs[name])):
            issues.append(Issue("error", path,
                                f"{name}={as_int} does not fit {inputs[name]} bit(s)"))

    if not norm.activation.text.strip():
        issues.append(Issue("error", f"normalize.{uid}.activation",
                            "no activation text; every requirement applies under "
                            "some condition, even if that condition is 'always'"))
    if not norm.expectation.strip():
        issues.append(Issue("error", f"normalize.{uid}.expectation",
                            "no expectation; a requirement with nothing to check "
                            "is not a requirement"))
    return issues


def run_normalize_fanout(
    *,
    requirements: list[dict],
    contract_json: str,
    contract: dict,
    port: ModelPort,
    max_repairs: int = 2,
    fanout: bool = True,
) -> tuple[list[NormalizedRequirement], list[StageResult[NormalizeOutput]]]:
    """One small call per requirement. Requirements do not constrain each other.

    Same argument as the stimulus fan-out (`testcase_agent.py:756-787`): the
    coupling that makes the reference model a single call -- shared state,
    execution order, reset priority -- does not exist here. Each requirement's
    activation and observable are independent of every other's.
    """
    def one(req: dict) -> StageResult[NormalizeOutput]:
        return run_stage(
            stage=f"{STAGE}_{req.get('uid', 'unknown')}",
            port=port,
            build_prompt=lambda issues, previous: build_prompt_one(
                req, contract_json, contract, issues, previous),
            parse=parse_response,
            gate=lambda out: gate_one(req, out, contract),
            max_repairs=max_repairs,
        )

    results = run_fanout(requirements, one) if fanout else [one(r) for r in requirements]
    merged: list[NormalizedRequirement] = []
    for req, result in zip(requirements, results):
        for norm in result.output.normalized[:1]:
            # `req_uid` is the harness's to stamp, never the model's -- the same
            # treatment `run_judge` gives a verdict (`judge.py:796-804`). A model
            # that mislabelled one would misroute the whole requirement.
            merged.append(norm.model_copy(
                update={"req_uid": str(req.get("uid") or "")}))
    return merged, results


def unobservable(normalized: list[NormalizedRequirement]) -> dict[str, str]:
    """`req_uid -> why`, for every requirement with no boundary observable.

    These do not get an oracle, a testpoint or a repair attempt. They get
    reported, once, to whoever wrote the specification.
    """
    return {
        n.req_uid: n.unobservable_reason
        for n in normalized if n.unobservable and n.req_uid
    }


def write_artifacts(
    run_dir: Path,
    normalized: list[NormalizedRequirement],
    results: list[StageResult[NormalizeOutput]],
) -> Path:
    out_dir = Path(run_dir) / "specflow"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "normalized.json"
    path.write_text(
        json.dumps(
            {
                "normalized": [n.model_dump() for n in normalized],
                "unobservable": unobservable(normalized),
                "issues": [
                    {"severity": i.severity, "path": i.path, "message": i.message,
                     "kind": i.kind}
                    for r in results for i in r.issues
                ],
            },
            indent=2, ensure_ascii=False,
        ) + "\n",
        encoding="utf-8",
    )
    return path
