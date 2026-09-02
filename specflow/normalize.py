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
import logging
import re
from pathlib import Path

from pydantic import (BaseModel, Field, computed_field, field_validator,
                      model_validator)

from eda_agent.utils import extract_json_object, strip_markdown_code_fences

from . import encoding
from .fanout import compose, json_block, shared_block
from .model_io import ModelPort
from .schema import Issue
from .stage import StageResult, run_fanout, run_stage

logger = logging.getLogger(__name__)

STAGE = "normalize"

#: House convention: a `reasoning` starting with this is a parse failure, not a
#: conclusion (`s1_requirements.py:145-153`, `judge.py:242`).
PARSE_ERROR = "Parse Error: "


#: Phrases that name a SPAN rather than an instant. Lexical, and broad on
#: measured grounds rather than by default.
#:
#: The narrower reading is tempting: `after(trace, activation)` with no `until`
#: already closes when the activation stops holding, so "while X" with
#: `inputs={X}` is CORRECTLY normalised and warning on it looks like a false
#: positive by construction. Restricting the list to the sequential words on
#: that argument makes the screen strictly worse on BOTH axes -- measured
#: against a2-i2c's 41 known-bad checks (over-strict plus vacuous):
#:
#:     sequential only            fires 39/105   recall 36%   precision 38%
#:     sequential + co-extensive  fires 73/105   recall 80%   precision 45%
#:
#: Because "during an accepted WRITE" needs a close condition and "during reset"
#: does not, and which one a phrase is depends on whether the activation outlasts
#: its own trigger -- not on the word. No lexical split separates them, and the
#: broad list at least separates them no worse.
#:
#: This is a MIGRATION signal, not a permanent lint. A high count now is the
#: finding; it falls as normalisation starts filling `until`.
#: Edge words a condition may carry instead of a level. Mirrors
#: `temporal.EDGES` -- the one place that computes them.
_EDGE_WORDS = frozenset({"rise", "fall", "change"})

_WINDOW_WORDS = re.compile(
    r"\b(during|while|throughout|until|for the duration|as long as|"
    r"start of|end of|sequence|phase|then|after|subsequent|following)\b",
    re.IGNORECASE)


def _names_a_window(text: str) -> bool:
    return bool(_WINDOW_WORDS.search(text or ""))


class Sustain(BaseModel):
    """How long an opening condition must HOLD, in consecutive sampled rows.

    `until` bans counts on purpose -- "for 12 edges" is a guess at pacing the
    specification does not state, and Phases 3-6 severed pacing from latency
    for exactly that reason. That rule is right about PACING and wrong about a
    count the design's own structure fixes.

    MEASURED, and it cost the filter. REQ-0046 is "majority voting over the
    THREE-SAMPLE histories must produce sSCL and sSDA so that short glitches are
    suppressed". Its `observed_via` correctly prescribed the discriminating
    experiment -- "apply a pulse SHORTER than the majority-filter window (fewer
    than 2 of 3 samples) AND COMPARE WITH a sustained change occupying at least
    2 of 3" -- and no field could carry it. The activation came back
    `opens_on: [{scl_i: change}, {sda_i: change}]`, which is "any edge", and the
    authored check faithfully implemented that: "no output may change on any
    input edge". It convicts every design including golden, was correctly judged
    ORACLE_INVALID, and was dropped -- leaving nothing to notice when a debug run
    later deleted the filter outright and scored ABOVE golden for it.

    "Fewer than 2 of 3 samples" is not a pacing guess. It is the filter's own
    arity, stated by the requirement. A count that comes from the specification
    is expressible here; one invented to describe latency still is not, and
    `until` remains the place for conditions.

    `temporal.pulse(w, port, active=, width=)` already evaluates exactly this --
    "port must go active for exactly `width` consecutive rows, once" -- so the
    capability existed where the oracle RUNS and was missing where it is
    SPECIFIED.
    """

    #: The port whose run-length is bounded.
    port: str = ""
    #: The value it must hold for that run. A symbol where the port has an
    #: encoding, resolved by `specflow.encoding` like everywhere else.
    value: int | str = 0
    #: Inclusive bounds on the run, in CONSECUTIVE SAMPLED ROWS. `at_most=1` is
    #: a glitch narrower than a 3-sample majority; `at_least=2` is one wide
    #: enough to survive it. Either may be omitted; both omitted is not a
    #: constraint and is rejected rather than silently ignored.
    at_least: int | None = None
    at_most: int | None = None
    #: Why this count is the specification's rather than the author's, quoting
    #: the span it came from. Required, because the whole reason `until` refuses
    #: counts is that an unattributed one is a guess.
    stated_by: str = ""

    @model_validator(mode="after")
    def _one_bound_at_least(self):
        """A `field_validator` on `at_most` does NOT run when the field is left
        at its default, which is precisely the unbounded case it exists to
        reject -- so written that way the guard was inert. Caught by testing the
        rejection rather than the acceptance."""
        if self.at_least is None and self.at_most is None:
            raise ValueError(
                "a Sustain with neither at_least nor at_most constrains "
                "nothing; give a bound or drop the entry")
        if (self.at_least is not None and self.at_most is not None
                and self.at_least > self.at_most):
            raise ValueError(
                f"at_least={self.at_least} exceeds at_most={self.at_most}, so "
                f"no run length satisfies this entry")
        return self


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
    #:
    #: INPUT PORTS ONLY, and that restriction is load-bearing:
    #: `obligation.check_static` decides from the stimulus steps alone, "no
    #: model, no replay, no doubt", which is only possible because every name
    #: here is something the stimulus drives. Conditions on outputs go in
    #: `opens_on`.
    #:
    #: A VALUE MAY BE A SYMBOL, and where the port declares an encoding it
    #: should be: `{"cmd": "I2C_CMD_WRITE"}`. The specification names its
    #: commands by symbol and never states the numbers, so a number written here
    #: is a guess -- and it was guessed independently at four stages that never
    #: compared answers. Measured on c1-i2c: "WRITE" came back as 4, 1, 2 AND 3
    #: across the corpus, and seven requirements used a value the design decodes
    #: as nothing. `specflow.encoding` resolves the symbol against the ONE table
    #: on the contract, so the number stops being anybody's opinion.
    #: A VALUE MAY ALSO BE A LIST, MEANING ANY OF THESE:
    #: `{"cmd": ["I2C_CMD_START", "I2C_CMD_STOP", "I2C_CMD_READ",
    #:           "I2C_CMD_WRITE"], "ena": 1}` -- the window opens on any of the
    #: four commands, and `ena` must be 1 in every case.
    #:
    #: WITHOUT IT THIS FIELD COULD ONLY SAY "AND". It is a mapping port ->
    #: value, so every named port had to hold together, and a requirement
    #: triggered by ANY OF several values had nowhere to say so. `opens_on`,
    #: `until` and `aborts_on` all took the list-of-alternatives shape long ago
    #: for exactly this reason; `inputs` was the last field that could not.
    #:
    #: Measured on h2-i2c: of 22 observable requirements whose activation
    #: carried no trigger at all, 8 had a disjunctive one -- "a START, STOP,
    #: READ, or WRITE command is accepted while the FSM is idle", "reset is
    #: asserted via nReset low or rst high" -- which the model wrote into
    #: `text`, where no gate and no oracle can reach it. It knew the trigger and
    #: had nowhere to put it, so the activation read as unconditional.
    #:
    #: A DISJUNCTION ACROSS DIFFERENT PORTS is not this: "nReset low OR rst
    #: high" names two ports, and a per-port value-set cannot express it. That
    #: one belongs in `opens_on`, which is disjunctive normal form and already
    #: general enough -- `[{"nReset": 0}, {"rst": 1}]`.
    inputs: dict[str, int | str | list[int | str]] = Field(default_factory=dict)
    #: The rest of the opening condition, and this one MAY name outputs.
    #:
    #: A LIST OF ALTERNATIVES: any entry opening the window is enough, and every
    #: port WITHIN one entry must hold together. Disjunctive normal form, which
    #: is fully general and is the shape the requirements actually take --
    #: REQ-0028 is "an output-enable (scl_oen or sda_oen) is driven low", where
    #: a single dict `{scl_oen: 0, sda_oen: 0}` says BOTH and means neither.
    #:
    #: The schema had one slot for "when" and it held inputs, so a requirement
    #: activated by an OUTPUT had nowhere to say so and the slot was filled with
    #: whatever inputs were lying around -- REQ-0028's came back
    #: `{nReset: 1, rst: 0}`, the reset qualifier and none of the condition.
    opens_on: list[dict[str, int | str]] = Field(default_factory=list)
    #: WHERE THE WINDOW CLOSES -- same any-of-a-list shape, outputs allowed.
    #: Empty means the requirement is about the activation instant itself.
    #:
    #: This is the field whose absence caused the largest measured defect here.
    #: `Activation` could express only a predicate over ONE ROW, while 63% of
    #: a2-i2c's 105 requirements name a span in their own text. Normalisation
    #: flattened each to the instant the activation began, so every check over
    #: one became a point check -- which fails every design or passes every
    #: design depending only on which way the port sat at that instant. Measured:
    #: the over-strict and vacuous populations are 79% and 83% that shape,
    #: against 58% of the checks carrying neither flag.
    #:
    #: AND THE LIST IS NOT DECORATION. Written first as a single dict -- mirroring
    #: `inputs` -- it read as a conjunction, and a close condition is routinely a
    #: disjunction: "until the command completes OR arbitration is lost". Six of
    #: 28 activations came back `{al: 1, cmd_ack: 1}`, which is unsatisfiable by
    #: construction, since arbitration loss drives the FSM to idle and clears
    #: `cmd_ack`. Those windows opened, ran off the end of the trace and decided
    #: nothing. `inputs` stays a plain dict because there the conjunction is
    #: right: every named input must be driven for the precondition to be
    #: reachable at all.
    #:
    #: A CONDITION, NEVER A COUNT. "until cmd_ack" is expressible; "for 12 edges"
    #: is a guess at pacing this specification does not state, and Phases 3-6
    #: severed pacing from latency for exactly that reason. Deliberately the same
    #: shape as the stimulus schema's own `until`, and it feeds
    #: `temporal.after(trace, applies, until=closes)` directly.
    until: list[dict[str, int | str]] = Field(default_factory=list)
    #: RUN-LENGTH BOUNDS on the opening condition -- the one count `until`
    #: refuses and a requirement can legitimately state. See `Sustain`: the
    #: filter requirement REQ-0046 needs "fewer than 2 of 3 samples", which is
    #: the filter's arity and not a pacing guess, and without this field the
    #: activation could only say "any edge".
    #:
    #: ALTERNATIVES, like `opens_on`: any entry satisfied opens the window, so a
    #: requirement discriminating short from sustained gives both and the check
    #: compares them. Empty is the norm; most activations are about an instant.
    sustains: list[Sustain] = Field(default_factory=list)
    #: SVA's `disable iff`: conditions that DISCARD the attempt rather than
    #: close it. Same shape as `until` and a different claim.
    #:
    #: `until` says the span ENDED, so whatever the requirement promised should
    #: have appeared by then. `aborts_on` says the span was CUT SHORT by
    #: something that makes the promise moot -- reset, or an arbitration loss
    #: that returns the FSM to idle -- and nothing is owed. Folded into `until`
    #: the two are indistinguishable, and a strong obligation over the second
    #: convicts a design for not doing what it was never asked to do. Measured
    #: on c1-i2c: 13 requirements close on reset and 40 on `al`, and REQ-0055
    #: convicts the known-good RTL because an `al` pulse the design is right to
    #: emit ends its window at edge 7, and the START it checks does not drive
    #: sda_oen low until edge 28 or ack until edge 38.
    #:
    #: NOT DERIVABLE, so it is asked rather than inferred: on 11 of those 40,
    #: `al` is the requirement's own declared observable -- the response it
    #: exists to check -- and rewriting those to aborts would delete the check.
    #: Whether a condition ends a span or voids it is a reading of the sentence.
    aborts_on: list[dict[str, int | str]] = Field(default_factory=list)

    @field_validator("opens_on", "until", "aborts_on", mode="before")
    @classmethod
    def _one_alternative_is_still_a_list(cls, v):
        """A bare dict is the single-alternative case. Accepted rather than
        rejected: the list is the general form, and refusing the common shape
        would spend a repair round on punctuation."""
        if isinstance(v, dict):
            return [v] if v else []
        return v

    @property
    def input_only(self) -> bool:
        return bool(self.inputs)

    @property
    def windowed(self) -> bool:
        """The requirement governs a span, not an instant."""
        return bool(self.until)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def effect_follows(self) -> bool:
        """Does the expectation land AFTER the trigger, or at it? -- `|=>`.

        DERIVED, NOT ASKED, and that is the point. `after_activation` was
        offered to the check author in prose with the measured count behind it,
        which is exactly the posture that got v1 of the temporal block 0 uptake
        in 306 responses. The schema already knows the answer, so it should
        carry it rather than request it.

        A window that closes on a CONDITION is a window whose effect outlasts
        its trigger: "during an accepted WRITE, until cmd_ack" describes bus
        activity that runs for many states after `cmd` was sampled. A window
        with no close condition is either an instant or co-extensive with a
        level -- "while ena is low" -- and there the expectation holds at the
        activation row too. So `bool(until)` is the whole rule.

        `computed_field` so it SERIALIZES: the author reads the normalized
        block as JSON, and a plain property would be invisible there.

        WHY `strong` IS NOT DERIVED THE SAME WAY, since the signal looks
        identical and is not. A non-empty `until` says the window closes on a
        condition; it does NOT say the requirement asserts that the closing
        happens. "During a WRITE, sda_oen follows din" with `until cmd_ack` is
        about sda_oen, not about the write completing -- deriving `strong` from
        the same field would convict a design whose trace merely ended early.
        Liveness is a claim in the requirement's own words and stays a claim
        the author makes.
        """
        return bool(self.until)

    @property
    def unconditional(self) -> bool:
        """The requirement applies at all times, so there is nothing to reach.

        `input_only` was carrying this case and getting it wrong. It is
        `bool(self.inputs)`, so "at all times" with no inputs reports
        `input_only == False` and reads as state-dependent -- conflating "no
        inputs because none are needed" with "needs something to run". Measured
        on a2-i2c: 11 requirements looked state-dependent by that test and 8 of
        them were `"always"` or `"at all times"`.

        Lexical, and deliberately conservative in one direction: a missed
        unconditional costs one model call asking how to reach `"always"`, while
        a missed STATE-dependent silently skips the reaching chain the stimulus
        author needed. So a conditional connective anywhere disqualifies it, and
        when in doubt this returns False.
        """
        text = (self.text or "").strip().lower()
        if not text:
            return False
        if re.search(r"\b(when|while|if|after|before|during|until|unless|once)\b",
                     text):
            return False
        return bool(re.match(r"^(always|at all times|continuously|"
                             r"at every (clock|clk|rising edge)|unconditionally)\b",
                             text))

    @property
    def state_dependent(self) -> bool:
        """Something has to have HAPPENED for this requirement to apply.

        Not drivable as input values, and not true at all times -- the only case
        that needs an `activated_via` chain. "while the FSM is in START_B" is
        this; "cmd is WRITE and ena is 1" is not; "at all times" is not.
        """
        return not self.input_only and not self.unconditional


