"""Does this oracle test the requirement it claims to test?

**The gap this closes.** Every other check asks whether an oracle is a good
CHECK -- well-formed, satisfiable, able to fail something. None of them asks
whether it is a check of THIS requirement. An oracle can name a declared port,
run cleanly, catch a variant, and be about something the requirement never
mentions. `RequirementOracle.clause` exists to anchor it -- the oracle quotes the
sentence it decides -- but only its PRESENCE was ever checked, never its
correspondence to what the code actually does.

**Why this one is allowed to block when the designs are not.** Authority here
follows independence, not strength. The witness and the control are the stronger
instruments and both are disqualified: the witness is a second reading by the
same author, so an oracle failing it means two same-author readings disagree;
the control is a proxy for the held-out grade, so gating on it tunes the model
toward its own scorer transitively. This reviewer sees neither. It reads the
requirement and the oracle source -- two texts, no design, no trace, no
behaviour -- and answers one question about the relationship between them. It
cannot be contaminated by an implementation because it is never shown one.

**One question, deliberately.** It is not offered "ambiguous". A reviewer given
that option takes it, which is how the retired judge produced a run of 50
AMBIGUOUS verdicts out of 77. Yes or no, and a no carries what is missing, so
the stage's repair loop has something to act on.

**What it is NOT asked.** Not whether the oracle is too strict -- that is a
question about designs, and the two instruments that could answer it have been
demoted for good reasons. Not whether any implementation is correct; no
implementation is in the prompt. Only: does this decision procedure decide the
requirement it names.
"""

from __future__ import annotations


from eda_agent.utils import extract_json_object, strip_markdown_code_fences
from pydantic import BaseModel

from ..fanout import compose, json_block, shared_block
from ..model_io import ModelPort
from ..stage import run_fanout
from .oracles import RequirementOracle

STAGE = "correspond"

PARSE_ERROR = "Parse Error: "


class Review(BaseModel):
    reasoning: str = ""
    #: Does the oracle decide the requirement it names?
    tests_the_requirement: bool = True
    #: On a no: what the check would have to do instead. The repair prompt.
    what_is_missing: str = ""


SYSTEM = """\
You are given a requirement and a decision procedure written to decide it. You
answer ONE question: does that procedure actually decide THAT requirement?

You are not judging any design. No implementation appears below and none is
relevant. You are not judging whether the check is too strict, or whether the
requirement is a good requirement. Only whether the check and the requirement
are about the same thing.

Answer NO when, for example:

  - the check reads ports the requirement is not about, or ignores the port the
    requirement's behaviour is visible on;
  - the check tests a condition the requirement does not state, or omits the
    condition it does state;
  - the check would be satisfied by a design that plainly violates the
    requirement, or failed by one that plainly satisfies it, on the requirement's
    own terms rather than any particular design's;
  - the `clause` names one sentence and the code decides a different one.

Answer YES when the procedure decides the requirement, even if you would have
written it differently. Style, structure and strictness are not your question.

There is no third answer. If you find yourself wanting to say "it depends" or
"unclear", decide which is more nearly true and say why in `reasoning` -- a
reviewer that can abstain does, and an abstention decides nothing.

Reply with ONE JSON object and nothing else:

{
  "reasoning": "one or two sentences",
  "tests_the_requirement": true,
  "what_is_missing": "on false: what the check must decide instead, concretely"
}
"""


def build_prompt(
    *,
    requirement: dict,
    oracle: RequirementOracle,
    normalized: dict | None = None,
) -> str:
    """Two texts. There is no parameter a design could arrive through.

    The same structural enforcement `oracle_gen.build_prompt` uses, for the same
    reason and one stage later: a named signature makes adding an implementation
    a visible change to a function rather than one more key in a dict.
    """
    parts = [json_block("requirement", requirement)]
    if normalized:
        parts.append(json_block("normalized", normalized))
    parts.append(json_block("oracle", {
        "clause": oracle.clause, "source": oracle.source}))
    return compose(shared_block(("system", SYSTEM)), "\n\n".join(parts))


def parse_response(text: str) -> Review:
    try:
        obj = extract_json_object(strip_markdown_code_fences(text))
        return Review.model_validate(obj)
    except Exception as exc:  # noqa: BLE001
        return Review(reasoning=f"{PARSE_ERROR}{exc}")


def review_one(
    oracle: RequirementOracle,
    requirement: dict,
    *,
    port: ModelPort,
    normalized: dict | None = None,
    round_: int = 0,
) -> Review:
    """One call. Never raises: a reviewer that cannot answer does not reject.

    An unreachable model or an unparseable reply is a fact about this call, not
    about the oracle, and convicting on it would make a blocking gate out of a
    network error.
    """
    try:
        reply = port.complete(
            stage=f"{STAGE}_{oracle.req_uid or 'unknown'}", round_=round_,
            prompt=build_prompt(requirement=requirement, oracle=oracle,
                                normalized=normalized))
    except Exception as exc:  # noqa: BLE001
        return Review(reasoning=f"{PARSE_ERROR}{exc!r}")
    out = parse_response(reply)
    if out.reasoning.startswith(PARSE_ERROR):
        return Review(reasoning=out.reasoning)
    return out


def review(
    oracles: list[RequirementOracle],
    requirements: dict[str, dict],
    *,
    port: ModelPort,
    normalized: dict[str, dict] | None = None,
    round_: int = 0,
    fanout: bool = True,
) -> dict[str, Review]:
    """`{req_uid: Review}` over the oracles given. One call each."""
    norm = normalized or {}
    wanted = [o for o in oracles if o.req_uid in requirements]

    def one(oracle: RequirementOracle) -> Review:
        return review_one(
            oracle, requirements[oracle.req_uid], port=port,
            normalized=norm.get(oracle.req_uid), round_=round_)

    done = run_fanout(wanted, one) if fanout else [one(o) for o in wanted]
    return {o.req_uid: r for o, r in zip(wanted, done)}


def rejects(out: Review) -> str:
    """Why this oracle is not a check of its requirement, or empty.

    A reply that could not be parsed is not a rejection: see `review_one`.
    """
    if out.reasoning.startswith(PARSE_ERROR) or out.tests_the_requirement:
        return ""
    detail = out.what_is_missing or out.reasoning or "(no detail)"
    return f"off-target: {detail}"
