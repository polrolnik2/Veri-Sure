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
    #: THE PRIOR QUESTION. Does the requirement's own sentence condemn any
    #: design at all? A definition ("cmd is the bit-level command") and a scope
    #: statement ("the module begins with a reset sequence") name something
    #: without saying what must happen, and no check of them can be a fair test
    #: because there is nothing to be unfair to.
    #:
    #: Defaults TRUE, and that direction is deliberate: a reply from a model
    #: that never saw this field must not silently become a rejection, and the
    #: expensive error here is rejecting a real requirement, not missing a
    #: hollow one.
    states_an_obligation: bool = True
    #: Does the oracle decide the requirement it names?
    tests_the_requirement: bool = True
    #: On a no: what the check would have to do instead. The repair prompt.
    what_is_missing: str = ""


SYSTEM = """\
You are given a requirement written in English and a decision procedure written
in Python to decide it. You answer ONE question: DOES THE CODE DECIDE WHAT THE
TEXT SAYS?

Read this whole briefing before you answer. The task is a comparison between a
logical form and a piece of code, and both halves have a fixed shape.

================================================================
1. WHAT A REQUIREMENT IS
================================================================

Every requirement is one claim with three parts:

    TRIGGER   the situation in which the claim applies
    EFFECT    what the design must do in that situation
    PORT      where the effect is visible at the boundary

    "The busy output is set when a filtered START condition is detected."
      TRIGGER  a filtered START condition is detected
      EFFECT   busy is set
      PORT     busy

A requirement is a claim about SOME rows -- the ones where the trigger holds --
and says NOTHING about any other row. That is the single most important fact
here, and most defects come from forgetting it. "busy is set on START" does not
say what busy does when there is no START. It does not say busy stays set. It
does not say anything at all about cmd_ack.

Some requirements have no trigger: "scl_o is permanently driven to 0". The
trigger is then every row, and the claim really does cover all of them.

================================================================
2. WHAT A CHECK IS, AS CODE
================================================================

Every check has the same skeleton, however it is written:

    def decide(trace):
        rows = [r for r in trace if TRIGGER(r)]   # find where the claim applies
        if not rows:
            return (None, ...)                    # trigger never occurred
        for r in rows:
            if not EFFECT(r):
                return (False, ...)               # the design is wrong here
        return (True, ...)

The three verdicts are not interchangeable and each MEANS something:

    None   "this trace never put the design in the situation the requirement
            is about."  A statement about the STIMULUS. Costs nothing.
    False  "I saw the situation the requirement is about, and the design did
            not do what the requirement says."  An accusation against the
            DESIGN. Someone will go and change code because of it.
    True   "I saw the situation, and the design did what it says."

Combinators are the same skeleton written shorter. `after(trace, opens,
until=closes)` builds the trigger windows. `throughout(w, p)` /
`eventually(w, p)` assert the effect inside one. `worst([...])` folds them. A
check using them has a trigger and an effect exactly like the loop above; read
them out of the combinator arguments.

================================================================
3. THE RULE
================================================================

    FOR EVERY PATH ON WHICH THE CHECK RETURNS False, THERE MUST BE A SENTENCE
    IN THE REQUIREMENT SAYING THAT A DESIGN BEHAVING THAT WAY IS WRONG.

That is the whole question. Find each way the check can return False. For each,
describe the design it would convict, and point at the words that condemn it.
If you cannot point at the words, that path convicts where the requirement is
silent, and the answer is NO.

Note what the rule does NOT ask. It never asks whether the check demands
ENOUGH. A check that convicts only where the requirement speaks, but does so
weakly, is a YES.

================================================================
3b. THE PRIOR QUESTION: IS THERE AN OBLIGATION AT ALL?
================================================================

The rule above presupposes that the requirement CONTAINS sentences condemning a
design. Some requirements do not, and for those the rule has nothing to run on.

    CAN YOU DESCRIBE A DESIGN THAT THIS SENTENCE, IN ITS OWN WORDS, CALLS
    WRONG?  If no such design exists, the requirement states no obligation.

Two shapes fail it.

  A DEFINITION says what something IS or MEANS.
      "The cmd[3:0] input is the bit-level command provided by the byte-level
       controller."
      "The arbitration-lost output al indicates that the controller has
       detected an arbitration loss."
    Name the design these convict. There is none: they are true of every
    implementation and false of none.

  A SCOPE STATEMENT names a capability without saying what must happen.
      "The module begins operation with a reset and initialization sequence."
    Which design does it condemn? One with no reset -- but the sentence never
    says what the sequence must DO, so no trace can contradict it.

WHY THIS IS ASKED OF YOU AND NOT OF THE AUTHOR. The author was handed this
sentence and told to write a check for it. It cannot decline. Faced with a
definition it will produce the most plausible-looking check in the
neighbourhood -- typically an obligation borrowed from a nearby requirement --
and that check will be well-formed, satisfiable and confident. **A competent
check is therefore not evidence that the requirement asked for one.** You are
the only reader positioned to notice, because you hold the sentence and the
code side by side.

THE BOUNDARY, AND IT IS THE WHOLE RISK IN THIS SECTION. This is NOT the
internal-signal rejection, which section 7 forbids outright and for good reason.
A sentence may name an invisible mechanism and still state a real obligation:

  OBLIGATION, despite naming an internal counter --
      "When the core enable input ena is low, the module reloads the internal
       counter cnt from clk_cnt and normal command-FSM bit timing does not
       progress."
    `cnt` is invisible and no check can watch it. But the sentence ALSO says
    bit timing does not progress, and a design whose outputs advanced while ena
    was low is condemned by those words. That is an obligation. Answer yes.

  NO OBLIGATION --
      "The slave_wait condition indicates that another bus participant is
       holding the SCL line low."
    Also names an invisible signal -- but says only what the condition MEANS.
    No design is wrong by it. Answer no.

So the question is never "can this be observed". It is "does this sentence
forbid anything". Read past the mechanism to whatever the sentence claims must
happen, and if you find a claim, there is an obligation.

WHEN YOU ANSWER NO. Set `states_an_obligation` to false, say in
`what_is_missing` which part is absent -- the trigger, the effect, or both --
and do not labour the fit question: it is unanswerable when there is nothing to
fit. This verdict does not go back to the check's author, because nothing the
author writes can add an obligation to a sentence that has none. It goes to
whoever wrote the specification. So a no here ENDS the requirement rather than
spending a repair round on it, which is why it must be a reading of the
sentence and never a complaint about the check.

================================================================
4. HOW ENGLISH MAPS ONTO CODE
================================================================

These are the phrasings that appear in this specification and what each one
licenses. Mismatches here are the commonest defect.

  "when X" / "while X" / "during X"
      TRIGGER is the rows where X holds. Convicting on a row where X does not
      hold is unlicensed.

  "after X" / "X then Y"
      TRIGGER opens at X; the effect is asserted on LATER rows. Requiring the
      effect on the same row as X is a different claim.

  "X causes Y" / "driving X low drives Y low"
      A relation between VALUES: wherever X holds, Y holds. This is NOT an
      edge. A design that has X true from reset and never transitions still
      satisfies it, and a check triggering only on the transition into X never
      examines that design at all.

  "X shall assert Y" / "Y must be produced"
      An OBLIGATION. Y failing to appear IS the violation, so False is
      licensed when the trigger held and Y never came.

  "Y is high while X" / "Y is observed low" / "Y remains released"
      A STATE, not an event. The design may already be in it. Requiring a
      TRANSITION into that state convicts a design that was correct all along.

  "until X"
      The trigger window CLOSES at X. Rows after X are outside the claim.

  "for exactly one clock" / "within N cycles"
      A count, and licensed ONLY if the text states the number. If it does not,
      any cycle count in the check is unlicensed.

  "the module reloads its internal counter" / "the FSM remains in idle"
      The SUBJECT is internal and is not in the trace. The check must decide at
      the port the effect reaches -- see section 6 -- and doing so is correct.

================================================================
5. A CORRECT CHECK, READ OUT IN FULL
================================================================

REQUIREMENT  "The module clears the cmd_ack output so cmd_ack is deasserted
             while reset is active (nReset low or rst high)."
             TRIGGER: reset active.  EFFECT: cmd_ack == 0.  PORT: cmd_ack.

CODE         reset_rows = [r for r in trace
                           if r['inputs'].get('nReset') == 0
                           or r['inputs'].get('rst') == 1]
             if not reset_rows:
                 return (None, None, 'reset never observed in this trace')
             for r in reset_rows:
                 if r['outputs'].get('cmd_ack') == 1:
                     return (False, r['edge'], 'cmd_ack asserted while reset')
             return (True, None, ...)

WHY IT IS A YES.  One False path: a row where reset is active and cmd_ack is 1.
The requirement's own words condemn exactly that design. The trigger is the
requirement's trigger. Rows outside reset are never convicted. Absence of reset
returns None, not False.

AND NOTE WHAT IT DOES NOT DO, WHILE STILL BEING A YES. It does not check WHEN
cmd_ack cleared, or that it stays cleared, or anything about the other outputs.
That is how much it demands, which is not your question.

================================================================
6. THE FIVE WAYS IT GOES WRONG, EACH WITH A REAL CASE
================================================================

--- (a) CONVICTS ON MISSING EVIDENCE ------------------------------------
The check returns False because it did not SEE something, rather than because
it saw the design do the wrong thing. "I have no evidence" is not "the design
is broken".

  BAD   past = w.past('scl_oen')
        if past is None:
            return False          # the previous value was not available
  BAD   "no indicator observed -> return False"
  GOOD  return (None, None, 'the scenario never occurred in this trace')

Ask: could this False fire on a PERFECT design given a thin stimulus? If yes,
it is this defect.

--- (b) TRIGGERS ON THE WRONG SITUATION ---------------------------------
The window opens somewhere other than where the requirement's trigger holds, so
the check convicts on rows the requirement never covered -- or misses the rows
it did.

  REQUIREMENT  "Driving an output-enable low CAUSES the corresponding line to
               be driven low."   (a relation on values)
  BAD          fell = edges(trace, 'scl_oen', 'fall')
               opens = lambda r: r['edge'] in fell
               -> only examines the TRANSITION. A design holding the enable low
                  from reset is never checked, and the requirement covers it.
  GOOD         opens = lambda r: r['outputs']['scl_oen'] == 0

--- (c) ASSERTS THE TRIGGER INSTEAD OF THE EFFECT ------------------------
The window opens on a condition and the assertion re-states that same
condition. It reduces to "when X, X" and no design can fail it.

  BAD   windows = after(trace, lambda r: r['outputs']['scl_oen'] == 0)
        throughout(w, lambda r: r['outputs']['scl_oen'] == 0)
  GOOD  throughout(w, lambda r: r['outputs']['scl_o'] == 0)   # the EFFECT

--- (d) CONVICTS ON PORTS THE REQUIREMENT NEVER MENTIONS ------------------
An extra conjunct is added, and the check now fails designs that break the
extra one while satisfying the requirement.

  REQUIREMENT  "The module pauses bit timing while SCL is held low by another
               participant."   (says nothing about cmd_ack)
  BAD          never(w, cmd_ack_rises)      # cmd_ack is not in the claim
  GOOD         assert only what the requirement names.

--- (e) CONVICTS OUTSIDE THE CLAIM'S SCOPE -------------------------------
The requirement speaks about an instant or a bounded window; the check asserts
over a longer span, and convicts on rows after the claim has closed.

  REQUIREMENT  "The FSM releases SDA while SCL is high to generate a STOP."
  BAD          throughout(w, sda_oen == 1)  over the whole remaining window
  GOOD         assert it where the requirement says it holds, and stop there.

================================================================
7. NOT YOUR QUESTION -- ANSWER YES
================================================================

  HOW MUCH IT DEMANDS.  Loose, untimed, only one of several sub-conditions,
  weaker than you would have written. A different gate measures that, and
  answering it here pushes every check toward demanding more while that gate
  pushes them toward demanding less.

  HOW IT IS WRITTEN.  Combinators, structure, helper functions, style.

  WHERE IT READS A VALUE FROM.  `row['outputs']` versus `row['inputs']` is a
  mechanical slip, not a claim about the requirement. One real case turned on
  exactly this and it is NOT a correspondence defect.

  THAT IT DOES NOT WATCH AN INTERNAL SIGNAL.  The trace carries the declared
  ports and nothing else -- no counter, no state variable, no internal flag,
  whatever the requirement's sentence names. "It would need to observe
  <internal signal>" is NEVER a valid rejection: it asks for something no check
  can do. This project has made that mistake once already, calling 27 of 77
  requirements unobservable by reading each one's MECHANISM instead of its
  EFFECT, when 10 of them already had working checks.

================================================================
8. WHAT YOU ARE GIVEN, AND WHAT TO DO WITH IT
================================================================

`normalized.observed_via` is the OBSERVATION ROUTE: the declared port this
requirement is decidable at, `when` that port carries THIS requirement's effect
rather than another's, and `shows` -- what the port does when the requirement
holds and when it does not. THAT IS THE STANDARD. A check deciding at the
route's port under the route's condition is correct even when the requirement's
own sentence names something invisible.

`route_requirements` prints any requirement a route points at through
`through_req`. Read it for one thing: has the check silently become THAT
requirement's check? If it would pass or fail identically whether or not THIS
requirement holds, it is testing the neighbour under a different uid. `when` is
what was supposed to separate them. That is a NO, and it is a rejection only
you can make.

`interface` lists every declared port with its direction. A port not in that
list is internal -- see section 7.

PROCEDURE. In `reasoning`, in this order:
  0. section 3b: name a design this sentence's own words call wrong. If you
     cannot, say so and answer `states_an_obligation: false` -- the rest does
     not apply;
  1. the requirement's TRIGGER and EFFECT, in its own words;
  2. the check's trigger and the check's assertion, read out of the code;
  3. each way the check can return False, and the sentence that licenses it,
     or the absence of one.
Then answer.

There is no third answer. If you want to say "unclear", decide which is more
nearly true and say why -- a reviewer that can abstain does, and an abstention
decides nothing.

Reply with ONE JSON object and nothing else:

{
  "reasoning": "trigger and effect; the check's trigger and assertion; each False path and its licence",
  "states_an_obligation": true,
  "tests_the_requirement": true,
  "what_is_missing": "on either false: for states_an_obligation, which part the sentence lacks -- trigger, effect, or both. For tests_the_requirement, which False path is unlicensed and what the check's TRIGGER would have to become. Deleting the offending assertion is usually not the fix -- measured, the repairs that worked rebuilt the window."
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


def _through(normalized: dict, siblings: dict[str, dict]) -> dict:
    """The requirements a route POINTS AT, so the pointer is not dangling.

    `through_req` names the requirement whose port this one borrows, and until
    now the prompt carried the uid and nothing else -- "REQ-0007" appearing
    exactly once, with that requirement's text and normalized form both absent.
    A reviewer told a behaviour is visible through REQ-0007 and given no way to
    read REQ-0007 cannot evaluate the route at all, and falls back to the only
    thing it can read: this requirement's own sentence, which is the MECHANISM
    the route exists to get past. That is arm C's failure mode exactly.

    It also unblocks the one job the route design assigned this gate -- asking
    whether an indirect check silently became the SIBLING's check. That test is
    not expressible without the sibling in front of the reviewer.

    Texts only, and only the ones a route names: the requirement sentence and
    the normalized fields that say where IT is decided. No design, so I1 holds.
    """
    out: dict[str, dict] = {}
    for route in normalized.get("observed_via") or []:
        uid = route.get("through_req")
        if not uid or uid in out:
            continue
        sib = siblings.get(uid)
        if not sib:
            continue
        out[uid] = {k: sib[k] for k in ("text", "observable", "expectation")
                    if sib.get(k) is not None}
    return out


def build_prompt(
    *,
    requirement: dict,
    oracle: RequirementOracle,
    normalized: dict | None = None,
    spec: str = "",
    contract: dict | None = None,
    siblings: dict[str, dict] | None = None,
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
        borrowed = _through(normalized, siblings or {})
        if borrowed:
            parts.append(json_block("route_requirements", borrowed))
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
    siblings: dict[str, dict] | None = None,
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
                                contract=contract, siblings=siblings))
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
    # Every requirement, keyed by uid, so a route's `through_req` resolves. The
    # caller already holds them; the reviewer only ever sees the handful its
    # own routes name.
    sibs = {u: {**requirements.get(u, {}), **{k: v for k, v in norm.get(u, {}).items()
                                              if k in ("observable", "expectation")}}
            for u in requirements}

    def one(oracle: RequirementOracle) -> Review:
        return review_one(
            oracle, requirements[oracle.req_uid], port=port,
            normalized=norm.get(oracle.req_uid), spec=spec,
            contract=contract, siblings=sibs, round_=round_)

    done = run_fanout(wanted, one) if fanout else [one(o) for o in wanted]
    return {o.req_uid: r for o, r in zip(wanted, done)}


def rejects(out: Review) -> str:
    """Why this oracle is not a check of its requirement, or empty.

    A reply that could not be parsed is not a rejection: see `review_one`.
    """
    if out.reasoning.startswith(PARSE_ERROR):
        return ""
    detail = out.what_is_missing or out.reasoning or "(no detail)"
    # THE PRIOR QUESTION WINS, including when the reply says both. "This
    # sentence forbids nothing" and "your check is off-target" are not two
    # grades of the same finding: the first accuses the specification and ends
    # the requirement, the second accuses the check and buys it a repair round.
    # Reporting the second when the first is true sends the author to fix
    # something that is not theirs, which is the routing error this whole enum
    # exists to prevent.
    if not out.states_an_obligation:
        return f"not-assertable: {detail}"
    if out.tests_the_requirement:
        return ""
    return f"off-target: {detail}"
