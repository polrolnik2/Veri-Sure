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
AMBIGUOUS verdicts out of 77.

**AND LOGICAL DIRECTION IS PART OF THAT ONE QUESTION, not a second one.** A
check that asserts its own antecedent is not a weak check of the requirement;
it is not a check of the requirement at all, which is exactly what this gate
asks. Splitting it out was over-cautious: the reason it was going to be a
separate reviewer is that its LABEL differs -- a check that cannot fail is
satisfied by any implementation, so vacuity sees it and over-strictness does not
-- and that is a fact about how to CALIBRATE it, not about what to ask. The
line this gate must not cross is strength and code style, and direction is
neither. Measured before it was added: 0 rejections in 82 checks, 37 of which a
known-good implementation refutes. Yes or no, and a no carries what is missing, so
the stage's repair loop has something to act on.

**What it is NOT asked.** Not whether the oracle is too strict -- that is a
question about designs, and the two instruments that could answer it have been
demoted for good reasons. Not whether any implementation is correct; no
implementation is in the prompt. Only: does this decision procedure decide the
requirement it names.

**Its yield, measured, and why a low one is the right one.** Over 70 frozen
oracles it rejects 3, and the same 3 with or without the whole specification in
the prompt. Live on a second run, 2 of the first 40. That is not the gate
failing to do anything: off-target-ness is genuinely rare, and the rejections
are precise -- a check about command lifecycle standing in for a requirement
about the prescaler, and a placeholder that lists the ports it can see and
concludes the requirement cannot be decided.

The earlier calibration rejected 56 of 70, and only 3 of those were about the
wrong subject; 26 said "it should also check X" and 15 wanted tighter timing,
both answers to the question a different gate asks. So 3 is what this gate finds
when it is asked its own question, and the recalibration made it accurate rather
than turning it off.