class Route(BaseModel):
    """How a requirement is observed at a port it does not itself name.

    ONE OF SEVERAL ALTERNATIVES. Each route independently suffices, and more
    routes mean a more robust check -- which is the opposite of `Reach` below,
    where every hop is required. Conflating the two would let a requirement look
    reachable on one of three necessary steps.

    A POINTER IS NOT A ROUTE. `{port, through_req}` tells the oracle author
    where to look and nothing about what to expect there, which is how an
    indirect check becomes a restatement of the requirement it borrowed from.
    `shows` carries the DISCRIMINATION: "busy is observable" is useless, "busy
    stays low for a glitch narrower than the filter depth and rises for one at
    or above it" is an oracle.
    """

    #: A declared OUTPUT port the behaviour reaches.
    port: str = ""
    #: The requirement whose own text names that port.
    through_req: str = ""
    #: When that port carries THIS requirement's effect rather than the other's.
    when: str = ""
    #: What the port does when this requirement holds, AND when it does not.
    #: Two cases, or there is nothing for a check to discriminate between.
    shows: str = ""
    #: WHAT THE PORT DOES WHEN THE REQUIREMENT DOES NOT HOLD. A SECOND SLOT,
    #: not a second sentence, and that is the whole point of the change.
    #:
    #: The demand for two cases is right: a check written over "the port shows
    #: X" with nothing to contrast against passes any design that ever shows X,
    #: including one with none of the behaviour. What was wrong was INFERRING
    #: two-ness from prose. The old gate searched `shows` for " not ",
    #: "otherwise", "does not" or " and " -- a substring test standing in for a
    #: semantic property -- and it gave opposite verdicts to identical claims:
    #: REQ-0004's "no discrimination: scl_o is structurally tied to 0" was
    #: recorded as undecidable, while REQ-0034's "there is no case where this
    #: requirement does not hold" -- the same claim -- passed as a real check,
    #: because the string happens to contain " not ".
    #:
    #: With two slots the check is a FACT rather than a guess: is the second one
    #: filled. No wording is privileged, an author writing plainly is not
    #: punished for its vocabulary, and the escape hatch stays an explicit
    #: opt-in rather than something inferred.
    otherwise: str = ""


class Reach(BaseModel):
    """One hop toward the state a requirement's activation needs.

    ONE HOP, NOT A CHAIN. Normalisation sees one requirement against the merged
    set and can answer "to be in START_B, REQ-0012 must have just fired"
    reliably; asking it for the whole chain back to reset asks it to hold the
    design's state machine in its head, and one wrong link invalidates the rest.
    The transitive walk is mechanical -- see `reaching`.

    `activation` reuses `Activation` verbatim rather than inventing a second
    vocabulary for "what must be driven".

    AND A POINTER IS NOT A ROUTE HERE EITHER. `Route` says this in its own
    docstring and then carries `when` and `shows` to fix it; this class carried
    `{through_req, activation}` and nothing else, which is the pointer shape
    `Route` rejects. "REQ-0096 puts the FSM into the READ sequence" tells an
    author which requirement to thank and gives it no way to RECOGNISE, in a
    trace of declared ports, that the sequence is now running -- so the check it
    writes opens on whatever is easy to see instead.

    Measured on n4-i2c: 8 requirements were rejected with the same objection --
    "the trigger must identify an actual command sequence", "it must open only
    on a filtered-SCL rising edge during an active READ" -- and every one had an
    empty `activated_via`. Filling it with the pointer alone would not have
    answered any of them.

    So `when` and `shows` mirror `Route`'s, and mean the activation-side thing:
    `when` is the condition under which the hop actually delivers the state,
    `shows` is how the boundary betrays that it has.
    """

    through_req: str = ""
    activation: Activation = Field(default_factory=Activation)
    #: The condition under which this hop actually puts the design in the state
    #: -- not every firing of `through_req` need do so.
    when: str = ""
    #: How a trace of DECLARED PORTS tells you the hop has fired and the state
    #: now holds. Without this the author cannot open a window on it, which is
    #: the whole point of naming the hop.
    shows: str = ""


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
    #: Alternatives, any one sufficient -- for EVERY requirement, not only the
    #: blind ones. A directly observable requirement names its own port with an
    #: empty `through_req`; an indirect one names another requirement's.
    #:
    #: The base case rather than the exception, because the field that matters
    #: is `shows` and only the exception was ever being asked for it. REQ-0075
    #: ("the FSM advances only when clk_en is asserted") was DIRECTLY
    #: observable, got `observed_via: []`, and was never made to say what
    #: distinguishes the requirement holding from it not holding -- so its check
    #: settled for "an output moved", which nothing can falsify. Asking every
    #: requirement for the discrimination puts the vacuity check a stage earlier
    #: and applies it to all of them instead of to the 28 that borrowed a port.
    #:
    #: `observable` still holds the ports it is decidable at by ANY route, so
    #: every downstream stage keeps reading one field.
    observed_via: list[Route] = Field(default_factory=list)
    #: Prerequisites, ALL required, one hop each. A hop with an EMPTY
    #: `through_req` is the direct case -- the activation is driven, and the
    #: hop's `activation.inputs` are the values that drive it.
    #:
    #: ASKED OF EVERY REQUIREMENT, exactly as `observed_via` is, and for the
    #: same reason. Observation never had a selector: the direct pass asks the
    #: question of everyone and an empty `through_req` means "my own port", so
    #: there is no predicate to get wrong. Activation had one -- entry was gated
    #: on `state_dependent`, which rested on `input_only == bool(self.inputs)`
    #: -- and it got it wrong for 76 of 110 requirements on n4-i2c, because
    #: `{nReset: 1, rst: 0, ena: 1}` is a precondition carried by almost every
    #: requirement in the module and satisfies `bool(...)` exactly as a real
    #: trigger does. 49 of those carried nothing else.
    #:
    #: The heuristic could not be repaired by a better port list either: on this
    #: module `ena = 1` selects 95.9% of recorded rows and discriminates
    #: nothing, while `ena = 0` selects 4.1% and IS the trigger of REQ-0015. A
    #: name-based rule would have discarded that requirement's actual trigger,
    #: and would not transfer to a module whose enable is called something else.
    #:
    #: So the question is asked rather than inferred. The model already knows
    #: which of its inputs constitute the trigger; nothing else does.
    activated_via: list[Reach] = Field(default_factory=list)
    #: Why the activation cannot be reached, set if and only if the model can
    #: say the requirement needs a prior event it cannot name. The mirror of
    #: `unobservable_reason`, and it replaces the inferred `state_dependent` as
    #: what nominates a requirement for the indirect pass -- a claim the model
    #: makes, not one the harness guesses on its behalf.
    unreachable_reason: str = ""

    @field_validator("observed_via", "activated_via", mode="before")
    @classmethod
    def _accept_the_shapes_the_model_actually_returns(cls, v):
        """Coerce a losslessly-equivalent shape instead of losing the record.

        THIS DISCARDED FIVE REQUIREMENTS' NORMALIZATION ENTIRELY. Pydantic
        rejects the whole `NormalizeOutput` on one field's shape, and the stage
        recorded a Parse Error and moved on -- so REQ-0010, REQ-0017, REQ-0048,
        REQ-0078 and REQ-0100 reached the oracle author with NO activation and NO
        observation route, and a check was written for each of them anyway.
        REQ-0010's is the naive "no output may change on any input edge", which
        is what authoring with no normalized form looks like; it went on to
        INVERT, passing a design that deleted the input filter while convicting
        the golden one.

        The returned content was complete every time. Only its shape differed:

            {"busy": {through_req: ...}, "al": {...}}   dict KEYED BY PORT
            {"port": "cmd_ack", "through_req": ...}     a single route, unwrapped

        Both carry strictly more than enough to build the list, so refusing them
        loses information the model successfully produced. A keyed dict supplies
        `port` from its key; a bare dict is a list of one.

        Deliberately NOT permissive about content -- an entry that is neither a
        mapping nor a `Route` still fails, and `_check_routes` still demands
        `shows` name both cases. This widens the accepted SHAPE, not the standard.
        """
        if isinstance(v, dict):
            # Keyed by port: {"busy": {...}} -> [{"port": "busy", ...}]
            if v and all(isinstance(x, dict) for x in v.values()):
                return [{"port": k, **x} for k, x in v.items()]
            # A single route returned unwrapped.
            return [v]
        return v

    @field_validator("observable", mode="before")
    @classmethod
    def _observable_may_arrive_as_routes(cls, v):
        """`observable` is a list of PORT NAMES, and REQ-0048's came back as a
        list of route objects -- `{"port": "busy", "through_req": ...}`. The port
        is right there under its own key; taking it costs nothing and keeps the
        requirement, where refusing cost REQ-0048 its entire normalization."""
        if isinstance(v, list):
            return [x.get("port", "") if isinstance(x, dict) else x for x in v]
        return v

    @property
    def unobservable(self) -> bool:
        return not self.observable

    @property
    def unreachable(self) -> bool:
        """The model said the activation needs a prior event it cannot name."""
        return bool(self.unreachable_reason.strip())

    @property
    def indirect(self) -> bool:
        """Observed at a port its own text does not name.

        `through_req`, not a non-empty list. Every requirement carries a route
        now -- a directly observable one names its OWN port with `through_req`
        empty -- so the list being non-empty stopped meaning indirect the moment
        the route became the base case rather than the exception.
        """
        return any(r.through_req for r in self.observed_via)


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

