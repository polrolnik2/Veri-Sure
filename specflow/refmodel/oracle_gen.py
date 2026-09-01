"""Write one requirement's oracle, from the requirement and nothing else.

Today the oracle is written by the JUDGE, in the same reply as its verdict, from
a prompt that carries the reference model's source (`judge.py:456`), the model
driven over a corner sweep (`:459`), and the model replayed under each
testpoint's concrete stimulus (`:665`). Three measurements say what that costs:

* On `a-i2c` the generated model passed 35 of 54 trusted oracles while the
  known-good control passed 25. A correct design scoring WORSE than the design
  under test, on checks meant to come from the specification, is what an oracle
  fitted to what it was shown looks like.
* On the same run 22 of 54 trusted oracles were failed by that control, and 10
  of the 18 findings the debug agent could not discharge were among them. It
  spent its attempts on demands no correct model can meet.
* Reading the implementation is HOW an oracle acquires implementation-specific
  demands. There is no prompt rule that survives having the answer in context;
  the ISSTA-2026 misguidance result is that presence in context is the cause,
  not intent.

So the oracle is generated here instead, before any verdict exists, from the
normalized requirement plus the contract's port list. Not "and is asked not to
look at the model" -- the model is not in the prompt, and
`tests/test_oracle_isolation.py` reads the constructed prompt back and asserts
it. That is the same enforcement `validate._static_checks` (`validate.py:40-70`)
already applies to RTL contamination of the reference model: a property of the
artifact, checkable by a script, rather than an instruction.

**`tp_uids` is assigned by the harness, not chosen by the model.** S2 already
recorded which testpoints cover which requirement, in `covers`, before any
oracle existed. Letting the generator choose instead means letting it choose
without having seen any stimulus -- and on `d-i2c` that failure was measured at
17 of 23 malformed oracles: 11 omitted `tp_uids` and 6 invented names no
testplan contains. Assigning it removes the whole class, and it keeps the
scoping that step 0 measured as load-bearing (deciding oracles outside their
named testpoints traded 1 true finding for 27 false ones).
"""

from __future__ import annotations

import json

from eda_agent.utils import extract_json_object, strip_markdown_code_fences
from pydantic import BaseModel

from ..fanout import compose, json_block, shared_block
from ..model_io import ModelPort
from ..schema import Issue
from ..stage import StageResult, run_fanout, run_stage
from .oracles import RequirementOracle, well_formed

STAGE = "oracle"

PARSE_ERROR = "Parse Error: "


class OracleOutput(BaseModel):
    reasoning: str = ""
    clause: str = ""
    source: str = ""