**What it therefore does NOT catch, by construction.** An oracle that decides
the right requirement and cannot fail is ON TARGET and this gate passes it --
it passed 21 of the 23 that `liveness` shows cannot be moved by any legal
value. Those are different axes and the second one needs execution, not a
better reader. One rejection overlaps: a placeholder that decides nothing is
both off-target and dead, and both instruments name it independently.
"""

from __future__ import annotations

import json

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
answer ONE question: is that procedure ABOUT that requirement?

Subject matter only. You are not judging any design -- none appears below. You
are not judging how thorough, how strict, or how complete the check is. And you
are NOT judging how the code is written: which combinators it uses, how it is
organised, which data structures it reaches for, whether you would have written
it differently. Only WHAT IT DECIDES.

**YOU DECIDE THE LOGIC, NOT THE IMPLEMENTATION.** A requirement here states ONE
claim -- it is meant to be atomic and almost always is -- so the question is
never "did the check cover enough of it", and never "would I have written it
this way".

THE LOGIC IS YOURS TO JUDGE. Does the check assert what the requirement says
is true, under the condition the requirement says makes it true, in the
direction the requirement states it? Direction, causality, and what is ASSERTED
against what is merely ASSUMED -- those are the question.

THE IMPLEMENTATION IS NOT YOURS. Which combinators it uses, how it is
organised, where it reads a value from, and HOW MUCH IT DEMANDS. A check whose
logic is right and which does not pin the timing, does not test every
sub-condition of its trigger, or asks for less than you would have asked for,
is ON TARGET. How much a check demands is a different question measured by a
different gate, and answering it here would push every check toward demanding
more -- while another gate is simultaneously pushing them toward demanding less.

The one claim has two halves: a CONDITION under which it applies, and what it
says HAPPENS then. Asking little of the second half is an implementation
choice and is fine. Asserting only the FIRST half is a LOGIC error -- it checks
the premise, which is true whenever the check looks, and says nothing whatever
about the design.

**THE CHECK CAN ONLY SEE DECLARED PORTS.** The trace it reads is a list of
rows carrying the interface above and nothing else -- no internal register, no
counter, no state variable, no intermediate signal, whatever the requirement's
text names. So a requirement that describes an internal MECHANISM is decided at
the port its effect reaches, and a check doing that is CORRECT, not off-target.

"It would need to observe <internal signal>" IS NEVER A VALID REJECTION. It
asks for something no check can do, and it is the specific error this project
has already made once at another stage -- reading each requirement's MECHANISM
instead of its EFFECT, which called 27 of 77 requirements unobservable when 10
of them already had working checks. If the only fault you can find is that the
check does not look at something that is not a port, the answer is YES.

Answer NO only when the procedure is about something ELSE, or is about it
BACKWARDS:

  - it reads ports the requirement is not about, and not the ones it is;
  - it decides a different behaviour than the one the requirement names --
    a different command, a different signal, a different phase of operation;
  - `clause` names one sentence and the code plainly decides another;
  - it is a placeholder: it decides nothing at all about this requirement,
    whatever it returns;
  - IT ASSERTS THE CONDITION INSTEAD OF THE EFFECT. It opens on a situation and
    then requires that same situation, or a restatement of it, to hold. It
    reduces to "when X, X" and no design can fail it;
  - IT HAS THE IMPLICATION THE WRONG WAY ROUND. The requirement says the
    condition produces the effect; the check requires the effect to imply the
    condition, and so convicts a design that produced that effect for some
    other legitimate reason;
  - IT DECIDES THE CASE THE REQUIREMENT DOES NOT COVER. It convicts on what
    happens when the condition does NOT hold. A requirement that says what
    happens under X says nothing whatever about not-X.

Those last three are one question, not three: does the check assert what the
requirement says, in the direction the requirement says it? Name the
requirement's condition and its effect in `reasoning` before you answer, and
say which of the two the check asserts.

Answer YES whenever the check's LOGIC is this requirement's logic, however
little it demands and however awkwardly it is written. "It should also check X"
is a YES. "It should check X more precisely" is a YES. "I would have written
this differently" is a YES. Only "it is checking something else" and "it is
checking it backwards" are a NO.

There is no third answer. If you find yourself wanting to say "it depends" or
"unclear", decide which is more nearly true and say why in `reasoning` -- a
reviewer that can abstain does, and an abstention decides nothing.

Reply with ONE JSON object and nothing else:

{
  "reasoning": "one or two sentences",
  "tests_the_requirement": true,
  "what_is_missing": "on false: what the check is about instead, and what it would have to decide to be about this requirement"
}
"""


def _ports(contract: dict) -> dict:
    """The interface, projected to what a reviewer of two texts can use.

    Direction, width and `notes` -- not the whole contract. `latency_cycles` and
    the pacing fields were severed from gating in Phases 3-6 precisely because
    the specification does not pin cycle counts, and putting them in front of a
    reviewer invites the timing demands the surplus question exists to catch.
    """
    out = []
    for port in contract.get("io") or []:
        row = {"name": port.get("name"), "direction": port.get("dir"),
               "width": port.get("width")}
        row = {k: v for k, v in row.items() if v is not None}
        for extra in ("notes", "idle_value"):
            if port.get(extra) is not None:
                row[extra] = port[extra]
        if row.get("name"):
            out.append(row)
    return {"ports": out}