THE REQUIREMENT BLOCK. `obligation` is the requirement: one span, the text this
requirement IS, and the only text anything will ever be checked against.
Normalise THAT.

`spec_spans` beside it is CONTEXT -- spans the obligation cannot be read
without. USE THEM. That is what they are for, and the fields they legitimately
supply are exactly the ones the obligation tends to leave open:

  * the ACTIVATION, when the obligation says what must hold but the condition
    it holds under is stated in the sentence that introduces it;
  * the OBSERVABILITY route, when the obligation names an internal signal and
    a context span says which port it reaches;
  * a DEFINITION -- the value of a term, the encoding of a command, the width
    of a field -- that the obligation uses without restating.

The ONE field a context span may never supply is the EXPECTATION. What must be
true is what `obligation` says, and only that. If a context span states a
behaviour of its own, that behaviour is a DIFFERENT requirement with its own
uid, listed in `supports`, and it is being normalised separately -- taking it
here would check the same thing twice under one name and leave the obligation
you were given unchecked.

`unit_kind` and `supportive` are bookkeeping from an earlier stage. Ignore them.

ACTIVATION. Give `text` always: the precondition in one clause. Additionally
give `inputs` -- a map of input port name to the value that must hold.

`inputs` is a NECESSARY condition, not a sufficient one. The question is not
"do these values guarantee the precondition" but "must these values be driven
for the precondition to be reachable at all". Those are different questions and
only the second is being asked here.

So a precondition phrased in terms of internal state STILL gets `inputs`,
whenever some input must have been driven to reach that state:

  "during the READ data-bit phase"     -> {"cmd": 8}   the phase is unreachable
                                                        without READ issued
  "when the WRITE sequence completes"  -> {"cmd": 4}   likewise
  "while the core is enabled and idle" -> {"ena": 1}   idle is state, ena is not

Give `inputs` empty ONLY when no input value whatsoever is required to reach the
condition -- "after arbitration has been lost" is the real case, because
arbitration loss is caused by the bus, not by anything a test drives. Reset
ports may appear in `inputs`: "while reset is asserted" is a genuine
precondition.

Why necessary is the right bar: a later stage uses `inputs` to decide whether a
testpoint is WORTH CHECKING against this requirement, and then runs the actual
check, which reports the scenario as unexercised if it did not occur. A value
that is necessary-but-not-sufficient therefore costs one wasted replay when it
is wrong, and an empty `inputs` costs the requirement every chance of ever being
exercised. Measured: leaving them empty put 57 of 77 requirements out of reach
of new stimulus, and a run that added 48 testpoints moved nothing at all.

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

THERE IS A THIRD ANSWER, and it is the right one more often than either of the
first two. You are shown ONE requirement. Some behaviour has no port of its own
and still reaches the boundary -- through what it makes some OTHER requirement
do. An FSM state is not a port, but whatever the design does IN that state is,
and another requirement describes it.

You cannot name that route: you cannot see the other requirements, so you do not
know which one owns which port. A later pass can, and will be asked. What helps
it is knowing you suspected one. So when the effect plainly reaches the boundary
but not through anything this sentence names, still give `observable: []`, and
say so in `unobservable_reason` in those words -- name the effect you think is
visible and what you think would show it:

  "not visible on any port this requirement names; the effect is that no START
   is detected, which should be visible wherever START detection is"

That is a different claim from "nothing at the interface distinguishes this",
and the difference is what the later pass is for. Do NOT reach for a port on the
strength of it -- writing a port you cannot justify is the mistake below, and it
is worse than this answer.

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


WHERE THE WINDOW CLOSES. Give `until` whenever the requirement governs a SPAN
that outlasts its own trigger -- port -> value, and this one MAY name outputs,
because a window closes on what the DESIGN does.

`until` IS A LIST OF ALTERNATIVES. Any ONE of them closing the window is
enough, and every port within ONE entry must hold together. So "or" is a second
entry and "and" is a second key:

  "during an accepted WRITE"          -> inputs {"cmd": 8}, until [{"cmd_ack": 1}]
  "at the start of the STOP sequence" -> inputs {"cmd": 2}, until [{"cmd_ack": 1}]
  "until the WRITE completes"          -> until [{"cmd_ack": 1}]

NAME A VALUE BY ITS SYMBOL WHERE THE PORT DECLARES ONE. The contract's port
list carries an `encoding` for any port whose values the design decodes by name:

  "a WRITE command is issued"   -> inputs {"cmd": "I2C_CMD_WRITE"}

NOT `{"cmd": 4}`. The specification names its commands and never states their
numbers, so a number here is YOUR READING and nothing checks it. Measured on one
design: "WRITE" came back as 4, 1, 2 and 3 across the requirement set, and seven
requirements used a value the design decodes as nothing -- windows that can
never open, which at decide time look exactly like a design that never did it.
The symbol resolves against the contract, so it cannot be any of those things.

Where a port declares NO encoding, write the number as before.

ENDING AND VOIDING ARE DIFFERENT, AND `aborts_on` IS THE SECOND ONE.

`until` says the span ENDED, so whatever the requirement promised should have
appeared by then. `aborts_on` says it was CUT SHORT by something that makes the
promise moot, and nothing is owed:

  "until the WRITE completes"          -> until     [{"cmd_ack": 1}]
  "...unless arbitration is lost"      -> aborts_on [{"al": 1}]
  "...or reset intervenes"             -> aborts_on [{"nReset": 0}, {"rst": 1}]

This is SVA's `disable iff`, and putting an abort in `until` is the single
costliest error this field has made. Measured on one design: 40 requirements
closed on `al` and 13 on reset, all as `until`. One of them, "each command
sequence drives the enables", convicted the KNOWN-GOOD RTL. An `al` pulse the
design is right to emit -- one row, at edge 7 -- ended its window, and the START
it was checking does not drive sda_oen low until edge 28 or ack until edge 38.
The check reported the response as never coming.

RESET IS ALWAYS AN ABORT, never a close. A design held in reset owes no
sequence, and a requirement whose text does not mention reset does not license
convicting one that was reset mid-command.

BUT AN ABORT IS A READING, NOT A RULE. On 11 of those 40, `al` was the
requirement's OWN observable -- "the module asserts al when arbitration is
lost" -- and there `al` is the response being checked, not an abort. Ask what
the sentence promises: if the condition is what the requirement is ABOUT, it
belongs in `observable`; if it is what stops the design owing the promise, it
belongs here.

Getting the list shape wrong is not cosmetic either.
`[{"al": 1, "cmd_ack": 1}]` is ONE entry naming two ports, so it asks for both
AT THE SAME ROW -- and arbitration loss drives the FSM to idle and clears
`cmd_ack`, so it can never happen. The window then opens, runs off the end of
the trace and decides nothing. Six of one run's 28 windows were exactly this.

`opens_on` takes the same list-of-alternatives shape, for the same reason:
"an output-enable (scl_oen or sda_oen) is driven low" is
`[{"scl_oen": 0}, {"sda_oen": 0}]`, and `[{"scl_oen": 0, "sda_oen": 0}]` says
BOTH and means neither.

A CONDITION, NEVER A COUNT. "until cmd_ack" is expressible; "for 12 edges" is a
guess at pacing this specification does not state, and a check that asserts one
either fails correct designs or asserts nothing.

`sustains` IS WHERE A COUNT GOES WHEN THE SPECIFICATION ITSELF STATES ONE, and
it is the one exception to the line above. The rule there forbids INVENTING
pacing; it does not forbid transcribing a duration the spec gives you. A
requirement whose whole content is a threshold -- "a majority of the three
consecutive samples", "at least two clocks", "shorter than the filter window" --
cannot be checked at all without it, because the property IS the count.

    "sustains": [
      {"port": "sda_i", "value": 0, "at_most":  1,
       "stated_by": "a majority of the three-sample history"},
      {"port": "sda_i", "value": 0, "at_least": 2,
       "stated_by": "a majority of the three-sample history"}
    ]

`port` and `value` say what is held; `at_least` / `at_most` bound how long, in
EDGES; `stated_by` quotes the words of the specification that give the number.
Give at least one bound -- an entry with neither constrains nothing and is
rejected. Two entries, one short and one long, are how a threshold requirement
states both sides of its own boundary.

LEAVE IT EMPTY unless the specification supplies the number. `stated_by` is the
test: if you cannot quote the phrase the count comes from, you are guessing
pacing, and the rule above applies instead.

Leave `until` EMPTY when the activation condition is itself co-extensive with
the span -- "while ena is low", "during reset". Those hold at every row they
govern, so the condition already delimits the window and a close condition would
be redundant.

The cost of getting this wrong is not small and is not hypothetical. A
requirement whose span was dropped can only be checked at the instant its
activation began, which reads the outputs before the design has done anything.
Depending on which way the port happens to sit at that instant, the check then
fails EVERY design or passes every design -- and on one measured run those two
populations were 79% and 83% exactly this.

NEVER NAME THE CLOCK. Every row of the trace a check sees is already a clock
edge, so `{"clk": "rise"}` matches no row at all and `{"clk": 1}` matches every
one. If the requirement says "on the rising edge of clk", the trigger is
whatever ELSE must be true at that edge -- name that instead.

AN EDGE IS NOT A LEVEL. Where the requirement says a signal RISES, FALLS or
CHANGES, write that word instead of a value -- `"rise"`, `"fall"`, `"change"`:

  "a falling edge on the filtered SCL
   while the controller has released SCL"
        -> opens_on [{"scl_i": "fall", "scl_oen": 1}]
  "dout captures on the rising edge of SCL"
        -> opens_on [{"scl_i": "rise"}]

Levels and edges mix freely inside one entry: the edge ports must have just
transitioned, and the level ports must hold at that same row.

Writing a level where the requirement means an edge changes what is being
asked. `{"scl_i": 0, "scl_oen": 1}` is "both hold at some row", which is ALSO
true when `scl_oen` rises over an SCL that was already low -- a different event
entirely, and not the one the requirement is about. Three checks on one run
reported their activation as never occurring for exactly this reason, while
their own activation text said "a falling edge occurs".

WHEN AN OUTPUT IS PART OF THE TRIGGER. `inputs` takes input ports only, because
a later stage decides it from the stimulus steps alone with no model. If the
activation also depends on an output, put that in `opens_on`:

  "an output-enable is driven low"    -> opens_on [{"scl_oen": 0}, {"sda_oen": 0}]
  "after the controller releases SCL" -> opens_on [{"scl_oen": 1}]

Putting it in `inputs` is rejected, and leaving it out silently changes what the
requirement is about.

EXPECTATION. What must hold of those outputs when the activation occurs, in one
clause. If `observable` is empty, still state the expectation in terms of the
internal thing -- it records what could not be checked.

AND SAY HOW THE ACTIVATION IS REACHED, in `activated_via`.