SYSTEM = """\
You write the DECISION PROCEDURE for one requirement: a small Python function
that decides mechanically whether a design honours it.

You are not judging anything. You have not been shown an implementation and you
will not be -- that is deliberate and it is the point of this stage. An oracle
written while looking at a design ends up encoding that design's choices, and
then a DIFFERENT correct design fails it. Measured on this pipeline: oracles
written that way were failed by a known-good reference implementation 41% of the
time, and the loop spent its repair budget on demands no correct design can
meet.

So write what the SPECIFICATION requires, not what any particular design does.
Where the specification leaves something open -- an exact cycle count it never
states, an encoding it does not fix -- your check must leave it open too.

You are given the requirement, the specification text it was drawn from, and its
normalized form:

  activation   WHEN the requirement applies
  observable   WHICH declared output ports the behaviour is visible on
  expectation  WHAT must then be true of them

Your oracle decides the `expectation` over the `observable`, at the moments the
`activation` holds.

WHEN A ROUTE NAMES A `through_req`, THE PORT BELONGS TO ANOTHER REQUIREMENT.

`observed_via` IS NOT THAT SIGNAL, and reading it as one is the error this
paragraph used to invite. Every observable requirement carries a route -- the
route is the base case, and a DIRECTLY observable one names its own port with
`through_req` EMPTY. Measured on c1-i2c: 109 of 122 requirements carry
`observed_via` and only 33 name a `through_req`, so everything below applied to
76 requirements whose port was their own. Check the field, not the list.

A route with an empty `through_req` is your own port and the rest of this
section does not apply to it: decide the `expectation` there directly.

For a route that DOES name one, this requirement's own text names no output
port -- the behaviour reaches the boundary through what it makes some other
requirement do. Each such entry gives you:

  port         the declared output to decide at
  through_req  the requirement that port belongs to
  when         the condition under which that port carries THIS requirement's
               effect rather than the other requirement's own
  shows        what the port does when this requirement holds, AND when it does
               not

Any ONE route is enough; you do not have to use them all.

TWO WAYS TO GET THIS WRONG, and they are opposite.

  Checking the OTHER requirement. If your check would pass or fail identically
  whether or not this requirement holds, you have written `through_req`'s check
  again under a different uid. `when` is what separates them: decide only at the
  moments it describes.

  Checking only one side of `shows`. It names two cases because the observation
  is a DIFFERENCE at a port this requirement does not own -- one case is
  satisfied by that port's ordinary behaviour, so a check on it alone would pass
  a design with none of this requirement's behaviour at all. Return None rather
  than True when the trace shows only one of the two.

WHEN `activated_via` IS PRESENT, the activation is a state something has to
reach, not values something drives. The entries are the prerequisites in order,
each naming the requirement whose behaviour gets you there. You do not stage
anything -- that is the stimulus's job -- but you may need them to recognise the
moment: the activation holds after those prerequisites have occurred, not
whenever their inputs appear.

    def decide(trace):
        # trace is a list of STATES, not of clock edges:
        #   {"index": int,      position in the sequence, 0, 1, 2, ...
        #    "held":  int,      how many clock edges this state lasted
        #    "inputs": {...}, "outputs": {...},
        #    "edge":  int}      the first clock edge of this state
        #
        # Consecutive edges with identical inputs AND outputs are one entry, so
        # trace[i+1] is THE NEXT DISTINCT STATE, not the next clock. That is
        # what a specification means by "then": the design may take any number
        # of edges to get there -- synchronisers, filters and prescaler dividers
        # all cost edges the spec does not fix -- and it is still correct.
        #
        # Walk the sequence. Use `index` to talk about order and `held` when the
        # requirement states a duration. Do not compute with `edge`; it is there
        # so a failure can be pointed at, not reasoned from.
        # Return (ok: bool | None, edge: int | None, detail: str).
        #
        # WHEN THE REQUIREMENT DESCRIBES AN ACTION, LOOK FOR THE TRANSITION,
        # NOT THE LEVEL. On an open-drain or active-low line the RESTING value
        # and the "released"/"inactive" value are the SAME NUMBER, so a scan for
        # `outputs[p] == released` matches the very first state, before anything
        # has happened, and every prior step you meant to require looks absent.
        #
        # Measured: a check demanding SDA pulled low before SCL is released
        # failed a design that did exactly that -- sda_oen 0, then scl_oen 1 --
        # because it took the first `scl_oen == 1` in the trace, which was the
        # idle state at index 0. Compare `trace[i]` against `trace[i-1]` and
        # require the CHANGE, or anchor your search after the activation you
        # already located. A sibling requirement stated the same ordering, so
        # this was not a disagreement about the protocol; it was a level read
        # where a transition was meant.
        #
        # Each port's `notes` in the contract say which value drives and which
        # releases. Read them before deciding what "asserted" means for it.
        #
        # AND THE CONVERSE, WHICH IS THE OTHER HALF OF THE SAME RULE. A
        # requirement can describe a STATE rather than an ACTION -- "is high
        # while X", "is observed low", "remains released", "holds its value".
        # There a correct design may ALREADY hold the value when the window
        # opens and never change it, so a check that requires a transition, an
        # edge, or `strong=True` reports a failure against a design that is
        # right. Nothing in the trace distinguishes "it changed to the correct
        # value" from "it was correct all along" except which of the two the
        # requirement asked for.
        #
        # So: require the TRANSITION when the requirement names an ACTION, and
        # require the LEVEL when it names a STATE. When the resting value and
        # the asserted value are the same number, say which one the requirement
        # means BEFORE choosing -- that ambiguity is the reason for both halves
        # of this rule, and reading it only one way is how a correct design gets
        # convicted. Measured: 8 of one run's 43 control-refuted checks demanded
        # a transition where the requirement stated a level.
        #
        # Return ok=None when THE ACTIVATION NEVER OCCURS in this trace -- no
        # START was issued, reset was never asserted, the arbitration case never
        # arose. Do NOT return False for that. False means you SAW the situation
        # and the design got it wrong, and it sends someone to fix code that may
        # be perfectly correct. Do NOT return True either: an oracle that passes
        # because it never looked is vacuous, and is discarded as such. ok=None
        # is the honest answer and costs you nothing -- it is routed to whoever
        # writes the stimulus, not counted against the design.
        #
        # THAT RULE COVERS "NO WINDOW". IT DOES NOT COVER THE COMMONER CASE:
        # the activation DID occur, the window opened, and the evidence you
        # were looking for is not inside it. Ask which of two things you are
        # looking at before convicting. If the requirement obliges the design to
        # produce something -- "shall assert", "must complete" -- then its
        # absence IS the violation, and False is right. If the requirement
        # states a condition the design is meant to hold, and the window simply
        # never contained the case, that is missing evidence and ok=None is
        # right. "I did not see it" and "it failed to happen" are different
        # findings with different owners, and returning False for the first
        # blames the design for a testpoint that did not exercise it. Measured:
        # 7 of one run's 43 control-refuted checks convicted on absent
        # evidence inside a window that opened.

Rules, each for a reason:

  - Read only DECLARED PORTS out of `outputs` and `inputs`. Internal signals are
    not in the trace. An oracle naming none is rejected as deciding nothing.
  - NEVER look for a clock transition. Every row IS one rising clock edge, so
    the clock port is pinned at its idle value for the whole trace and carries
    no information. "the next rising edge" is simply the next row. An oracle
    hunting a 0->1 on the clock finds a flat line and reports that it cannot see
    its scenario -- which reads as a thin testplan when nothing is wrong.
  - Decide ONLY this requirement's clause. An oracle that also checks
    neighbouring behaviour is discarded for rejecting a correct design.
  - DO NOT DEMAND A RESPONSE AT A PARTICULAR EDGE. The comparison this feeds
    compares the ORDERED SEQUENCE of distinct output states and ignores how long
    each is held, so a design is not required to be cycle-accurate. Real designs
    put synchronisers, majority filters and prescaler dividers between an input
    event and the output that answers it, and every one of those costs edges the
    specification does not fix.

    So "busy rises at the edge the START appears" is wrong even when "busy rises
    after a START" is right, and "al is high at every edge the condition holds"
    is wrong even when "al goes high once the condition occurs" is right. Say
    THAT THE STATE IS REACHED, and where order matters say only that one state
    precedes another. Search forward for the state you expect; do not index a
    fixed edge, and do not require the response in the same row as its cause.

    Demand an exact count only when the requirement itself states one AND the
    specification text you were given says it -- "cmd_ack is high for exactly one
    clock" is a duration the spec fixes, and checking it is correct.

    Measured: 27 of 77 oracles written without this rule are failed by an
    implementation that scores 181/181 against golden RTL, and demanding a
    response too early is the single largest reason.
  - Return the EDGE your decision turns on, so a failure localises itself.
  - No imports, no file or network access.
  - It must FAIL a design that violates the clause and PASS one that honours it.
    It is checked both ways: against an implementation built from this same
    requirement, and against deliberately broken variants of it. An oracle
    nothing can falsify is discarded as demanding nothing.

Do NOT name testpoints. Which testpoints exercise this requirement was decided
by the test plan and is filled in for you.

YOUR EXPECTATION IS ABOUT OUTPUTS. INPUTS ARE THE STIMULUS'S AND THE DESIGN
CANNOT MOVE THEM. Read an input to QUALIFY when your check applies -- "while
`ena` is high", "out of reset" -- and never as the thing that must happen. A
check that passes only when an input takes some value is a check on the
testbench, not on the design: no implementation can satisfy it, so it fails
every design including a correct one, and there is no edit that discharges it.

The case this is written from: a requirement said "driving an output-enable low
causes the I2C line to be pulled low", and its check waited for the line INPUT
`sda_i` to fall after the design asserted `sda_oen`. Pulling the line low is
what the external open-drain wiring does -- the pad and the pull-up, outside
this module. The design's half is asserting the enable, and that is all a check
here may require. Three debug turns could not move it, because nothing could.

TIMING IS TRANSACTIONAL HERE, AND THE OPERATORS ARE HOW YOU SAY SO.
This pipeline compares designs by TRANSACTION, not by cycle: what a requirement
pins is the ORDER and the CONDITIONS of what happens, never the number of edges
between them, because the specification does not state edge counts and a check
that asserts one either fails correct designs or asserts nothing. A window
opened by an activation and closed by a CONDITION is that transaction, and
`after(trace, applies, until=closes)` is how you write one down. These are not
a convenience for requirements that happen to be temporal -- they are the
vocabulary for the comparison this whole pipeline makes.

So: most requirements here are "when A, then B" where B lands LATER -- a command
is accepted, and the bus activity it causes runs for many states afterwards. A
check that reads the output on the same row the activation held reads it before
anything has happened, passes every broken design, and is convicted vacuous.
Six of the last run's fourteen vacuous checks were exactly this. And a check
that instead waits a FIXED number of edges is the opposite failure, pinning a
count the specification never gave.

    from specflow.refmodel.temporal import (after, edges, eventually,
                                            throughout, stable, pulse, worst)

    def decide(trace):
        windows = after(trace,
                        lambda r: r['inputs']['cmd'] == 8,          # applies when
                        until=lambda r: r['outputs']['cmd_ack'] == 1)  # closes on
        return worst([eventually(w, lambda r: r['outputs']['sda_oen'] == w.value('din'))
                      for w in windows])

  after(trace, applies, until=closes)   -> list[Window], one per activation
  eventually(w, holds)                  -> Verdict; holds at SOME row of w
  throughout(w, holds)                  -> Verdict; holds at EVERY row of w
  stable(w, port)                       -> Verdict; port never changes in w
  runs(trace, port, value=0, at_least=N, at_most=M)
                                        -> set of `edge` numbers where a run of
                                           `port == value` BEGINS, bounded in
                                           EDGES. The opener for
                                           `activation.sustains`.
  pulse(w, port, width=1, active=1)     -> Verdict; active for exactly `width`
                                           EDGES, exactly once
  worst(verdicts)                       -> Verdict; folds many, failure first
  w.value(port)                         the value AT the activation
  w.rows, w.edge, w.closed              the rows it spans, where it opened, and
                                           whether it was closed or ran out

A `Verdict` IS `(ok, edge, detail)` -- the same triple `decide` returns -- so
`return worst([...])` is the whole function, and one temporal result can sit
beside hand-written branches without conversion.

`worst([])` is `(None, None, 'the activation never occurred')`. Return it. Do
NOT turn an empty window list into False: no window means the scenario was never
staged, which is a fact about the stimulus, and reporting it as a violation
blames the design for a testpoint that does not exist.

`after` returns at most 64 windows. If you hit that on a long trace you are
matching something far broader than the requirement.

`activation.sustains` IS A WINDOW OPENER, NOT AN OBLIGATION. When it is
present the requirement's activation includes a DURATION the specification
states -- "a majority of the three samples", "shorter than the filter window" --
and `runs` turns it into edges you can open on:

    # normalized: sustains [{"port": "sda_i", "value": 0, "at_most": 1}]
    short = runs(trace, "sda_i", value=0, at_most=1)
    windows = after(trace, lambda r: r["edge"] in short)

A requirement stating BOTH sides of a threshold gives two entries, and they are
two different activations of the same check -- the short one is where the
design must NOT react, the long one where it must. Build both, and let the
short arm convict only when the long arm shows the outputs can move at all;
otherwise a design that ignores the port entirely passes the short arm for the
wrong reason.

COUNT IN EDGES AND LET `runs` DO IT. The trace is state-compressed, so a
five-edge level is one row carrying `held: 5`; a hand-written scan that counts
ROWS calls it a one-edge glitch, which inverts exactly the distinction the
requirement is about.

THE `normalized` BLOCK ALREADY CONTAINS YOUR WINDOW. TRANSCRIBE IT.
`activation.inputs` and `activation.opens_on` are what OPENS it;
`activation.until` is what CLOSES it; `activation.aborts_on` is what DISCARDS
it. You are not inventing a window, you are copying one.

    windows = after(trace, applies, until=closes, aborts=voided)

`aborts` IS SVA's `disable iff`. A window it ends returns UNKNOWN from every
operator -- not a pass, not a failure -- because the attempt was cut short by
something that makes the requirement's promise moot: reset, or an arbitration
loss that returns the FSM to idle. `strong=True` over such a window would read
"the response never came" when the response was never owed, and that is how a
check convicts a correct design. Pass `aborts_on` whenever it is non-empty and
`after` handles the rest -- no operator needs a guard of its own. Every
construct below is built the same way:

    from specflow.refmodel.temporal import (after, eventually, throughout,
                                            stable, pulse, worst)

    # `{port: value}` straight out of the normalized block -> a row predicate.
    def _holds(cond):
        def p(row):
            return all(
                row["outputs"].get(k, row["inputs"].get(k)) == v
                for k, v in cond.items())
        return p

    # `opens_on`, `until` and `aborts_on` are LISTS OF ALTERNATIVES: any entry
    # is enough, and every port within one entry holds together. So this is the
    # one you want for all three.
    def _any(alts):
        preds = [_holds(a) for a in alts]
        return lambda row: any(p(row) for p in preds)

  A WINDOW THAT OUTLASTS ITS TRIGGER -- `until` is non-empty:

    # normalized: inputs {"cmd": 8, "ena": 1}, until [{"cmd_ack": 1}, {"al": 1}]
    # -- "until the WRITE completes OR arbitration is lost"
    windows = after(trace, _holds({"cmd": 8, "ena": 1}),
                    until=_any([{"cmd_ack": 1}, {"al": 1}]))

  A CO-EXTENSIVE WINDOW -- `until` is EMPTY. Omit it, and the window closes when
  the activation stops holding, which is what "while ena is low" means:

    # normalized: inputs {"ena": 0}, until []
    windows = after(trace, _holds({"ena": 0}))

  AN INSTANT -- the same call. A one-row activation gives a one-row window and
  `throughout` over it IS the point check. There is no separate form:

    windows = after(trace, _holds({"rst": 1}))

  AN INVARIANT -- "at all times", "never":

    windows = after(trace, lambda r: True)

  AN ACTIVATION THAT DEPENDS ON AN OUTPUT -- merge `opens_on` into the opening
  predicate. It qualifies the trigger; it is not the thing being checked:

    # normalized: inputs {"nReset": 1}, opens_on [{"scl_oen": 0}, {"sda_oen": 0}]
    # -- "AN output-enable is driven low", either of them
    opens = _any([{"scl_oen": 0}, {"sda_oen": 0}])
    windows = after(trace, lambda r: _holds({"nReset": 1})(r) and opens(r))

  AN EDGE IN THE CONDITION -- a value of `"rise"`, `"fall"` or `"change"`
  instead of a number. `edges()` gives you the rows where the port moved, and
  the level ports are checked at that same row:

    # normalized: opens_on [{"scl_i": "fall", "scl_oen": 1}]
    fell = edges(trace, "scl_i", "fall")
    windows = after(trace, lambda r: r["edge"] in fell
                    and r["outputs"].get("scl_oen") == 1)

  `after` alone will NOT do this for you, and the reason is worth knowing. It
  opens on a rising activation, so a lone `{"scl_i": 0}` does give
  falling-edge-of-scl_i windows -- but a MIXED condition makes it open on the
  edge of the CONJUNCTION, which also fires when `scl_oen` rises over an
  already-low `scl_i`. That is a different event, and it is the one three
  checks reported as never occurring.

  WHETHER THE EFFECT FOLLOWS THE TRIGGER IS ALREADY DECIDED FOR YOU. The
  normalized block carries `activation.effect_follows`. Pass it straight
  through -- do not re-derive it, and do not leave it out:

    follows = normalized["activation"]["effect_follows"]
    return worst([eventually(w, holds, after_activation=follows)
                  for w in windows])

  It is true exactly when the window closes on a condition, because a window
  that closes on a condition is one whose effect outlasts its trigger. When it
  is false the expectation holds at the activation row too, and reading from
  there is correct.

  EVERY WINDOW OPERATOR TAKES IT, not just `eventually` -- `throughout`,
  `stable`, `pulse`, `never`, `sequence` and `until` all do, and they all mean
  the same thing by it: evaluate from the row AFTER the trigger. Pass it to
  whichever one the requirement needs. (`nexttime` accepts it too and is
  already `##1`, so it is a no-op there.)

  THEN THE EXPECTATION -- one operator per shape, and `worst` folds the windows:

    return worst([eventually(w, lambda r: r["outputs"]["sda_oen"] == w.value("din"))
                  for w in windows])     # at SOME row -- "eventually X"
    return worst([throughout(w, lambda r: r["outputs"]["scl_oen"] == 1)
                  for w in windows])     # at EVERY row -- "X remains"
    return worst([stable(w, "scl_oen") for w in windows])   # "held steady"
    return worst([pulse(w, "cmd_ack") for w in windows])    # "for one clk cycle"

NEVER COLLAPSE A LIST OF ALTERNATIVES INTO ONE DICT. `[{"al": 1},
{"cmd_ack": 1}]` is "either"; `{"al": 1, "cmd_ack": 1}` is "both at one row",
and arbitration loss clears `cmd_ack`, so that one can never happen -- the
window opens, runs to the end of the trace and decides nothing. Six of one
run's 28 windows were exactly this.

DO NOT RE-DERIVE THE WINDOW BY HAND. `for i in range(len(trace))` with your own
index arithmetic is how a check ends up reading the outputs on the row the
activation began, before the design has done anything. That gives a check which
fails EVERY design or passes every design depending only on which way the port
happened to sit at that instant -- and on one measured run those two populations
were 79% and 83% exactly this shape.

THESE ARE THE SVA OPERATORS, over a Python trace instead of a clock.
They are SVA-SHAPED, NOT SVA -- the eight numbered differences further
down are the ones that will bite you:

  after(t, a, until=b)          `a |-> ...` up to `b` -- the antecedent window
  eventually(w, p)              `p` at SOME row of it        -- weak
  eventually(w, p, strong=True) `s_eventually p`             -- must happen
  eventually(w, p, after_activation=True)   `a |=> p` -- NOT at the trigger row
  throughout(w, p)              `p throughout` the window
  never(w, p)                   `not p` anywhere in it
  until(w, p, q)                `p until q`   (strong=True -> `s_until`)
  sequence(w, p, q, r)          `p ##[1:$] q ##[1:$] r` -- ORDER, no counts
  nexttime(w, p)                `##1 p` -- the next STATE, not the next clock
  stable(w, port)               `$stable(port)` across it
  pulse(w, port)                `$rose` then `$fell` one state later

  ...and `after_activation=` is accepted by EVERY operator on that list which
  takes a window: `throughout`, `never`, `until`, `sequence`, `stable`,
  `pulse`, `nexttime`. It always means `|=>` rather than `|->`.
  edges(t, port, "rise")        `$rose(port)`   ("fall" -> `$fell`,
                                                 "change" -> `$changed`)
  w.value(port)                 the sampled value AT the activation
  w.past(port)                  `$past(port)` -- its value the row before
  first_match(windows)          `first_match` -- the first attempt only
  after(t, a, overlap=True)     windows may OVERLAP in extent -- the scan for
                                the next one resumes at the row after this
                                window OPENED rather than after it closed.
                                NOT SVA's attempt model: a window still starts
                                only on a RISING activation, in both modes.
  worst(verdicts)               fold many attempts, failure first

TWO THINGS ARE DELIBERATELY ABSENT AND YOU SHOULD NOT WANT THEM.
`##[2:5]` and `[*n]` are CYCLE COUNTS. This specification does not state edge
counts, so a check that asserts one either fails correct designs or asserts
nothing -- Phases 3-6 of this project severed pacing from latency for exactly
that reason. `##1` survives because a ROW IS A STATE: consecutive edges with
identical inputs and outputs collapse into one, so "the next row" means "the
next time anything changed", which is what "then" means in a specification.

THE TWO DEFAULTS MOST OFTEN WRONG, and both were measured:

  * `eventually(w, p)` is satisfied AT THE ACTIVATION ROW, because the window
    opens there -- six of one run's fourteen vacuous checks read the
    expectation on the same row as the activation. You do not have to judge
    this: `activation.effect_follows` in the normalized block is the answer,
    and passing it through is the whole of the fix.
  * `eventually(w, p)` is WEAK: a window that runs off the end returns UNKNOWN,
    not a failure. If the requirement says the response MUST come, pass
    `strong=True`, or the check can never be violated -- only left undecided.
    Five of one run's fourteen abstaining checks abstained for this reason.

    THIS ONE HAS A BOUNDARY AND IT IS EASY TO CROSS. `strong=True` says
    "running out of trace is the design's fault". That is true for an
    OBLIGATION -- the requirement promised a response and none came -- and
    false for a STATE, where running out of trace means only that you stopped
    looking. Passing it on a requirement that says "is high while X" converts
    a short testpoint into a conviction. Read the requirement for an obligation
    before you pass it; the default is weak because most requirements are not
    obligations.

Write the check the way you would write the assertion, and reach for the
operator you would reach for in SVA. EIGHT PLACES THE ANALOGY BREAKS, and the
third is the one that bites:

  1. `throughout(w, p)` takes a WINDOW and a PREDICATE, where SVA takes a
     sequence on each side.
  2. `stable(w, port)` is "never changed anywhere in the window", not a
     sampled-value function at one tick.
  3. A ROW IS NOT A CLOCK TICK. The trace is state-compressed: consecutive
     edges with identical inputs AND outputs collapse into one row carrying
     `held`. So `len(w.rows)` is not a cycle count and never was. `pulse` sums
     `held` for you -- which is why a 40-edge assertion is not a one-cycle
     pulse -- and any counting you do yourself must sum it too.
  4. `$rose` IS A SAMPLED-VALUE FUNCTION and `edges` IS A SET. SVA evaluates
     `$rose(p)` at each tick and you drop it straight into an expression; here
     `after` takes a predicate over ONE row and cannot see the previous one, so
     the transitions are computed over the whole trace up front and you test
     membership: `r["edge"] in fell`. Same meaning, computed once instead of
     per row.

     And on a MULTI-BIT port they are not the same thing at all. SVA's `$rose`
     is defined on the LSB; `edges(..., "rise")` means the value INCREASED. On
     a 1-bit port those coincide exactly, which is every port these
     requirements are about. On a wider one, say what you mean with "change".
  5. AN ANTECEDENT THAT NEVER MATCHES IS UNKNOWN HERE, NOT A PASS. `a |-> b`
     with no matching `a` is VACUOUSLY TRUE in SVA and only `cover property`
     reports the miss. `worst([])` returns UNKNOWN instead, because a check
     that decided nothing must not read as a check that passed. You do not
     have to do anything about this -- just do not write a fallback `return
     True` for "the activation never occurred", which would reintroduce
     exactly the vacuous pass the operator refuses.
  6. AN INCOMPLETE WINDOW IS UNKNOWN HERE TOO. SVA passes attempts still open
     when the simulation ends; a window that ran off the end of the trace
     returns UNKNOWN. Same reason as 5.
  7. THERE IS NO `disable iff`, and no `[->n]` goto repetition. Reset
     exclusion goes in your activation predicate, by hand. "The nth
     occurrence" is not expressible -- note that this is NOT the cycle-count
     rule below, which is a separate and deliberate omission; `[->n]` is
     simply not built yet, so write the requirement without it or say in your
     reasoning that you could not.
  8. `until` IS SVA's `until`, NOT `until_with`: `holds` need not be true on
     the row where `release` fires, because the release is tested first.
     There is no `until_with`.

TWO OPERATORS ABSTAIN WHERE YOU MIGHT EXPECT A VERDICT, AND BOTH ARE ON
PURPOSE. `throughout`, `never`, `stable` and `pulse` over ZERO rows -- which
is what `after_activation=True` gives you on a one-row window -- return
UNKNOWN, because an invariant that held over no rows did not hold. And `pulse`
returns UNKNOWN when the port was ALREADY at its active value before the
window opened: no rise was witnessed there, so the width is not measurable,
and counting it let a port stuck high report "pulsed once". If you need the
pulse and the window keeps opening too late, put
`edges(trace, "port", "rise")` in the ACTIVATION rather than widening the
check.

GIVE `after` AN `until`. Without one the window ends where the activation
does, so a check looking for a later effect sees nothing and fails -- which is
the safe direction, but it is not the check you meant.

`until` CLOSES ON A CONDITION, NEVER A COUNT. "wait until cmd_ack" is
expressible; "wait 12 edges" is a guess, and a check that asserts a cycle count
this specification does not state will either fail correct designs or assert
nothing.

A window that runs off the end of the trace returns UNKNOWN, not False --
nothing was seen to be wrong, we stopped looking -- and these operators do that
for you. Hand-written scanning gets it wrong in the direction that blames a
correct design.

Use plain Python where the requirement really is about one instant. These are
for when it is not.

Reply with ONE JSON object and nothing else:

{
  "reasoning": "...",
  "clause": "cmd_ack is high for exactly one clock when the command completes",
  "source": "def decide(trace):\\n    pulses = [r for r in trace if r['outputs']['cmd_ack']]\\n    if not pulses:\\n        return (None, None, 'cmd_ack never rose; the command never completed in this trace')\\n    bad = [r['held'] for r in pulses if r['held'] != 1]\\n    if bad:\\n        return (False, pulses[0]['edge'], f'cmd_ack held for {bad} edges, expected 1')\\n    return (True, None, f'{len(pulses)} single-edge pulse(s)')"
}
"""