def build_prompt(
    *,
    requirement: dict,
    oracle: RequirementOracle,
    normalized: dict | None = None,
    spec: str = "",
    contract: dict | None = None,
) -> str:
    """Texts only. There is no parameter a design could arrive through.

    The same structural enforcement `oracle_gen.build_prompt` uses, for the same
    reason and one stage later: a named signature makes adding an implementation
    a visible change to a function rather than one more key in a dict.

    `spec` is the source document the requirement was extracted FROM, and it is
    admitted here on purpose. It is strictly upstream of every artifact in this
    pipeline -- it is what S1 read -- so it cannot carry back anything the
    pipeline produced. What it adds is the surround: `requirement.spec_spans`
    already quotes the sentence, and a reviewer holding only that sentence
    cannot tell a clause whose testable content is stated two paragraphs later
    from one that has none. Ahead of the requirement rather than after it, so
    the shared prefix stays cacheable across the fan-out.

    It does NOT let this gate see behaviour. Whether a check can fail is decided
    by `liveness`, mechanically, from traces -- a fact about execution that no
    amount of prose can settle.

    `contract` is admitted on the same argument and was missing for the same
    reason nothing else here was: it was never added. `oracle_gen.build_prompt`
    takes it (`:514-522`), so until now the check's AUTHOR knew every port's
    direction and width and its REVIEWER did not -- an asymmetry with no
    defence. The contract is an interface, not a design: it is upstream of the
    reference model, the witness and every trace, so it can carry nothing back
    from any of them, and I1 is untouched.

    Three questions become answerable that were not. "Reads ports the
    requirement is not about" needs to know what the ports are. A check that
    convicts on the value of an INPUT is asserting something the DUT does not
    drive, which is visible in one line with directions and invisible without
    them. And a check reading a declared OUTPUT out of the `inputs` half of a
    row is a navigation error rather than a subject-matter one -- the reviewer
    can now say which, instead of confabulating a semantic story for a
    mechanical slip.

    Ports only, and deliberately: `notes` are included because they say which
    value drives and which releases, which is what "asserted" means for an
    open-drain line and is the distinction the author is held to, and
    `idle_value` with them because a port resting at its asserted value is the
    exact case the level/action rule turns on.

    THE FIELD IS `io` AND THE DIRECTION KEY IS `dir`. The first version of this
    read `contract["ports"]` and `port["direction"]`, which are both absent, so
    it emitted an empty block and the whole change was inert -- caught only
    because an A/B of it against itself would have measured nothing.
    `oracle_gen.shared_prefix` reads `contract.get("io")`, and this is the same
    contract.
    """
    # BOTH PER-DESIGN CONSTANTS GO IN THE SHARED BLOCK, not merely early in the
    # item. `shared_block` is the cached head and its rule is that nothing in it
    # varies between the items of one stage -- which is true of the
    # specification and of the interface, and of neither the requirement nor
    # the oracle. Putting them in the item half placed them AFTER the sentinel,
    # so they were re-sent and re-priced on every call while the docstring
    # claimed the opposite. `fanout.py`'s floor comment records this stage
    # doing it once already: SYSTEM alone is ~471 tokens, under the 1024-token
    # floor below which NOTHING caches, measured at 12% against 65-83% for
    # every other fan-out.
    shared: list[tuple[str, str]] = [("system", SYSTEM)]
    if spec.strip():
        shared.append(("specification", spec))
    if contract:
        shared.append(("interface", json.dumps(_ports(contract), indent=2)))
    parts = [json_block("requirement", requirement)]
    if normalized:
        parts.append(json_block("normalized", normalized))
    parts.append(json_block("oracle", {
        "clause": oracle.clause, "source": oracle.source}))
    return compose(shared_block(*shared), "\n\n".join(parts))


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
    spec: str = "",
    contract: dict | None = None,
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
                                normalized=normalized, spec=spec,
                                contract=contract))
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
    spec: str = "",
    contract: dict | None = None,
    round_: int = 0,
    fanout: bool = True,
) -> dict[str, Review]:
    """`{req_uid: Review}` over the oracles given. One call each."""
    norm = normalized or {}
    wanted = [o for o in oracles if o.req_uid in requirements]

    def one(oracle: RequirementOracle) -> Review:
        return review_one(
            oracle, requirements[oracle.req_uid], port=port,
            normalized=norm.get(oracle.req_uid), spec=spec,
            contract=contract, round_=round_)

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