Some requirements apply whenever their inputs are driven a certain way. Others
apply only once something has ALREADY HAPPENED -- a command was accepted, a
sequence is running, a condition was detected. Those are different answers and
only you can tell them apart.

  DRIVEN: one entry, `through_req` empty, carrying the inputs that drive it.
    {"through_req": "", "activation": {"text": "...", "inputs": {"cmd": 4}}}

  REACHED: one entry per prerequisite, each naming the requirement whose
  behaviour puts the design there, plus `when` and `shows`.
    {"through_req": "REQ-0096",
     "activation": {"text": "the FSM has entered the READ sequence"},
     "when": "the command is accepted from idle",
     "shows": "scl_oen or sda_oen departs the released idle pair and sda_oen
               stays 1 until cmd_ack"}
  `shows` is how a trace of DECLARED PORTS reveals the hop has fired. Without
  it the check author knows which requirement to thank and still cannot open a
  window on it, so it opens on whatever is easy to see instead.

  NEITHER: if it needs a prior event you cannot name, leave `activated_via`
  empty and say so in `unreachable_reason`. That is a real answer and it is
  worth more than a hop you invented.

PINNING AN INPUT TO THE VALUE IT RESTS AT IS NOT DRIVING ANYTHING. If the only
inputs you would name are the ones saying nothing unusual is happening -- reset
inactive, core enabled -- then this requirement is NOT driven by its inputs, and
saying it is hides the fact that something must have happened first.

WHEN ANY OF SEVERAL VALUES OPENS THE WINDOW, WRITE THEM ALL AS A LIST.
`inputs` maps a port to the value that must hold, so naming two ports means
BOTH -- but a port may take a LIST, and that means ANY OF THESE:

  {"cmd": ["I2C_CMD_START", "I2C_CMD_STOP", "I2C_CMD_READ", "I2C_CMD_WRITE"],
   "ena": 1}

opens on any of the four commands, with `ena` 1 in every case. Requirements
about "a supported command", "any command sequence", "a START or STOP
condition" are exactly this shape. Do NOT leave `inputs` empty and put the
alternatives in `text`: prose is not something a check can open a window on,
and a requirement whose trigger lives only in `text` reads as unconditional.

A DISJUNCTION ACROSS DIFFERENT PORTS is a different thing and does not go here.
"nReset is low OR rst is high" names two ports, and no per-port list can say
it. Put that in `opens_on`, which is a list of alternatives and may name any
declared port: [{"nReset": 0}, {"rst": 1}].

Reply with ONE JSON object and nothing else:

{
  "reasoning": "...",
  "normalized": [
    {
      "activation": {
        "text": "a START command is issued while the core is enabled",
        "inputs": {"cmd": "I2C_CMD_START", "ena": 1},
        "opens_on": [],
        "until": [{"cmd_ack": 1}],
        "aborts_on": [{"al": 1}, {"nReset": 0}]
      },
      "observable": ["cmd_ack", "busy"],
      "unobservable_reason": "",
      "expectation": "cmd_ack pulses high for exactly one clock and busy rises",
      "activated_via": [
        {"through_req": "", "activation": {"text": "a START command is issued", "inputs": {"cmd": "I2C_CMD_START", "ena": 1}}}
      ],
      "unreachable_reason": ""
    }
  ]
}
"""


def shared_prefix(contract_json: str, contract: dict, *,
                  system: str = "", note: str = "") -> str:
    """Byte-identical across every requirement of one node.

    `system` and `note` let the INDIRECT pass reuse the port lists under a
    different question. It needs its own prefix rather than a different item
    block: the default note ends "if the requirement is about one of those,
    `observable` is empty", which is the first pass's instruction and the
    exact opposite of what the second pass is asking.

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
        ("system", system or SYSTEM),
        ("contract_json", contract_json),
        ("output_ports", json.dumps(outputs, indent=2) + "\n\n" + (
            note or
            "These are the ONLY names `observable` may contain. Anything else "
            "named in the requirement is internal to the design; if the "
            "requirement is about one of those, `observable` is empty.")),
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



INDIRECT_SYSTEM = """\
A requirement has come back needing something the first pass could not give it:
a way to OBSERVE it at a port its own text does not name, or a way to REACH the
state its activation needs, or both. Before either is accepted as a hole in the
specification, you are asked the narrower questions the first pass could not.

THE ITEM BLOCK BELOW NAMES WHICH OF THE TWO IS BEING ASKED OF THIS REQUIREMENT.
Answer that one. Answering the other as well is not useful -- a requirement
already observable at a port does not need a route to one, and a route invented
for it will be discarded.

This is not a second chance to reach for the nearest port. It is a different
question, and it has a real answer more often than the first pass suggests: an
FSM state is not a port, but the requirements describing behaviour IN each state
name real ports, so the state is observable through what it makes those
requirements do.

TWO INDEPENDENT QUESTIONS, and a requirement may need either without the other.
Answer the one the item block asks for, or say plainly that you cannot.

OBSERVATION -- `observed_via`, a list of ALTERNATIVES, any one sufficient.
  port         a declared OUTPUT port, named by the OTHER requirement
  through_req  that requirement's uid
  when         the phase, edge or window in which a reading of that port is
               evidence about THIS requirement -- rather than about the other
               requirement's own behaviour, or about anything else the design
               happens to be doing at the same time. REQUIRED, and required on
               a DIRECT route too, where there is no other requirement to be
               told apart from: an unscoped route makes a check that watches
               the port everywhere and blames this requirement for whatever it
               sees. Restating the activation is a fine answer; empty is not
  shows        what the port does when this requirement HOLDS
  otherwise    what it does when it does NOT -- a SEPARATE FIELD, never a
               second clause inside `shows`

  BOTH CASES ARE REQUIRED, and a route carrying only one will be rejected.
  "busy is observable" is useless. `shows` "busy rises for a glitch at or above
  the filter depth" with `otherwise` "busy stays low for one narrower than it"
  is something a check can be written on; the first half alone passes any
  design that ever raises busy, including one with none of this behaviour.
  If nothing could contradict the requirement -- it restates its own antecedent,
  so no design could fail it -- put "no discrimination" in `otherwise` and it is
  recorded as a finding rather than made a check.

ACTIVATION -- `activated_via`, a list of PREREQUISITES, every one required.
  Give this only when the activation cannot be stated as input values. "cmd is
  WRITE and ena is 1" is drivable and needs nothing here. "while the FSM is in
  START_B" is not: something has to have put it there.

  through_req  the requirement whose behaviour puts the design in this state
  activation   what that requirement's own activation prescribes -- text, and
               inputs where they can be stated
  when         the condition under which that hop actually delivers the state.
               Not every firing of `through_req` need put you there.
  shows        HOW A TRACE OF DECLARED PORTS REVEALS that the hop has fired and
               the state now holds. Required. Without it the author is told
               which requirement to thank and still cannot open a window on it,
               so it opens on whatever is easy to see instead -- which is the
               single most common reason a check is later rejected.

  ONE HOP ONLY. Say what must have just happened, not the whole sequence back
  to reset. The chain is followed mechanically from the hops every requirement
  gives; a whole chain guessed here would invalidate everything after its first
  wrong link.

THIS IS THE LAST PASS. There is no third question and no later stage that asks
again: a requirement returning empty lists here ends with no check written for
it at all. So an empty answer is a FINDING ABOUT THE SPECIFICATION, not a way to
hand the question on, and it is only true of text that makes no behavioural
claim -- a port declaration, a list marker, a section heading, architectural
prose. If the requirement says the design DOES something, that something reaches
a port, and finding which is what this pass is for.

AN ABSENCE IS AN OBSERVATION. "the FSM stalls" is not unobservable: it shows as
cmd_ack NOT pulsing where it otherwise would, or scl_oen held where it otherwise
releases. That is what the two cases are for -- a delay, a non-event or a held
level fills `shows` or `otherwise` as well as a transition does. An internal
signal whose only effect is to POSTPONE a boundary event is routed by naming the
event it postpones and the requirement that would otherwise produce it.

What is still not acceptable is a port you cannot justify. A route reached for
because it was nearest produces a check that fails correct designs, and that is
the failure this whole pipeline exists to prevent. Name the port the effect
actually reaches, scope it with `when`, and fill both cases.

Reply with ONE JSON object and nothing else:

{
  "reasoning": "...",
  "normalized": [
    {
      "req_uid": "REQ-0031",
      "observed_via": [
        {
          "port": "busy",
          "through_req": "REQ-0007",
          "when": "after a START-shaped edge on sda_i while scl_i is high",
          "shows": "busy rises for a glitch at or above the filter depth",
          "otherwise": "busy stays low for one narrower than it"
        }
      ],
      "activated_via": [
        {
          "through_req": "REQ-0012",
          "activation": {"text": "a START command is issued", "inputs": {"cmd": 1}},
          "when": "the command is accepted from idle, i.e. presented while clk_en allows the FSM to advance",
          "shows": "sda_oen falls to 0 while scl_oen is still 1 -- the START-condition signature at the boundary",
          "otherwise": "sda_oen holds at 1, or falls only after scl_oen has already gone low"
        }
      ]
    }
  ]
}

With no route, that is:

{"reasoning": "...", "normalized": [{"req_uid": "REQ-0031", "observed_via": [], "activated_via": []}]}
"""


def indirect_prefix(contract_json: str, contract: dict,
                    others: list[NormalizedRequirement]) -> str:
    """The cached head for the indirect pass: ports, system text, and the SET.

    `the_other_requirements` BELONGS IN THE PREFIX, and putting it in the item
    block was measured costing 7x. Every call needs the whole set -- that is
    what the pass is for -- and the set is the same for all of them, so it is
    the largest cacheable thing this stage has. It was in the item block only
    because each call filtered out the requirement's own entry, which made a
    ~48 KB block differ on every call for the sake of one row.

    Measured on a2-i2c before the fix: 31 calls, 549 KB of input, 11.9% cached,
    with a common prefix of 16,262 of 64,423 characters -- 25%. `normalize`
    beside it, whose set-free prompt caches properly, ran 84.7%.

    The self entry stays IN, and the prompt says to ignore it. A row a model is
    told to skip costs a few tokens once; a prefix that differs per call costs
    the whole prefix every time.
    """
    return shared_block(
        ("system", INDIRECT_SYSTEM),
        ("contract_json", contract_json),
        ("output_ports", json.dumps([
            {"name": p.get("name"), "width": p.get("width", 1)}
            for p in (contract.get("io") or [])
            if p.get("dir") == "output" and p.get("name")
        ], indent=2) + "\n\nA route may name ANY of these -- the point of this "
           "pass is that the port belongs to another requirement, not to this "
           "one. `observed_via[].port` must be one of them."),
        ("input_ports", json.dumps([
            {"name": p.get("name"), "width": p.get("width", 1)}
            for p in (contract.get("io") or [])
            if p.get("dir") == "input" and p.get("name")
        ], indent=2)),
        ("the_other_requirements", json.dumps([
            {"req_uid": o.req_uid, "observable": o.observable,
             "activation": o.activation.model_dump(),
             "expectation": o.expectation}
            for o in others
        ], indent=2) + "\n\nYour own requirement is in this list. Ignore that "
           "entry: a requirement cannot be observed through itself, and naming "
           "it will be rejected."),
    )


#: What each requirement is being asked. In the ITEM block, never the prefix:
#: forking the system text per question would split a 64 KB cached head three
#: ways to say one sentence, and that head is 97% of the prompt.
_ASKS = {
    "observation": (
        "THE QUESTION FOR THIS REQUIREMENT: OBSERVATION ONLY.\n"
        "No declared output port shows this behaviour directly. Give "
        "`observed_via`. Leave `activated_via` empty -- its activation is "
        "drivable, so there is nothing to reach."),
    "activation": (
        "THE QUESTION FOR THIS REQUIREMENT: ACTIVATION ONLY.\n"
        "This requirement is ALREADY OBSERVABLE at the port(s) in its reading "
        "below -- do not look for another one, and do not return "
        "`observed_via`. What it lacks is a way to REACH the state its "
        "activation names. Give `activated_via`: one hop, the requirement whose "
        "behaviour puts the design in that state."),
    "both": (
        "THE QUESTION FOR THIS REQUIREMENT: BOTH.\n"
        "No port shows it directly AND its activation is not drivable. Give "
        "`observed_via` and `activated_via`. They are independent: finding one "
        "and not the other is a real answer, and more useful than inventing "
        "the missing half."),
}


def build_indirect_prompt(
    requirement: dict,
    shape: NormalizedRequirement,
    others: list[NormalizedRequirement],
    contract_json: str,
    contract: dict,
    issues: list[Issue] | None = None,
    previous: str | None = None,
    ask: str = "observation",
) -> str:
    """The requirement, its first-pass reading, and WHICH question it is asked.

    `others` carries `req_uid`, `observable`, `activation` and `expectation`
    only -- the vocabulary needed to name a route, and nothing that would let
    this become a second attempt at the first pass's job.

    `ask` exists because the two indirections are independent and the pass now
    admits requirements that need only the second. Sending an already-observable
    requirement the blind requirement's prompt invites it to invent a route it
    does not need, and `observable` is the field every downstream stage reads.
    """
    return compose(
        indirect_prefix(contract_json, contract, others),
        "\n\n".join([
            _ASKS.get(ask, _ASKS["observation"]),
            json_block("requirement", requirement),
            # The first pass's reading, INCLUDING its `unobservable_reason`.
            # That field is where it recorded whether it merely could not name a
            # port or believed nothing at the interface distinguishes this at
            # all -- two different claims, and the second is a much stronger
            # reason to come back empty here.
            json_block("its_first_pass_reading", shape.model_dump()),
        ]),
        issues=issues,
        previous=previous,
    )


#: What a `shows` says when the requirement genuinely has no second case: an
#: EXPLICIT answer, never an empty field. Silence cannot be told apart from not
#: having answered, and the difference decides whether this is a finding about
#: the specification or a defect in the pass.
NO_DISCRIMINATION = "no discrimination"


def declines_discrimination(shows: str) -> bool:
    """Is this an explicit "there is no second case"?

    THE ESCAPE HATCH, and it has to exist. A tautology has no contrasting case
    -- REQ-0005 is "releasing scl_oen high causes the module to release the
    line", whose port is its own antecedent -- so a gate that DEMANDS a
    discrimination from every requirement gets a fabricated one, because a model
    asked for something impossible complies rather than refuses. An invented
    discrimination is worse than an absent one: it launders a check that cannot
    fail into one that looks checkable, and vacuity only catches it three stages
    later.

    Same shape as `observable` + `unobservable_reason`, which this file already
    treats as "empty WITH a reason passes, empty WITHOUT one does not".
    """
    return NO_DISCRIMINATION in (shows or "").strip().lower()


#: THE CONCESSION. An author that writes `unobservable_reason` while SAYING in
#: the same sentence where the effect can be seen has not judged the requirement
#: unobservable -- it has declined to write the route. Measured on h2-i2c's
#: Haiku normalization: 18 of 41 unobservable requirements (44%) concede a route
#: in their own reason. "...which should be visible through the timing of
#: command completion (cmd_ack)"; "...manifests through delayed FSM advancement
#: visible only through extended command timing".
#:
#: WHY THIS IS NOT A MODEL-STRENGTH PROBLEM, which is what it looks like. A
#: model that did not KNOW the route would not name the port and the mechanism.
#: These name both. What makes `unobservable_reason` attractive is that it is
#: CHEAP: `observed_via`'s `shows` demands a two-case discrimination -- how the
#: port looks when the requirement holds and when it does not -- and one free
#: sentence buys an exit from that. The prompt has warned against this since it
#: was written; the warning was not enough, and a gate is.
#:
#: THE FIX IS NOT A WEAKER `shows`. A route that cannot tell holds from
#: does-not-hold is not a route, and dropping the demand would launder exactly
#: the checks vacuity catches three stages later. The fix is to close the cheap
#: exit and hand the author back its own sentence.
#:
#: TIGHT ON PURPOSE. A concession has two parts -- an assertion that the effect
#: IS seen, and a preposition saying WHERE -- and neither alone is one. The
#: loose version of this predicate matched "is NOT directly observable at
#: declared output ports", which is the honest answer, so a negation anywhere in
#: the preceding clause disqualifies the match.
_CONCEDES_ROUTE = re.compile(
    r"\b(?:should\s+be|would\s+be|will\s+be|is|are|becomes?|remains?)\s+"
    r"(?:(?:indirectly|directly|only|still|clearly|ultimately|readily)\s+){0,2}"
    r"(?:visible|observable|observed|detectable|apparent)\s+"
    r"(?:through|via|wherever|by\s+observing|as\s+)"
    r"|\bmanifests?\s+(?:through|via|as|in)\b"
    r"|\bshows?\s+up\s+(?:in|through|as)\b"
    r"|\bsurfaces?\s+(?:through|via|in)\b"
    r"|\breflected\s+(?:in|through|by)\b",
    re.I)
_NEGATION = re.compile(r"\b(?:not|never|cannot|can't|no|nothing|neither)\b", re.I)


def concedes_a_route(reason: str) -> str:
    """The span of `reason` that says where the effect IS seen, or "".

    Returns the conceding phrase itself so the gate can quote it back: an
    author reads its own words faster than it reads a rule.
    """
    text = reason or ""
    for m in _CONCEDES_ROUTE.finditer(text):
        if _NEGATION.search(text[max(0, m.start() - 40):m.start()]):
            continue
        return text[m.start():m.end() + 90].strip()
    return ""


#: THE DISCRIMINATION GATE IS GONE, DELIBERATELY.
#:
#: `shows_issue` demanded that a route's `shows` name two cases -- what the port
#: does when the requirement holds and when it does not -- or say the explicit
#: no-second-case phrase. It was a SUBSTRING TEST (" not ", "otherwise", "does
#: not", " and ") standing in for a semantic property, applied at normalisation,
#: four stages before anything can check whether the promise was kept.
#:
#: WHAT IT COST, all measured:
#:   - repair rounds, a meaningful share of the 0.45-0.66 mean
#:   - the port-deletion defect: the cheapest way to satisfy an objection about
#:     a port's `shows` is to drop that port from `observable`, which silently
#:     shrinks what the requirement is ever checked against, and the gate cannot
#:     tell the two repairs apart because it only sees the routes that remain
#:   - inconsistent verdicts on identical claims. REQ-0004 said "no
#:     discrimination" and was recorded as undecidable; REQ-0034 said "there is
#:     no case where this requirement does not hold" -- the same claim -- and
#:     passed as a real check, because the string contains " not ".
#:
#: WHAT IT BOUGHT: nothing that survives measurement. Discrimination is a
#: property of the CHECK against real traces, and it is measurable there
#: directly, with no prose in the loop. Asking an author to promise it in a
#: sentence at normalisation buys a promise.
#:
#: `declines_discrimination` and `NO_DISCRIMINATION` SURVIVE, because
#: `oracles_stage._declines` (:1435) reads them to assign a disposition -- a
#: requirement whose routes all decline is classified, not gated. That is
#: reporting, which is the right use of a lexical screen.
def route_shows_issue(path: str, shows: str, otherwise: str) -> Issue | None:
    """Two cases, decided by whether the second SLOT is filled.

    No inference from wording. `declines_discrimination` survives as the
    author's explicit opt-out -- a sentinel it writes deliberately, which is a
    different act from a gate guessing at its prose.
    """
    if not (shows or "").strip():
        return Issue(
            "error", path,
            "`shows` is empty: say what the port does when the requirement "
            "HOLDS. Without it the check author has a port and no reason to "
            "watch it.")
    if declines_discrimination(shows) or declines_discrimination(otherwise):
        return None
    if not (otherwise or "").strip():
        return Issue(
            "error", path,
            "`otherwise` is empty: say what the port does when the requirement "
            "does NOT hold. One case is not a discrimination -- a check written "
            "over it passes a design with none of this behaviour. If there "
            f"genuinely is no second case, because the requirement restates its "
            f"own antecedent and nothing could contradict it, put "
            f"{NO_DISCRIMINATION!r} in `otherwise` and it is recorded as a "
            f"finding rather than turned into a check.")
    return None


def when_issue(path: str, when: str) -> Issue | None:
    """`shows` says WHAT the port does; `when` says WHERE it is allowed to say it.

    A route with an empty `when` tells the check author to watch a port with no
    scope, and an unscoped observation cannot tell a response to this
    requirement apart from anything else the design does in the same window.
    That is not a hypothetical: REQ-0046's re-authored check watched
    `(busy, dout, al)` at every edge of its window, because all three of its
    routes arrived with `when` empty. It convicted the golden design twice over
    -- once on an unreset `dout` making its power-on capture (180 of 311 golden
    testpoints, with no glitch present at all), and once on a legitimate
    filtered response that merely shared the window. Restoring the two
    when-clauses the routes SHOULD have carried stopped both.

    The bar is deliberately low. Restating the activation is a fine answer --
    "whenever the activation holds" scopes the observation exactly as much as
    this requirement does. What is rejected is saying nothing, because an empty
    string is not that claim; it is the absence of one.
    """
    if when.strip():
        return None
    return Issue(
        "error", path,
        "`when` is empty. Say when this port carries THIS requirement's "
        "effect -- the phase, the edge, or the window in which a reading of it "
        "is evidence about this requirement and not about something else the "
        "design is doing at the same time. If the answer is simply the "
        "activation, say that; what cannot stand is no answer, because a check "
        "written over an unscoped route watches the port everywhere and blames "
        "this requirement for whatever it sees.")


def reach_shows_issue(path: str, shows: str) -> Issue | None:
    """A hop's `shows` must be RECOGNISABLE, not DISCRIMINATING.

    NOT `shows_issue`, and the difference is a category one rather than a
    stylistic one. An `observed_via` route's `shows` has to name two cases --
    what the port does when the requirement holds and what it does when it does
    not -- because that route exists to separate THIS requirement's effect from
    the effect of the requirement whose port it borrows. One case there is a
    check that passes a design with none of the behaviour.

    A hop's `shows` answers a different question: how does a trace of declared
    ports reveal that the prerequisite STATE has been reached, so a window can
    open on it. That is a recognition condition. There is no second case to
    state, because the hop is not asserting anything -- it is locating the rows
    the assertion applies to, and the assertion supplies its own discrimination.
    Demanding "and what it does when it does not" of a window-opener asks for a
    sentence that has no referent, and the measured cost of asking is a repair
    loop that spends its whole budget failing to produce one.

    So the bar is the same as `when_issue`'s and for the same reason: what is
    rejected is saying nothing, because an empty string is not a claim about
    the boundary; it is the absence of one, and an author holding it falls back
    to whatever it can see.
    """
    if shows.strip():
        return None
    return Issue(
        "error", path,
        "`shows` is empty. Say how a trace of DECLARED PORTS reveals that this "
        "hop has fired and the prerequisite state now holds -- the edge, the "
        "level, or the ordered pair of transitions a check can open its window "
        "on. Naming the requirement that gets you there is not enough on its "
        "own: an author that cannot recognise the state opens its window on "
        "whatever it can see instead, which is the single most common reason a "
        "check is later rejected as testing the wrong situation.")


def gate_indirect(out: NormalizeOutput, *, uid: str,
                  contract: dict, known: set[str]) -> list[Issue]:
    """A route has to be usable, or it is worse than no route at all.

    The one rejection that matters is `shows` naming a single case. A check
    written over "the port shows X" with nothing to contrast against passes any
    design that ever shows X, including one with none of the behaviour -- which
    is the vacuity failure, arriving one stage earlier than usual and harder to
    see because the route looks like progress.
    """
    issues: list[Issue] = []
    outputs = _ports(contract, "output")
    if not out.normalized:
        return [Issue("error", f"normalize.{uid}.indirect",
                      "no answer returned; give empty lists if there is no route")]
    norm = out.normalized[0]

    # THE CONCESSION, and THIS is the pass where it is a failure rather than a
    # deferral. The first pass may honestly answer "unobservable, though it
    # should show through the command timing" -- that hands the question here.
    # This pass was asked directly, with the sibling requirements in hand, so
    # naming where the effect shows and still returning no route is declining to
    # answer the only question it was asked.
    if not norm.observable and not norm.observed_via:
        conceded = concedes_a_route(norm.unobservable_reason)
        if conceded:
            issues.append(Issue(
                "error", f"normalize.{uid}.unobservable_reason",
                f"this pass exists to find the route, and your own reason says "
                f"where the effect is seen: {conceded!r} -- yet `observed_via` "
                f"is empty. Write it: the declared output port it reaches, the "
                f"`through_req` it travels through, `when` it shows there, "
                f"`shows` for how that port looks when the requirement holds "
                f"and `otherwise` for how it looks when it does not -- two "
                f"SEPARATE fields. An absence counts: a port that does not "
                f"move where it otherwise would is an observation. If you now "
                f"judge no "
                f"boundary effect exists at all, say that plainly instead; do "
                f"not describe an effect you are declining to name"))

    for i, route in enumerate(norm.observed_via):
        path = f"normalize.{uid}.observed_via[{i}]"
        if route.port not in outputs:
            issues.append(Issue("error", path,
                                f"{route.port!r} is not a declared output port "
                                f"(declared: {sorted(outputs)})"))
        if route.through_req and route.through_req not in known:
            issues.append(Issue("error", path,
                                f"{route.through_req!r} is not a requirement uid"))
        if route.through_req == uid:
            issues.append(Issue("error", path,
                                "a requirement cannot be observed through "
                                "itself -- that is the direct case, and the "
                                "first pass already said there is none"))
        bad = route_shows_issue(path, route.shows, route.otherwise)
        if bad is not None:
            issues.append(bad)
        bad = when_issue(path, route.when)
        if bad is not None:
            issues.append(bad)
    for i, hop in enumerate(norm.activated_via):
        path = f"normalize.{uid}.activated_via[{i}]"
        if hop.through_req and hop.through_req not in known:
            issues.append(Issue("error", path,
                                f"{hop.through_req!r} is not a requirement uid"))
        if hop.through_req == uid:
            issues.append(Issue("error", path,
                                "a requirement cannot be its own prerequisite"))
        #: AN EMPTY `through_req` IS THE DIRECT CASE, exactly as it is for a
        #: `Route`: the activation is driven, and `activation.inputs` are the
        #: values that drive it. There is no hop to recognise, so `when` and
        #: `shows` do not apply -- what must be there instead is the inputs.
        if not hop.through_req:
            if not (hop.activation.inputs or hop.activation.text.strip()):
                issues.append(Issue(
                    "error", path,
                    "a hop with no `through_req` is the DIRECT case and must "
                    "say what drives the activation: give "
                    "`activation.inputs`, or `activation.text` if the "
                    "requirement holds at all times."))
            continue
        #: The pointer-is-not-a-route checks, for a hop that names one. `when`
        #: is shared with `observed_via` verbatim -- an unscoped hop is
        #: unscoped the same way. `shows` is NOT: see `reach_shows_issue`.
        bad = reach_shows_issue(path, hop.shows)
        if bad is not None:
            issues.append(bad)
        bad = when_issue(path, hop.when)
        if bad is not None:
            issues.append(bad)
    return issues


#: The direct pass's only explanation of `observed_via` -- WHAT it is asking
#: for and WHAT SHAPE the answer takes -- repeated verbatim at both points
#: where a model can reach here without ever having seen it. `INDIRECT_SYSTEM`
#: carries a worked example; the direct pass's own `SYSTEM` text
#: (`shared_prefix`) does not, even though `gate_one` below demands the field
#: -- the check was added to the base case without the explanation following
#: it.
#:
#: Measured live, or1200_ctrl REQ-0001: told only the task prose (below) with
#: no shape shown, round 1 guessed a dict keyed by port name -- a defensible
#: reading of that sentence alone. The parse failure it produced
#: short-circuits `gate_one` to the raw pydantic error (`observed_via` must be
#: a list) before line ~1052 ever runs, so round 2 saw a DIFFERENT, narrower
#: message than round 1 did -- the task sentence was gone, not just the shape
#: -- and, with nothing to imitate, emptied the field back to the base case,
#: which reproduces round 0's error and round 3 would see the identical
#: message round 1 did. Two wrong shapes trading places, not a near-miss one
#: round away. Both pieces are carried at both trigger points now, so a round
#: reached through either path sees the same complete explanation.
_OBSERVED_VIA_TASK = (
    "Give one route naming that port, leaving `through_req` empty. Say in "
    "`shows` what the port does when this requirement holds and what it does "
    "when it does not, and say in `when` the phase, edge or window in which a "
    "reading of that port is evidence about THIS requirement rather than about "
    "something else the design is doing at the same time. If the answer is "
    "simply the activation, say that -- what cannot stand is leaving `when` "
    "empty, because a check written over an unscoped route watches the port "
    "everywhere and blames this requirement for whatever it sees."
)
_OBSERVED_VIA_SHAPE = (
    "`observed_via` is a LIST of objects, one per route -- not a dict keyed by "
    "port name. Each entry:\n"
    '  {"port": <output port>, "through_req": "", '
    '"when": <when this port carries this requirement\'s effect>, '
    '"shows": <what the port does when this requirement HOLDS>, '
    '"otherwise": <what it does when it does NOT>}\n'
    "`otherwise` is a SEPARATE FIELD, not a second clause inside `shows`. One "
    "case is not a discrimination: a check written over \"the port shows X\" "
    "passes any design that ever shows X, including one with none of this "
    "behaviour. If nothing could contradict the requirement -- it restates its "
    "own antecedent, so no design could fail it -- put \"no discrimination\" "
    "in `otherwise` and it is recorded as a finding rather than made a check.\n"
    "Example:\n"
    '  [{"port": "busy", "through_req": "", '
    '"when": "after a START-shaped edge on sda_i while scl_i is high", '
    '"shows": "busy rises for a glitch at or above the filter depth", '
    '"otherwise": "busy stays low for one narrower than it"}]'
)



#: THE ACTIVATION HALF, asked of every requirement in the same breath as
#: `observed_via` and for the same reason -- see `NormalizedRequirement.
#: activated_via`. An empty `through_req` is the direct case, which is what
#: makes a selector unnecessary: "drivable" is an answer the model gives rather
#: than a property the harness infers from the shape of `inputs`.
_ACTIVATED_VIA_TASK = (
    "AND SAY HOW THE ACTIVATION IS REACHED.\n"
    "Some requirements apply whenever their inputs are driven a certain "
    "way. Others apply only once something has ALREADY HAPPENED -- a "
    "command was accepted, a sequence is running, a condition was "
    "detected. Those two need different answers and only you can tell "
    "them apart.\n"
    "  DRIVEN: give ONE entry with `through_req` empty and the inputs "
    "that drive it. Pinning an input to the value it rests at almost "
    "always is not driving anything -- if the only inputs you would name "
    "are the ones saying nothing unusual is happening, it is NOT driven.\n"
    "  REACHED: one entry per prerequisite, each naming the requirement "
    "whose behaviour puts the design there, plus `when` and `shows`.\n"
    "  NEITHER: if it needs a prior event you cannot name, leave "
    "`activated_via` empty and say so in `unreachable_reason`. That is a "
    "real answer and it is better than a hop you invented."
)
_ACTIVATED_VIA_SHAPE = (
    "`activated_via` is a LIST of objects. Each entry:\n"
    '  {"through_req": <uid, or "" for the driven case>, '
    '"activation": {"text": <what must hold>, "inputs": {<port>: <value>; '
    'a LIST of values means ANY of them}}, '
    '"when": <when that hop delivers the state>, '
    '"shows": <how declared ports reveal the hop has fired>}\n'
    "Examples:\n"
    '  driven:  {"through_req": "", "activation": {"text": "a WRITE '
    'command is presented", "inputs": {"cmd": 4}}}\n'
    '  reached: {"through_req": "REQ-0096", "activation": {"text": '
    '"the FSM has entered the READ sequence"}, "when": "the command '
    'is accepted from idle", "shows": "scl_oen or sda_oen departs '
    'the released idle pair and sda_oen stays 1 until cmd_ack"}'
)


def parse_response(text: str) -> NormalizeOutput:
    try:
        obj = extract_json_object(strip_markdown_code_fences(text))
        out = NormalizeOutput.model_validate(obj)
        # BOTH fields carry defaults, so ANY object validates -- including a
        # fragment `extract_json_object` scraped out of the middle of a broken
        # response. The result is an empty `NormalizeOutput` that is
        # indistinguishable from a model which answered nothing, and `gate_one`
        # then complains about CONTENT ("observable at [...] but no route
        # given") when the response was never read at all. The model is asked
        # to fix a field it did supply.
        #
        # Measured live, c1-i2c REQ-0048 r1: the model wrote `until
        # [{"busy":0}]` inside its `reasoning` STRING with the inner quotes
        # unescaped, which ends the JSON string early and breaks the document.
        # Recovery found the balanced `{"busy":0}` fragment, validated it to an
        # empty output, and all four rounds were spent on a content complaint
        # about a response whose only defect was one unescaped quote.
        if not out.normalized and not out.reasoning.strip():
            keys = sorted(obj)[:8] if isinstance(obj, dict) else []
            raise ValueError(
                "the response is not valid JSON, and the object recovered from "
                f"it carries neither `normalized` nor `reasoning` (its keys "
                f"were {keys}). Return ONE JSON object with those two "
                "top-level fields, and ESCAPE every quote that appears inside "
                'a string value -- write \\" for a quote you want in the text, '
                "or describe the shape in prose without quoting JSON at all.")
        return out
    except Exception as exc:  # noqa: BLE001
        detail = f"{PARSE_ERROR}{exc}"
        # Otherwise a shape mistake on THIS field loses its only explanation
        # the moment it stops parsing -- see `_OBSERVED_VIA_TASK`/`_SHAPE`
        # above. Both pieces, matching what the base "no route given" case
        # in `gate_one` says, not a narrower message this path invents.
        if "observed_via" in str(exc):
            detail += (f"\n\n{_OBSERVED_VIA_TASK}\n\n{_OBSERVED_VIA_SHAPE}"
                       f"\n\n{_ACTIVATED_VIA_TASK}\n\n{_ACTIVATED_VIA_SHAPE}")
        return NormalizeOutput(reasoning=detail)


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
    # THE CLOCK IS PINNED AND EVERY ROW IS ALREADY AN EDGE. Conditioning on it
    # cannot mean anything: `clk` is constant across the trace the oracle sees,
    # so `{"clk": "rise"}` matches NO row and `{"clk": 1}` matches every one.
    #
    # Not hypothetical -- it appeared the first time the edge vocabulary was
    # live. Three of forty activations came back `opens_on [{"clk": "rise"}]`,
    # and `edges(trace, "clk", "rise")` returns 0 of 105 rows, so those windows
    # could never open. Giving the author a way to name an edge gave it a way
    # to name the clock's, which reads natural and is empty.
    clock = str(((contract.get("clocking") or {}).get("clock") or {}).get("name") or "")
    # Both directions: a window closes on what the DESIGN does, and a
    # requirement can be activated by an output. Only `inputs` is one-sided.
    ports = {**inputs, **outputs}

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

    # NOT GATED HERE, AND THAT IS THE POINT. A first-pass answer reading
    # "unobservable, though the effect should show through the command timing"
    # is DEFERRING to the indirect pass, which is the stage built to answer it:
    # `unobservable` is literally the ticket into `blind`, and the second pass
    # re-asks with the sibling pool in hand that this one does not have.
    #
    # Measured on h2-i2c: of the 18 direct-pass answers that conceded a route,
    # the indirect pass recovered 15 (83%) with a real port AND route --
    # REQ-0042 through `scl_oen`, REQ-0084 through `cmd_ack` and `scl_oen` over
    # three routes. Refusing the concession here forced a worse route out of the
    # pass with LESS information and, because `unobservable` is `not
    # observable`, dropped the requirement from `blind` so it never got the
    # better-informed look at all. The check lives in `gate_indirect`, where the
    # author was asked the question directly and a concession is a refusal to
    # answer it.

    # THE ROUTE IS THE BASE CASE, so the first pass gates it too. Until now the
    # discrimination rule lived only in `gate_indirect`, which runs over the
    # blind subset -- so a DIRECTLY observable requirement was asked for `shows`
    # by the prompt and never held to it, which is the temporal-operator lesson
    # exactly: offered, and taken by 1 of 182.
    #
    # `through_req` is empty here by construction: the first pass sees one
    # requirement and cannot know another's uid, so a borrowed port is the
    # second pass's answer and naming one here is a claim it cannot support.
    if norm.observable:
        if not norm.observed_via:
            issues.append(Issue(
                "error", f"normalize.{uid}.observed_via",
                f"observable at {sorted(norm.observable)} but no route given. "
                f"{_OBSERVED_VIA_TASK}\n\n{_OBSERVED_VIA_SHAPE}\n\n"
                f"{_ACTIVATED_VIA_TASK}\n\n{_ACTIVATED_VIA_SHAPE}"))
        for i, route in enumerate(norm.observed_via):
            path = f"normalize.{uid}.observed_via[{i}]"
            if route.through_req:
                issues.append(Issue(
                    "error", path,
                    f"names {route.through_req!r}; this pass sees one "
                    f"requirement and cannot know another's uid, so leave "
                    f"`through_req` empty and name this requirement's own port"))
            if route.port and route.port not in norm.observable:
                issues.append(Issue(
                    "error", path,
                    f"{route.port!r} is not among the ports this requirement "
                    f"is observable at ({sorted(norm.observable)})"))
            bad = route_shows_issue(path, route.shows, route.otherwise)
            if bad is not None:
                issues.append(bad)
            bad = when_issue(path, route.when)
            if bad is not None:
                issues.append(bad)

    for name, value in (norm.activation.inputs or {}).items():
        path = f"normalize.{uid}.activation.inputs"
        if clock and name == clock:
            issues.append(Issue("error", path,
                                f"{name!r} is the clock; every row is already "
                                f"one of its edges, so this constrains nothing"))
            continue
        if name not in inputs:
            issues.append(Issue("error", path,
                                f"{name!r} is not a declared input port"))
            continue
        # RESOLVE THROUGH THE PORT'S ENCODING, when it declares one. Absent a
        # table this is `int(value)` and the same width check as before, so
        # every design without a shared constants header behaves as it did.
        #
        # `resolve_any` takes a scalar OR a value-set and always hands back a
        # tuple, so the width check below runs over every alternative and a set
        # with one bad member is rejected whole -- dropping the bad one would
        # narrow the window without saying so.
        vals, why = encoding.resolve_any(name, value, contract)
        if vals is None:
            issues.append(Issue("error", path, why))
            continue
        too_wide = [v for v in vals if not (0 <= v < (1 << inputs[name]))]
        if too_wide:
            issues.append(Issue("error", path,
                                f"{name}={', '.join(str(v) for v in too_wide)} "
                                f"does not fit {inputs[name]} bit(s)"))
            continue
        # NO NUDGE HERE FOR A NUMBER THAT HAPPENS TO BE RIGHT. `Severity` is
        # error|warning, and a warning on every correct numeric value would be
        # 45 of them on c1-i2c -- enough to bury the findings that mean
        # something. The prompt asks for the symbol; the gate only catches what
        # is wrong. The 122 normalizations predating the table stay valid.

    # `opens_on`, `until` and `aborts_on` may name ANY declared port, unlike
    # `inputs`. A window closes on what the design does -- "until cmd_ack" --
    # and a requirement can be activated by an output. Same width and integer
    # checks, and `aborts_on` earns them for the same reason the other two do:
    # an abort on an undeclared port is a window that can never be discarded,
    # which is exactly as silent as one that can never close.
    for field in ("opens_on", "until", "aborts_on"):
        alternatives = getattr(norm.activation, field) or []
        for alt in alternatives:
            for name, value in (alt or {}).items():
                path = f"normalize.{uid}.activation.{field}"
                if clock and name == clock:
                    issues.append(Issue(
                        "error", path,
                        f"{name!r} is the clock, and every row of the trace is "
                        f"already one of its edges -- an edge on it matches no "
                        f"row and a level matches every row. Name what the "
                        f"requirement is actually triggered by."))
                    continue
                width = ports.get(name)
                if width is None:
                    issues.append(Issue("error", path,
                                        f"{name!r} is not a declared port"))
                    continue
                # AN EDGE IS NOT A LEVEL, and the schema could only say
                # level. Measured on a2-i2c: 28 of 105 requirements name an
                # edge or transition in their own text, and three checks
                # reported the activation as never occurring because
                # "scl_i falls WHILE scl_oen is released" had been written
                # `{scl_i: 0, scl_oen: 1}` -- a conjunction of levels, which
                # also fires when scl_oen rises over an already-low scl_i.
                if isinstance(value, str):
                    table, _complete = encoding.encoding_for(contract, name)
                    if value in table:
                        # A SYMBOL, not an edge. These fields already carried
                        # `int | str` for edge words, so the two share a slot
                        # and the edge words win -- a port whose encoding
                        # defined a symbol called "rise" would be pathological.
                        continue
                    if value not in _EDGE_WORDS:
                        legal = sorted(_EDGE_WORDS) + sorted(table)
                        issues.append(Issue(
                            "error", path,
                            f"{name}={value!r} is neither a value nor one of "
                            f"{legal}"))
                    elif value in ("rise", "fall") and width > 1:
                        # SVA's `$rose`/`$fell` are defined on the LSB;
                        # `temporal.edges` reads them as increased/decreased.
                        # Identical on a 1-bit port -- which is every port these
                        # requirements name an edge of -- and different on a
                        # wider one, so say which was meant.
                        issues.append(Issue(
                            "warning", path,
                            f"{name} is {width} bits, so {value!r} means the "
                            f"value increased or decreased, not that a bit "
                            f"toggled; 'change' is usually what is meant"))
                    continue
                try:
                    as_int = int(value)
                except Exception:  # noqa: BLE001
                    issues.append(Issue("error", path,
                                        f"{name}={value!r} is not an integer"))
                    continue
                if not (0 <= as_int < (1 << width)):
                    issues.append(Issue("error", path,
                                        f"{name}={as_int} does not fit "
                                        f"{width} bit(s)"))

    # A WINDOW IN THE PROSE AND AN INSTANT IN THE SCHEMA. Reported, not
    # rejected: the phrasing is heuristic, and this repo has twice paid for a
    # screen that blocked before its false-positive rate was known -- gate 1's
    # blanket "met" discarded 30 requirements, and correspondence rejected 56 of
    # 70 on a miscalibration.
    #
    # What it catches is the largest measured defect here: 63% of a2-i2c's
    # requirements name a span in their own text, and every one of them was
    # normalised to the instant its activation began. The two symptoms that
    # produces -- over-strict and vacuous checks -- have the same profile, 79%
    # and 83% windowed-text-with-one-row-activation against 58% of the rest.
    if not norm.activation.windowed and _names_a_window(
            f"{norm.activation.text} {norm.expectation}"):
        issues.append(Issue(
            "warning", f"normalize.{uid}.activation.until",
            "the text names a span ('during', 'while', 'the ... sequence') but "
            "no close condition is given, so every check over this requirement "
            "can only read the instant the activation began"))

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
    max_repairs: int = 5,
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
        # A REQUIREMENT WHOSE NORMALIZED FORM NEVER PASSED ITS OWN GATE DOES
        # NOT SHIP. Until this line existed, `merged` took `result.output`
        # regardless of `result.ok`, so a form the gate had rejected reached S2,
        # the stimulus and the check author identically to one it had accepted.
        # Measured on c1-i2c: 15 of 122, every one of them carrying "observable
        # at [...] but no route given" or a `shows` that names only one case --
        # which hands the check author a port it may assert ANYTHING about.
        # REQ-0094 is the worked case and it did exactly that.
        #
        # NOT A QUALITY CLAIM, and the measurement forbids making one: 39% of
        # the checks from flagged requirements are refuted by the known-good
        # control against 39% from clean ones. This is a consistency fix. The
        # pipeline stops acting on a claim its own gate rejected.
        #
        # AND THE BUDGET IS NOT WHAT IS BINDING. All 15 spent every repair
        # round -- r0 through r3, the whole budget -- and still failed, so they
        # are not near-misses that one more round would rescue. Raising
        # `max_repairs` is not the fix and was measured before this landed.
        if not result.ok:
            continue
        for norm in result.output.normalized[:1]:
            # `req_uid` is the harness's to stamp, never the model's -- the same
            # treatment `run_judge` gives a verdict (`judge.py:796-804`). A model
            # that mislabelled one would misroute the whole requirement.
            merged.append(norm.model_copy(
                update={"req_uid": str(req.get("uid") or "")}))
    return merged, results



#: How far to follow `activated_via` hops before giving up. A reference model's
#: state machine is shallow; a chain longer than this is more likely a cycle or
#: a misreading than a real prerequisite sequence.
REACH_DEPTH = 6


def reaching(uid: str, by_uid: dict[str, NormalizedRequirement],
             *, depth: int = REACH_DEPTH) -> tuple[list[Reach], str]:
    """The full prerequisite chain for one requirement. `(chain, why_not)`.

    NORMALISATION EMITS LOCAL EDGES; THIS COMPUTES THE CLOSURE. Each requirement
    answers only "what must have just happened", which is a judgement it can
    make against the merged set. Following those hops until every prerequisite
    is `input_only` is a graph walk, and a graph walk is not a thing to ask a
    model for -- one wrong link would invalidate everything after it.

    Ordered nearest-first, then reversed so the caller reads it as a SEQUENCE to
    drive: the deepest prerequisite happens first.

    A CYCLE IS A SPECIFICATION FINDING, not a hang. REQ-A reachable only via
    REQ-B reachable only via REQ-A says the two describe each other and neither
    says how to get in, which is exactly the kind of hole this pipeline exists
    to surface rather than iterate on.
    """
    chain: list[Reach] = []
    seen = {uid}
    # `(hop, who named it)`, so a cycle can name the EDGE that closes it rather
    # than the requirement the walk happened to start from.
    frontier = [(h, uid) for h in
                (by_uid[uid].activated_via if uid in by_uid else [])]
    for _ in range(max(1, depth)):
        if not frontier:
            return list(reversed(chain)), ""
        nxt: list[tuple[Reach, str]] = []
        for hop, came_from in frontier:
            if hop.through_req in seen:
                return [], (
                    f"the prerequisite chain closes on itself: {came_from} is "
                    f"reachable only through {hop.through_req}, which is "
                    f"already in the chain from {uid}. The requirements "
                    f"describe each other and neither says how to enter the "
                    f"state")
            seen.add(hop.through_req)
            chain.append(hop)
            nxt += [(h, hop.through_req) for h in
                    (by_uid[hop.through_req].activated_via
                     if hop.through_req in by_uid else [])]
        frontier = nxt
    return [], (f"{uid} needs more than {depth} prerequisite hops, which is "
                f"more likely a misreading than a real sequence")



def resolve_indirect(
    *,
    normalized: list[NormalizedRequirement],
    requirements: list[dict],
    contract_json: str,
    contract: dict,
    port: ModelPort,
    max_repairs: int = 5,
    fanout: bool = True,
) -> tuple[list[NormalizedRequirement], list[StageResult[NormalizeOutput]]]:
    """Ask the blind requirements the second question. Returns the merged set.

    EVERY UNOBSERVABLE REQUIREMENT COMES THROUGH HERE. Not a subset, and not
    only the ones that look promising: `UNOBSERVABLE` is a claim that no port
    shows the behaviour, and this pipeline has already measured that claim wrong
    at scale -- normalisation called 27 of 77 requirements unobservable by
    reading each one's MECHANISM rather than its effect, and 10 of the 27
    already had working checks against real output ports.

    A SECOND PASS, NOT A CHANGE TO THE FAN-OUT. `run_normalize_fanout` rests on
    an assumption it states -- "Requirements do not constrain each other... Each
    requirement's activation and observable are independent of every other's" --
    which is true for the direct case and false for exactly this one. So the
    fan-out keeps its assumption where it holds, and this runs after the merge,
    over the blind subset only, with the merged set as its evidence.

    AND THIS IS WHY IT BELONGS AT NORMALISATION rather than at the oracle stage.
    A corrected `observable` propagates to S2, S3, stimulus and [O]: every
    downstream stage plans against the route. Repairing it later would leave the
    testplan built from the claim that was wrong.
    """
    # ENTRY IS NOT GATED ON OBSERVABILITY ALONE, and it used to be. The two
    # indirections are independent -- `observed_via` makes a requirement
    # CHECKABLE, `activated_via` makes it STAGEABLE -- but `blind` selected on
    # `unobservable`, so the "observable but unreachable" case could never be
    # filled. Measured on a2-i2c: 28 requirements got `observed_via`, 18 got
    # `activated_via`, and `activated_via` WITHOUT `observed_via` was zero --
    # not a property of the design, an artefact of who was let in.
    def _ask(n: NormalizedRequirement) -> str:
        if n.unobservable:
            return "both" if n.unreachable else "observation"
        return "activation"

    #: BOTH LEGS ARE NOW MODEL-DECLARED. `unobservable` was always a claim the
    #: model makes -- an empty `observable` plus a reason. `unreachable` is its
    #: mirror, and replaces `activation.state_dependent`, which inferred the
    #: same thing from the shape of `inputs` and was wrong for 76 of 110
    #: requirements. See `activated_via`.
    blind = [n for n in normalized if n.unobservable or n.unreachable]
    if not blind:
        return list(normalized), []
    asks = {n.req_uid: _ask(n) for n in blind}
    by_uid = {str(r.get("uid") or ""): r for r in requirements}
    known = {n.req_uid for n in normalized}

    def one(shape: NormalizedRequirement) -> StageResult[NormalizeOutput]:
        return run_stage(
            stage=f"{STAGE}_indirect_{shape.req_uid}",
            port=port,
            build_prompt=lambda issues, previous: build_indirect_prompt(
                by_uid.get(shape.req_uid, {}), shape, normalized,
                contract_json, contract, issues, previous,
                ask=asks[shape.req_uid]),
            parse=parse_response,
            gate=lambda out: gate_indirect(
                out, uid=shape.req_uid, contract=contract, known=known),
            max_repairs=max_repairs,
        )

    results = run_fanout(blind, one) if fanout else [one(b) for b in blind]
    routed: dict[str, NormalizedRequirement] = {}
    for shape, result in zip(blind, results):
        if not result.ok or not result.output.normalized:
            continue
        answer = result.output.normalized[0]
        update: dict = {}
        # AN OBSERVATION ROUTE IS ONLY APPLIED TO A REQUIREMENT THAT LACKED ONE.
        # `observable` is the field every downstream stage reads, and a
        # requirement asked only the activation question is already decidable at
        # a port of its own -- a route returned for it anyway is the model
        # answering a question it was told not to, and overwriting a good claim
        # with it would be strictly worse than ignoring it.
        if shape.unobservable and answer.observed_via:
            # `observable` now holds the ports it is decidable at BY ANY ROUTE,
            # so every downstream consumer keeps reading one field. The reason
            # goes, because it is no longer true.
            update["observable"] = sorted(
                {r.port for r in answer.observed_via if r.port})
            update["unobservable_reason"] = ""
            update["observed_via"] = list(answer.observed_via)
        # A REACHING CHAIN IS KEPT ON ITS OWN. It used to be discarded whenever
        # no observation route came back -- `if not answer.observed_via:
        # continue` threw away the whole answer -- so the one artefact the
        # stimulus author needs went out with a question it had not been asked.
        if answer.activated_via:
            update["activated_via"] = list(answer.activated_via)
        if not update:
            continue          # an honest "no route" -- see INDIRECT_SYSTEM
        routed[shape.req_uid] = shape.model_copy(update=update)
    merged = [routed.get(n.req_uid, n) for n in normalized]
    # "28 resolved" alone is the number a reader over-trusts. Logged with what
    # the routes rest on, because the two together say something neither says
    # apart -- and a 100% resolution rate is the shape of a model reaching for
    # an answer, so the count is never the whole report.
    review = indirect_review(merged)
    logger.info(
        "normalize: %d of %d requirement(s) resolved indirectly "
        "(%d resting wholly on timing, %d route(s) on a port their own "
        "activation pins)",
        len(routed), len(blind),
        review.get("requirements_resting_wholly_on_timing", 0),
        len(review.get("antecedent_port_routes", [])),
    )
    return merged, list(results)


#: Vocabulary that makes a `shows` clause rest on WHEN something happens rather
#: than WHAT value appears. Deliberately lexical and deliberately coarse: this
#: classifies the model's prose, it does not understand it.
_TIMING = re.compile(
    r"\b(cycle|cycles|clock|clk|tick|ticks|edge|edges|period|duration|interval|"
    r"latency|delay|delayed|pulse|pulses|re-?tim\w*|synchron\w*|held\s+steady|"
    r"remains?\s+held|quiescent|transition|transitions|timing|sample|samples|"
    r"sampled|expiry|expires|window)\b",
    re.I,
)


def discriminates_on(route: Route) -> str:
    """`"timing"` or `"value"` -- what this route's `shows` separates cases by.

    REPORTED, NEVER GATED, and the distinction is not neutral for this project.
    Phases 3-6 severed pacing from latency and stopped `latency_cycles` gating
    precisely because the specification does not pin cycle counts, so a check
    that asserts one either fails correct designs or asserts nothing. An
    INDIRECT route is more exposed than a direct one: it borrows a port whose
    timing belongs to another requirement's behaviour, so it inherits every
    timing assumption of the requirement it borrowed from.

    A lexical screen over prose is a weak instrument and is named as one -- it
    goes on the face of the artifact for a reader to weigh, and no gate reads
    it. On a2-i2c it reproduced a hand reading of all 28 resolved requirements
    exactly, which calibrates it against the one dataset that exists and not
    against any other.
    """
    return "timing" if _TIMING.search(route.shows or "") else "value"


def antecedent_port(req: NormalizedRequirement, route: Route) -> bool:
    """Is the route's port pinned by the requirement's OWN activation?

    When it is, the check risks reducing to "when scl_oen == 1, scl_oen == 1" --
    a route observing the requirement's ANTECEDENT instead of its consequent,
    which cannot fail.

    IT IS A SHAPE, NOT A CONVICTION, and the difference is measured. On a2-i2c
    seven routes carried an antecedent port: five restate the activation and are
    genuinely circular, two (REQ-0035, REQ-0069) name the port in a PRECONDITION
    and then discriminate on its DYNAMICS -- held steady versus transitioning,
    re-timed versus not -- which is the correct move, not a defect. A gate here
    would reject those two to catch the five, and this codebase refuses that
    trade elsewhere: `trust.sensitivity` prefers UNKNOWN over convicted.

    The instrument that convicts a circular route correctly is vacuity, one
    stage later and for free -- a check that cannot fail is what variants
    detect.
    """
    text = (req.activation.text or "") if req.activation else ""
    if not route.port or not text:
        return False
    return bool(re.search(rf"\b{re.escape(route.port)}\b", text))


def indirect_review(normalized: list[NormalizedRequirement]) -> dict:
    """What we computed ABOUT the routes, kept apart from what the model said.

    `observed_via` is the model's answer; this is our reading of it, and mixing
    the two into one object would let a computed flag be mistaken for something
    the resolution pass asserted. Same separation as the slicer replacing
    `covers`: a claim and a computation do not share a field.

    CONCENTRATION IS HERE FOR A REASON. Eleven requirements routed through one
    port fail together, and that is one finding rather than eleven -- if the
    timing story around `cmd_ack` is wrong it is wrong for all of them at once,
    and they will not fail independently. A reader who sees only "28 resolved"
    cannot know that.
    """
    routes = [(n, r) for n in normalized for r in n.observed_via]
    if not routes:
        return {}
    ports: dict[str, int] = {}
    through: dict[str, int] = {}
    kinds = {"timing": 0, "value": 0}
    antecedent: list[dict] = []
    per_req: dict[str, list[dict]] = {}
    for n, r in routes:
        kind = discriminates_on(r)
        kinds[kind] += 1
        ports[r.port] = ports.get(r.port, 0) + 1
        through[r.through_req] = through.get(r.through_req, 0) + 1
        pinned = antecedent_port(n, r)
        per_req.setdefault(n.req_uid, []).append(
            {"port": r.port, "through_req": r.through_req,
             "discriminates_on": kind, "antecedent_port": pinned})
        if pinned:
            antecedent.append({"req_uid": n.req_uid, "port": r.port})
    resolved = sorted(per_req)
    # A requirement every one of whose alternatives is an antecedent port has no
    # route left that could fail. That is the number to read, not the route
    # count: one bad alternative among three is survivable, all of them is not.
    no_free = sorted(u for u in resolved
                     if all(x["antecedent_port"] for x in per_req[u]))
    all_timing = sorted(u for u in resolved
                        if all(x["discriminates_on"] == "timing"
                               for x in per_req[u]))
    return {
        "resolved": len(resolved),
        "routes": len(routes),
        "discriminates_on": kinds,
        "requirements_resting_wholly_on_timing": len(all_timing),
        "port_concentration": dict(sorted(ports.items(),
                                          key=lambda kv: (-kv[1], kv[0]))),
        "through_req_concentration": dict(sorted(through.items(),
                                                 key=lambda kv: (-kv[1], kv[0]))),
        "antecedent_port_routes": antecedent,
        "requirements_with_no_non_antecedent_route": no_free,
        "by_requirement": per_req,
        "note": (
            "Computed from the routes, not asserted by the resolution pass, and "
            "read by no gate. `discriminates_on` is a lexical screen over the "
            "model's prose. `antecedent_port` marks a route whose port the "
            "requirement's own activation already pins -- a shape that MAY be "
            "circular and may equally be a precondition the route then "
            "discriminates on the dynamics of; vacuity is what convicts it."
        ),
    }


def unobservable(normalized: list[NormalizedRequirement]) -> dict[str, str]:
    """`req_uid -> why`, for every requirement with no boundary observable.

    These do not get an oracle, a testpoint or a repair attempt. They get
    reported, once, to whoever wrote the specification.
    """
    return {
        n.req_uid: n.unobservable_reason
        for n in normalized if n.unobservable and n.req_uid
    }


def unsupported_observable(
    normalized: list[NormalizedRequirement],
) -> dict[str, str]:
    """`req_uid -> why`, for a requirement whose `observable` NOTHING explains.

    A gate that says `error` and is then ignored is not a gate. The rule this
    reports on already exists and already fires -- "observable at [...] but no
    route given" -- and on c1-i2c it fired on 15 requirements whose checks were
    written anyway. REQ-0094 is the worked case: its text is "arbitration
    checking is performed during WRITE bit operations", it named one port
    (`cmd`), and it shipped declaring `al`, `cmd_ack`, `scl_oen` and `sda_oen`
    observable with NO route saying what any of them shows. The check it got was
    then free to invent one, and did: it required both lines released on
    arbitration loss, which correct hardware does not do.

    A `shows` is what stops that. Without one the port is a licence with no
    claim attached, which is the vacuity failure this stage exists to catch
    arriving as its opposite.

    STATED HONESTLY, because it bears on what this is worth: carrying this
    error does NOT predict a worse check. Measured on c1-i2c, 39% of the checks
    from flagged requirements are refuted by the known-good control, against
    39% from clean ones -- no difference at all. So this is not a quality fix
    and must not be reported as one. It is a consistency fix: the pipeline
    stops acting on a claim its own gate rejected, and the requirement is
    reported to the specification's author instead of being handed to a check
    author who has nothing to write.
    """
    return {
        n.req_uid: (
            f"observable at {sorted(n.observable)} but no route explains what "
            f"any of them shows when this requirement holds and when it does "
            f"not, so a check over them has nothing to assert"
        )
        for n in normalized
        if n.req_uid and n.observable and not n.observed_via
    }


def malformed(
    requirements: list[dict],
    results: list[StageResult[NormalizeOutput]],
) -> dict[str, list[str]]:
    """`req_uid -> the errors it still carried`, for what never normalized.

    DELIBERATELY NOT `ABANDONED`. That disposition means "we attempted this and
    the attempt was exhausted" -- a finding about the specification or the
    stimulus, routed to whoever wrote them. This is a finding about the
    NORMALIZER: it returned a structure its own gate rejects, after every
    repair round it was given. Collapsing the two would file a prompt defect
    inside a spec-quality count, and the two have different readers.

    Dropped from the loop, never dropped from the report. §8.0's denominator
    rule applies without exception: these leave the numerator AND the
    denominator, and the count is printed beside every rate that now has a
    smaller one. A build that passes with N requirements carrying no check at
    all has to say N.
    """
    out: dict[str, list[str]] = {}
    for req, result in zip(requirements, results):
        if result.ok:
            continue
        uid = str(req.get("uid") or "")
        if uid:
            out[uid] = [f"{i.path}: {i.message}"
                        for i in result.issues if i.severity == "error"]
    return out


def write_artifacts(
    run_dir: Path,
    normalized: list[NormalizedRequirement],
    results: list[StageResult[NormalizeOutput]],
    requirements: list[dict] | None = None,
) -> Path:
    out_dir = Path(run_dir) / "specflow"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "normalized.json"
    path.write_text(
        json.dumps(
            {
                "normalized": [n.model_dump() for n in normalized],
                "unobservable": unobservable(normalized),
                # Reported beside `unobservable` because the consequence is the
                # same -- no check can be written -- while the cause is not: the
                # boundary was named and never explained.
                "unsupported_observable": unsupported_observable(normalized),
                # What never normalized, and is therefore absent from
                # `normalized` above. On the face of the artifact so the
                # smaller denominator is visible beside the count.
                "malformed": (malformed(requirements, results)
                              if requirements is not None else {}),
                "indirect_review": indirect_review(normalized),
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