def shared_prefix(contract_json: str, contract: dict) -> str:
    """Byte-identical across every requirement of one node.

    It contains the SYSTEM prompt, the contract and the port lists -- and
    deliberately nothing else. Everything that changes per round in the judge's
    prefix (the model source, its observed behaviour) is absent here, so unlike
    the judge's this prefix is warm for the whole node rather than cold at the
    start of every round.
    """
    ports = {
        "outputs": [
            {"name": p.get("name"), "width": p.get("width", 1)}
            for p in (contract.get("io") or [])
            if p.get("dir") == "output" and p.get("name")
        ],
        "inputs": [
            {"name": p.get("name"), "width": p.get("width", 1)}
            for p in (contract.get("io") or [])
            if p.get("dir") == "input" and p.get("name")
        ],
    }
    return shared_block(
        ("system", SYSTEM),
        ("contract_json", contract_json),
        ("declared_ports",
         json.dumps(ports, indent=2)
         + "\n\nThese are the only names that appear in a trace row. Anything "
           "else the requirement mentions is internal to the design and cannot "
           "be read."),
    )


#: THE REPAIR-ROUND OVERRIDE, and it exists because the shared briefing is wrong
#: about this one thing on exactly the rounds that matter.
#:
#: `SYSTEM` says "THE `normalized` BLOCK ALREADY CONTAINS YOUR WINDOW.
#: TRANSCRIBE IT. You are not inventing a window, you are copying one." That is
#: a good default at generation: it keeps every check's window derived from one
#: reading of the sentence rather than from the author's own, which is what
#: makes two checks of neighbouring requirements comparable.
#:
#: It is NOT a claim that the window is correct, and nothing in the pipeline
#: makes it one. `normalize.gate_one` checks that the response parsed, that
#: there is one block, that `clk` is not in the window and that the port names
#: are declared. It never asks whether `opens_on`, `until` and `aborts_on` are
#: licensed by the requirement's own words -- which is precisely the question
#: `correspondence` asks about the CHECK. And normalization is never re-invoked:
#: `oracles_stage` imports it for two helper types and the repair loop's only
#: outlet is another call to this author.
#:
#: So a wrong window arrives as an instruction and departs as the author's
#: defect. Measured on the c1-i2c re-authoring run: of the nine rejected checks
#: whose requirements were well-formed and boundary-observable, EIGHT were
#: rejected for a condition transcribed verbatim out of `activation.opens_on` or
#: `activation.until`. REQ-0067's normalized form opens on `scl_oen` rising,
#: closes on `scl_oen` falling and declares `scl_oen` its observable, so
#: transcribing it yields a check that cannot fail -- and the reviewer's ground
#: was "there is no unlicensed False path; the check can never return False at
#: all". No author at any strength can transcribe that window and produce a
#: falsifiable check. The only way out is to change it.
#:
#: Emitted ONLY beside gate failures, so generation keeps the default and only a
#: round that has something to answer is told the window is open to question.
#:
#: AND IT IS DELIBERATELY SMALL, because the failure it could cause is the
#: silent one. Nothing gates a window that is too LOOSE: correspondence rejects
#: unlicensed False paths, so a window widened on suspicion makes the check
#: weaker rather than convicted, and the vacuity leg needs variants to see it.
#: Over-correcting here costs nothing visible; under-correcting costs a
#: rejection the author can read. So this says WHEN to change the window and
#: what licenses the change, and it does not pronounce on how much normalization
#: can be trusted in general -- an author told the block is unreliable has every
#: reason to rewrite windows nothing objected to, which loses the comparability
#: the default is there to buy and buys nothing back. The rationale for the
#: change lives in this comment; the prompt carries the instruction alone.
WINDOW_NOT_AUTHORITATIVE = """\
<window_authority>
WHEN A GATE FAILURE ABOVE OBJECTS TO THE WINDOW, CHANGE THE WINDOW.

`activation.opens_on` and `activation.until` are one reading of the same
sentence you have, and nothing has checked that reading against it. So an
objection to WHEN your window opens or closes is an objection to those fields,
and transcribing them again will fail the same way.

  - Drop a condition you cannot point at words in the requirement for, and
    cannot read as an abort either.
  - MOVE a condition that VOIDS the attempt rather than ending it. Reset is
    always one; so is an arbitration loss that returns the FSM to idle, unless
    the requirement is ABOUT that loss. Those belong in `aborts=`, and passing
    them to `until=` instead is the error that convicts a correct design: the
    window ends as though the sequence completed, and a strong obligation then
    reports a response that was never owed as one that never came. Moving is
    not dropping -- drop it and the window runs straight through the reset.
  - Add one the words do license, if the objection is that the window runs past
    what the sentence governs.
  - If the opening, the closing and the asserted effect are all the same
    signal, no design can fail the check whatever you write. Re-derive the
    window from the sentence.

Name the condition you changed in `reasoning` and quote the words that license
it. Change nothing that was not objected to: the default is there so that
neighbouring requirements get comparable windows, and a window rewritten on
suspicion loses that for nothing.
</window_authority>"""


def build_prompt(
    *,
    requirement: dict,
    contract_json: str,
    contract: dict,
    normalized: dict | None = None,
    issues: list[Issue] | None = None,
    previous: str | None = None,
) -> str:
    """Compose the prompt. There is no parameter that could carry a design.

    That is the structural half of invariant I1, and it is why this function
    takes a requirement rather than taking `**kwargs` or a context object: a
    later edit that wanted to pass the model source would have to add a
    parameter, which is a visible change to a signature rather than one more key
    in a dict.
    """
    parts = [json_block("requirement", requirement)]
    if normalized:
        parts.append(json_block("normalized", normalized))
        if issues:
            parts.append(WINDOW_NOT_AUTHORITATIVE)
    return compose(
        shared_prefix(contract_json, contract),
        "\n\n".join(parts),
        issues=issues,
        previous=previous,
    )


def parse_response(text: str) -> OracleOutput:
    try:
        obj = extract_json_object(strip_markdown_code_fences(text))
        return OracleOutput.model_validate(obj)
    except Exception as exc:  # noqa: BLE001
        return OracleOutput(reasoning=f"{PARSE_ERROR}{exc}")


def gate_one(
    out: OracleOutput,
    *,
    req_uid: str,
    tp_uids: list[str],
    contract: dict,
    testplan: list[dict],
    conforming_source: str = "",
    stimulus_by_tp: dict[str, list[dict]] | None = None,
    base: str = "step",
) -> list[Issue]:
    """Screen the oracle before it costs anything downstream.

    Reuses `oracles.well_formed` unchanged rather than re-deriving a screen: an
    oracle is the same trust class as the reference model -- generated Python
    this process will execute -- and if that sandbox is not good enough for one
    it is not good enough for the other.

    **Nothing here runs a design against the oracle, and that is deliberate.**

    A must-pass leg used to live here: the oracle was replayed against the
    witness and a failure came back as a gate issue, so `run_stage` re-prompted
    the author with the exact edge its check tripped on. The reasoning was that
    over-strictness is better caught where it can still be repaired than
    discovered a stage later.

    It is measurably the wrong trade. The witness is a second reading of the
    same requirement by the same author, so it has no authority to say the
    oracle is wrong -- and telling an author "an independent implementation
    fails your check" does not make the check more correct, it makes the check
    agree with the witness. Measured on h-i2c: over-strictness 27 -> 15,
    convictions 2 -> 16. Oracles relaxed until they stopped disagreeing, and the
    relaxation surfacing as vacuity. The docstring here used to concede the
    premise -- "a disagreement could be either" -- and then act on it anyway.

    So this gate is structural only: does the reply parse, does it name the
    clause it decides, and is it a well-formed decision procedure. Whether an
    oracle is satisfiable, and whether it can fail anything, are decided later
    by `oracles_stage.verify_one`, where a design records rather than rejects.
    """
    if out.reasoning.startswith(PARSE_ERROR):
        return [Issue("error", f"oracle.{req_uid}.response", out.reasoning)]
    if not out.clause.strip():
        return [Issue("error", f"oracle.{req_uid}.clause",
                      "no clause; say which sentence of the requirement this "
                      "decides, so a reader can tell an over-strict oracle from "
                      "a real defect")]
    oracle = RequirementOracle(req_uid=req_uid, tp_uids=list(tp_uids),
                               clause=out.clause, source=out.source)
    why = well_formed(oracle, contract, testplan)
    if why:
        return [Issue("error", f"oracle.{req_uid}.source", why)]

    return []


def run_oracle_gen(
    *,
    requirements: list[dict],
    contract_json: str,
    contract: dict,
    testplan: list[dict],
    port: ModelPort,
    normalized: dict[str, dict] | None = None,
    #: An implementation built from these same requirements, for the must-pass
    #: leg. NEVER the golden control: feeding a known-good design's behaviour
    #: back into oracle generation is the contamination I1 exists to prevent,
    #: and it would destroy `golden_check` as a held-out measure.
    conforming_source: str = "",
    stimulus_by_tp: dict[str, list[dict]] | None = None,
    base: str = "step",
    max_repairs: int = 2,
    fanout: bool = True,
    #: `req_uid -> issues` seeding the FIRST prompt for that requirement, so a
    #: rejected oracle is re-asked with the reason it was rejected for. This is
    #: what gives the oracle stage the repair loop every other stage has: today
    #: a rejection is terminal because nothing ever re-asks.
    feedback: dict[str, list[Issue]] | None = None,
    #: Regenerate only these requirements. Scoped repair costs one call each,
    #: against 77 for a full pass.
    only: set[str] | None = None,
    #: `req_uid -> the check being revised`, rendered as the previous answer.
    #: Only a repair round supplies one; first generation has nothing to revise.
    standing: dict[str, str] | None = None,
    #: Appended to the stage name so a LATER pass over the same requirement is
    #: recorded beside the first rather than on top of it. `model_io` keys every
    #: prompt/response pair by `{stage}_r{round}` and each `run_stage` call
    #: starts its rounds at zero, so a repair pass silently rewrites the record
    #: of the attempt it is repairing -- destroying both the oracle that was
    #: rejected and the prompt showing why, which is the evidence every
    #: measurement in this project is reconstructed from.
    label: str = "",
) -> tuple[list[RequirementOracle], dict[str, StageResult[OracleOutput]]]:
    """One oracle per requirement, generated before any verdict exists.

    `tp_uids` comes from the testplan's `covers`, never from the model. A
    requirement no testpoint covers gets no oracle: there would be nothing to
    replay it against, and an oracle naming no testpoint is discarded by
    `well_formed` anyway -- better to not spend the call.

    **Every oracle that has a source is returned, including one whose gate
    failed**, keyed results beside it. Dropping the failures here is what made 5
    of 77 requirements vanish on h-i2c into an `UNDECIDED` that also means
    "decided nothing" -- a silent subset, which is the failure mode the verdict
    enum exists to remove. Deciding what a gate-failing oracle IS belongs to the
    stage, which can record it; it does not belong to the generator, which can
    only forget it.
    """
    from ..obligation import by_requirement

    attached = by_requirement(testplan)
    wanted = [r for r in requirements if attached.get(str(r.get("uid") or ""))]
    if only is not None:
        wanted = [r for r in wanted if str(r.get("uid") or "") in only]
    seeds = feedback or {}

    def one(req: dict) -> StageResult[OracleOutput]:
        uid = str(req.get("uid") or "")
        tps = attached.get(uid, [])
        return run_stage(
            stage=f"{STAGE}_{uid or 'unknown'}{label}",
            port=port,
            # `previous` is THIS call's own prior attempt, which is empty on the
            # first one -- so a repair round said "tighten your check" to an
            # author holding no copy of the check. `standing` is the frozen
            # oracle being revised, and it fills that first attempt.
            #
            # Measured before this existed: every strengthening rejection read
            # `vacuous: passed all N variant(s)`, meaning the author answered
            # "tighten it" by writing something WEAKER. An author composing
            # afresh from the requirement has no way to be more specific than a
            # check it cannot see, and no reason to land near it.
            build_prompt=lambda issues, previous: build_prompt(
                requirement=req, contract_json=contract_json, contract=contract,
                normalized=(normalized or {}).get(uid),
                issues=issues or seeds.get(uid),
                previous=previous or (standing or {}).get(uid),
            ),
            parse=parse_response,
            gate=lambda out: gate_one(
                out, req_uid=uid, tp_uids=tps, contract=contract,
                testplan=testplan, conforming_source=conforming_source,
                stimulus_by_tp=stimulus_by_tp, base=base),
            max_repairs=max_repairs,
        )

    results = run_fanout(wanted, one) if fanout else [one(r) for r in wanted]
    by_uid: dict[str, StageResult[OracleOutput]] = {}
    oracles: list[RequirementOracle] = []
    for req, result in zip(wanted, results):
        uid = str(req.get("uid") or "")
        by_uid[uid] = result
        if not (result.output.source or "").strip():
            continue
        oracles.append(RequirementOracle(
            req_uid=uid,
            tp_uids=list(attached.get(uid, [])),
            clause=result.output.clause,
            source=result.output.source,
        ))
    return oracles, by_uid
