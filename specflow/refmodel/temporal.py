"""Temporal operators for requirement oracles.

An oracle decides a requirement over a trace, and almost every hardware
requirement is temporal: *when* A holds, *then* B must follow -- eventually,
or throughout, or exactly once. Python has no vocabulary for that, so every
oracle re-derives it as hand-rolled index arithmetic, and the shape that
arithmetic makes easiest is the one that is usually wrong.

Measured on a2-i2c. Fourteen oracles were convicted vacuous, and six of them --
REQ-0051, 0053, 0055, 0057, 0092, 0094 -- evaluate the expectation on the SAME
trace row as the activation. REQ-0092 is the clearest: its activation is
`cmd == 8 and ena == 1`, the command-issue window, and it reads `sda_oen`
there. An i2c bit controller drives SDA during transmission, tens of edges
after `cmd` has deasserted. The check is not weak, it is empty -- it reads a
port at edges where nothing was ever going to be wrong, which is why it passed
all five designs built to violate it.

Nothing in those oracles is badly written. There is no early return, no
any-match standing in for all-match; an AST screen over all fourteen found no
such pattern. Each half is a faithful transcription of the normalized form.
The fault is the joint assumption that the two halves hold at one instant.

WINDOWS CLOSE ON A CONDITION, NEVER A CYCLE COUNT. Phases 3-6 severed pacing
from latency and stopped `latency_cycles` gating because the specification does
not pin cycle counts, and a check that asserts one either fails correct designs
or asserts nothing. `until` mirrors the stimulus schema's own idiom, which
exists for the same reason: "drive this, then wait for that event" is
expressible where "wait 12 edges" is a guess.

AND THE TRUNCATION DISTINCTION COMES BACK STRUCTURED. `verdict.truncated()`
tells "failed because it saw a defect" from "failed because the trace ran out"
-- VIOLATES against NOT_EXERCISED -- by string-matching the oracle's own prose
against seven phrases ("end of trace", "never asserted", ...). An author who
words it differently is scored as having found a real bug. A window that closes
by running out of trace returns UNKNOWN here, once, and says so in wording
`truncated()` already recognises.

THIS IS AN SVA-SHAPED VOCABULARY, NOT SVA. `docs/sva-divergence.md` is the
complete list of where the two differ -- five places that were defects and are
now fixed, and ten that are deliberate. Read it before "correcting" an operator
toward SVA semantics: the abstentions especially are choices, not oversights,
and SVA's answer in several of them is a vacuous pass this pipeline refuses.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

#: A predicate over one trace row. A row is a STATE, not a clock edge:
#: consecutive edges with identical inputs AND outputs collapse into one entry
#: carrying `held`, the number of edges it lasted. `edge` is its first edge and
#: is for pointing at a failure, not for computing with.
Pred = Callable[[dict], bool]

#: What a check reports. `None` is not a third kind of failure: it means the
#: trace could not answer, and every gate in this pipeline keeps that separate
#: from a verdict it has earned.
Verdict = tuple[bool | None, int | None, str]


def _val(row: dict, port: str):
    outs = row.get("outputs") or {}
    return outs[port] if port in outs else (row.get("inputs") or {}).get(port)


@dataclass
class Window:
    """One activation and the rows it governs.

    `rows` runs from the activation row up to and including the row that closed
    the window. `closed` is False when the trace ended first, which is what
    makes "we never saw the end of this" reportable rather than silently a
    failure.
    """

    start: dict
    rows: list[dict] = field(default_factory=list)
    closed: bool = True
    #: The row immediately before the activation, for `$past`. One row, not a
    #: history: `$past(sig, 3)` is a cycle count and Phases 3-6 severed those.
    #: `$past(sig)` -- "what it was before this happened" -- is not.
    prev: dict | None = None

    @property
    def edge(self) -> int | None:
        return self.start.get("edge")

    @property
    def body(self) -> list[dict]:
        """The rows AFTER the activation row -- the `|=>` half of the window.

        `rows` opens AT the activation, so a consequent that happens to be true
        at that instant satisfies `eventually` over `rows`. That is the exact
        vacuity this module was written to remove: six of a2-i2c's fourteen
        vacuous checks evaluated the expectation on the SAME row as the
        activation. Reading `body` instead is `|=>`.
        """
        return self.rows[1:]

    def past(self, port: str):
        """`$past(port)` at the activation -- its value on the row before.

        `None` when the activation is the first row of the trace, which is
        `$past`'s own semantics: there is no previous sample to name.
        """
        return _val(self.prev, port) if self.prev is not None else None

    def value(self, port: str):
        """The value of `port` at the activation -- for expectations written
        against what the inputs were WHEN the requirement applied, which is the
        commonest form and the easiest to get wrong by re-reading it later."""
        return _val(self.start, port)


#: The transitions an activation may open on. `change` is either direction, for
#: "whenever X moves" -- narrower than it sounds, since a row exists only where
#: something moved.
EDGES = ("rise", "fall", "change")


def edges(trace: list[dict], port: str, direction: str = "change") -> set[int]:
    """The `edge` numbers of rows where `port` took that transition.

    A LEVEL IS NOT AN EDGE, and the schema could only say level. Measured on
    a2-i2c: 28 of 105 requirements name an edge or a transition in their own
    text, and their normalized activations came back as `{scl_i: 0}` -- the
    author knew it was an edge and had nowhere to write it. REQ-0038's
    requirement text says "a falling edge observed on the filtered SCL", its
    activation text says "a filtered SCL falling edge occurs", and its schema
    said `scl_i == 0`.

    `after` will not save you here, and that is the subtle part. It opens on a
    RISING activation, so a lone `{scl_i: 0}` does give falling-edge-of-scl_i
    windows. But the moment the condition is MIXED -- "scl_i falls WHILE
    scl_oen is released" -- `after` opens on the edge of the CONJUNCTION, which
    fires when `scl_oen` rises over an already-low `scl_i`. That is a different
    event, and it is the one three checks reported as never occurring.

    So the edge is computed here, over the port alone, and combined with the
    level conditions afterwards:

        fell = edges(trace, "scl_i", "fall")
        after(trace, lambda r: r["edge"] in fell and _val(r, "scl_oen") == 1)

    Returns `edge` numbers rather than rows because `edge` is the one field a
    row can be identified by; identity comparison on dicts is not stable across
    a re-read of the trace.

    The FIRST row is never an edge: a transition needs a previous sample, which
    is `$rose`/`$fell` semantics and not a limitation to work around. A port
    that starts at its target value has not moved to it.

    ON A MULTI-BIT PORT `rise`/`fall` MEAN INCREASED/DECREASED, and SVA's
    `$rose`/`$fell` are defined on the LSB. Those coincide exactly on a 1-bit
    port, which is every port these requirements name an edge of; on a wider
    one the two readings differ and `change` is what is usually meant.
    Documented rather than rejected here, and warned about at normalisation
    where the port width is known.

    A ROW THAT CARRIES NO SAMPLE OF `port` IS SKIPPED, and `prev` is left
    standing. `_val` returns `None` both for a port absent from the row and for
    one the harness could not read -- a DUT that does not expose a declared
    output samples as `None` -- and neither is a transition. Comparing that
    `None` raised `TypeError: '>' not supported between 'NoneType' and 'int'`
    on `rise`/`fall`, killing the whole check; on `change` it was quieter and
    worse, reporting an edge at the row where the sample went missing and
    another where it came back. Skipping means "we did not look here", so
    `0, <absent>, 1` is one rise at the third row rather than two changes at the
    second and third.
    """
    if direction not in EDGES:
        raise ValueError(f"direction must be one of {EDGES}, got {direction!r}")
    out: set[int] = set()
    prev = None
    for row in trace:
        now = _val(row, port)
        if now is None:
            continue
        if prev is not None and now != prev:
            if (direction == "change"
                    or (direction == "rise" and now > prev)
                    or (direction == "fall" and now < prev)):
                out.add(int(row.get("edge", -1)))
        prev = now
    out.discard(-1)
    return out


def after(trace: list[dict], activation: Pred, *, until: Pred | None = None,
          max_windows: int = 64, overlap: bool = False) -> list[Window]:
    """Every window the requirement applies over.

    A window opens on a RISING activation -- the first row where `activation`
    holds and the row before it did not -- so a condition true for forty
    consecutive edges is one window, not forty. It closes on the first row
    satisfying `until`, or on the last row where `activation` still holds when
    no `until` is given.

    THE ACTIVATION ROW IS NEVER TESTED FOR `until`. The scan for the close
    starts at the row AFTER the trigger, so a release condition that is already
    true when the window opens does not close it instantly -- which is what a
    reader means by "after A, until B" when A and B can hold together. The
    `until()` OPERATOR is the other half of this and takes the opposite default
    for the opposite reason: it asserts something INSIDE a window that already
    exists, so its release is tested from the first row it is given, and
    `after_activation=True` is how a caller excludes the trigger there. One
    rule, stated at both ends: *`after` defines the window and skips the trigger;
    `until` asserts within one and does not.*

    `overlap` CHANGES WHERE THE SCAN RESUMES, NOT WHAT COUNTS AS A START. The
    rising test above runs in both modes, so this is NOT SVA's attempt model --
    SVA opens an attempt at every tick the antecedent holds, and this opens one
    per rise, in both modes. See `docs/sva-divergence.md`, D4.
    """
    out: list[Window] = []
    i, n = 0, len(trace)
    while i < n and len(out) < max_windows:
        # A RISING activation, in both modes: a condition true for forty
        # consecutive rows opens one window, not forty. What `overlap` changes
        # is where the scan resumes, not what counts as a start.
        rising = activation(trace[i]) and (i == 0 or not activation(trace[i - 1]))
        if not rising:
            i += 1
            continue
        w = Window(start=trace[i], rows=[trace[i]], closed=False,
                   prev=trace[i - 1] if i else None)
        j = i + 1
        while j < n:
            w.rows.append(trace[j])
            if until is not None:
                if until(trace[j]):
                    w.closed = True
                    break
            elif not activation(trace[j]):
                w.closed = True
                break
            j += 1
        out.append(w)
        i = i + 1 if overlap else j + 1
    return out


def eventually(w: Window, holds: Pred, *, strong: bool = False,
               after_activation: bool = False,
               what: str = "the expected response") -> Verdict:
    """`holds` must be true at some row before the window closes.

    `s_eventually` VERSUS `eventually`, AND THE DEFAULT IS THE WEAK ONE.
    A window that ran off the end of the trace returns UNKNOWN, not False:
    nothing was seen to be wrong, we simply stopped looking. That is the
    distinction `verdict.truncated()` reconstructs from prose today.

    But a requirement that says the response MUST come is a strong liveness
    claim, and under weak semantics it can never be violated by this instrument
    -- only left undecided. Measured on a2-i2c: 11 of 105 requirements are
    phrased that way, and 5 of 14 abstaining checks abstained for exactly this
    reason ("had not occurred by the end of trace"). `strong=True` is
    `s_eventually`: running out of trace is a failure, because the obligation
    was never discharged.

    `after_activation` is `|=>` against `|->`. The window OPENS at the
    activation row, so a consequent that is already true there satisfies the
    default -- which is the vacuity this module exists to remove. Set it when
    the requirement says the effect FOLLOWS the trigger, which is most of them.

    BOTH FLAGS HAVE THE SAME BOUNDARY AND IT RUNS THE OTHER WAY. They exist
    because a check that cannot fail is worthless, and each converts an
    abstention into a conviction. On a requirement describing a STATE rather
    than an event -- "is high while X", "remains released" -- a correct design
    may hold the value from before the activation and never change it, and it
    may still be holding it when the trace ends. `strong=True` then convicts
    the design for the trace being short, and `after_activation=True` asks for
    a change the requirement never demanded. Neither flag is a default to
    reach for: each answers a question about the REQUIREMENT (does it oblige a
    response? does the effect follow the trigger?) and passing it without
    answering that question trades vacuity for over-strictness one check at a
    time.
    """
    rows = w.body if after_activation else w.rows
    for row in rows:
        if holds(row):
            return True, row.get("edge"), f"{what} occurred"
    if not w.closed:
        if strong:
            return False, w.edge, (
                f"{what} never occurred, and the window opening at edge "
                f"{w.edge} ran to the end of trace -- the obligation was never "
                f"discharged")
        return None, w.edge, (
            f"{what} had not occurred by the end of trace, and the window "
            f"opened at edge {w.edge} never closed")
    return False, w.edge, (
        f"{what} never occurred in the window opening at edge {w.edge}")


def throughout(w: Window, holds: Pred, *, after_activation: bool = False,
               what: str = "the invariant") -> Verdict:
    """`holds` must be true at EVERY row of the window.

    Fails on the first row that breaks it, and names that row -- an invariant
    is refuted by one counterexample, and the first is the one that explains
    the rest.

    `after_activation` excludes the activation row, for a requirement whose
    invariant begins once the trigger has happened rather than at it.

    AN EMPTY ROW SET IS UNKNOWN, NOT A PASS. `after_activation=True` on a
    one-row window leaves nothing to check, and returning `True` there is a
    vacuous pass -- the exact defect this module exists to remove, arriving
    through the operator meant to remove it. `stable` already guarded this and
    the three others did not; measured on c1-i2c, 39 of 110 oracles call
    `throughout` or `never` with `after_activation=`, so this was reachable by
    a third of the check set.
    """
    rows = w.body if after_activation else w.rows
    if not rows:
        return None, w.edge, (
            f"{what} had no rows to hold over in the window opening at edge "
            f"{w.edge}, so nothing was checked")
    for row in rows:
        if not holds(row):
            return False, row.get("edge"), (
                f"{what} broke at edge {row.get('edge')}, in the window opening "
                f"at edge {w.edge}")
    if not w.closed:
        return None, w.edge, (
            f"{what} held for every row seen, but the window opening at edge "
            f"{w.edge} ran to the end of trace without closing")
    return True, w.edge, f"{what} held throughout"


def stable(w: Window, port: str, *, after_activation: bool = False) -> Verdict:
    """`port` must not change anywhere in the window.

    The "held steady" shape, which on i2c is most of the `slave_wait` cluster:
    while the bus is stretched, `scl_oen` must not take its next phase-driven
    transition. Distinct from `throughout` because the value it must hold is
    whatever it happened to be, not one the requirement names.

    `after_activation` holds from the row AFTER the trigger, for a requirement
    whose steadiness begins once the trigger has happened rather than at it --
    which also makes the baseline value the one AFTER the activation settled,
    not the one it was caught mid-transition at.
    """
    rows = w.body if after_activation else w.rows
    if not rows:
        return None, w.edge, f"{port} had no rows to hold over"
    first = _val(rows[0], port)
    for row in rows[1:]:
        if _val(row, port) != first:
            return False, row.get("edge"), (
                f"{port} changed from {first} to {_val(row, port)} at edge "
                f"{row.get('edge')}, in the window opening at edge {w.edge}")
    if not w.closed:
        return None, w.edge, (
            f"{port} was steady for every row seen, but the window opening at "
            f"edge {w.edge} ran to the end of trace without closing")
    return True, w.edge, f"{port} stayed at {first} throughout"


def pulse(w: Window, port: str, *, active: int = 1, width: int = 1,
          after_activation: bool = False) -> Verdict:
    """`port` must go active for exactly `width` consecutive rows, once.

    i2c's `cmd_ack` is this and nothing else -- "asserts for one clk cycle to
    acknowledge completion" appears verbatim in several requirements. Written
    by hand it needs a rising-edge scan, a run-length count and a second-pulse
    check, and getting any of the three wrong produces a check that passes
    everything.
    """
    # WIDTH IS IN EDGES, AND ROWS ARE NOT EDGES. The trace an oracle sees is
    # state-compressed: consecutive edges with identical inputs AND outputs are
    # one entry carrying `held`. A one-edge pulse is therefore ONE row with
    # `held == 1`, and counting rows would call a 40-edge assertion a
    # single-cycle pulse. Summing `held` is the only reading that matches what
    # the requirement means by "for one clk cycle".
    rows = w.body if after_activation else w.rows
    if not rows:
        return None, w.edge, (
            f"{port} had no rows to pulse in, in the window opening at edge "
            f"{w.edge}, so nothing was checked")
    # A PULSE IS A RISE, AND THE EVIDENCE MUST SHOW ONE. If `port` is at
    # `active` on the first row considered AND the sample before it was ALSO
    # `active`, the transition happened before this window was looking: its
    # width is not measurable here, so the run is not a pulse this window
    # witnessed. Counting it anyway let a port stuck at `active` report
    # "pulsed once" -- verified on a window opening while `cmd_ack` was already
    # 1 and never rising inside it, which returned
    # `(True, 'cmd_ack pulsed once for 1 edge(s)')`. That is the check passing
    # the one design it exists to catch.
    #
    # THE PRECEDING SAMPLE DEPENDS ON THE MODE. Reading `w.rows`, it is
    # `w.prev` -- `$past` at the activation. Reading `w.body`, it is the
    # activation row itself, which `w.body` excluded but which was still
    # sampled. `None` means there is no preceding sample at all: the window
    # opens at the first row of the trace. That is NOT evidence of a missing
    # rise -- the design has just come out of reset and a port at its active
    # value there has genuinely just asserted -- so it is left alone, and only
    # positive evidence of "already active" abstains.
    before = w.start if after_activation else w.prev
    if _val(rows[0], port) == active and before is not None \
            and _val(before, port) == active:
        return None, w.edge, (
            f"{port} was already {active} before the window opening at edge "
            f"{w.edge}, so no rise was observed and the pulse width could not "
            f"be measured; open the window earlier, or put "
            f"`edges(trace, {port!r}, 'rise')` in the activation")
    runs: list[tuple[int, int]] = []
    run, began = 0, None
    for row in rows:
        if _val(row, port) == active:
            if not run:
                began = row.get("edge")
            run += int(row.get("held", 1) or 1)
        elif run:
            # The edge NAMED is where the pulse began, not where it ended. The
            # end row is the first one where the port is back at rest, and
            # pointing a reader there sends them to a row the pulse is not on.
            runs.append((run, began))
            run = 0
    if run:
        runs.append((run, began))
    if not runs:
        if not w.closed:
            return None, w.edge, (
                f"{port} had not pulsed by the end of trace, and the window "
                f"opening at edge {w.edge} never closed")
        return False, w.edge, (
            f"{port} never went to {active} in the window opening at edge "
            f"{w.edge}")
    if len(runs) > 1:
        return False, runs[1][1], (
            f"{port} pulsed {len(runs)} times in one window opening at edge "
            f"{w.edge}; exactly one was required")
    got, at = runs[0]
    if got != width:
        return False, at, (
            f"{port} was held at {active} for {got} edge(s), not {width}, in the "
            f"window opening at edge {w.edge}")
    return True, at, f"{port} pulsed once for {width} edge(s)"


def never(w: Window, holds: Pred, *, after_activation: bool = False,
          what: str = "the forbidden condition") -> Verdict:
    """`holds` must be true at NO row of the window -- SVA's `not`.

    `throughout(w, lambda r: not p(r))` says the same thing and reads as its
    own double negative. A requirement phrased "shall never" deserves an
    operator spelled the way the requirement is, so the transcription stays
    mechanical and the failure message says "occurred" rather than "the
    invariant broke".

    `after_activation` excludes the activation row, for a prohibition that
    begins once the trigger has happened -- "once a STOP is accepted, sda_oen
    must never fall again" says nothing about the row the STOP arrived on.

    AN EMPTY ROW SET IS UNKNOWN, NOT A PASS -- see `throughout`, which shares
    the defect and the reasoning. "It never happened" over zero rows is not
    evidence that it never happens.
    """
    rows = w.body if after_activation else w.rows
    if not rows:
        return None, w.edge, (
            f"{what} had no rows to occur in, in the window opening at edge "
            f"{w.edge}, so nothing was checked")
    for row in rows:
        if holds(row):
            return False, row.get("edge"), (
                f"{what} occurred at edge {row.get('edge')}, in the window "
                f"opening at edge {w.edge}")
    if not w.closed:
        return None, w.edge, (
            f"{what} was not seen, but the window opening at edge {w.edge} ran "
            f"to the end of trace without closing")
    return True, w.edge, f"{what} never occurred"


def nexttime(w: Window, holds: Pred, *, after_activation: bool = True,
             what: str = "the expected response") -> Verdict:
    """`holds` at the row immediately after the activation -- SVA `##1`.

    `after_activation` IS WHAT THIS OPERATOR ALREADY IS, and it is accepted so
    the schema-derived value can be passed through mechanically to whichever
    operator a requirement needs. `##1` evaluates at `w.body[0]`, which is the
    row after the trigger -- so `True` is what it already does, and the
    parameter changes nothing. It defaults to True for that reason, rather than
    to the False the other operators default to.

    Passing `False` does NOT move the evaluation onto the activation row: that
    would be `##0`, which is not `nexttime` but a plain predicate at the
    trigger, and an operator that silently became a different operator on a
    keyword would be worse than one that ignores it. The value is recorded in
    the detail so a reader who passed it can see it was not honoured, rather
    than finding a check that quietly answered a different question.

    ORDERING, NOT A CYCLE COUNT, and the difference is the whole reason this
    one is admissible while `##[2:5]` is not. A row is a STATE: consecutive
    edges with identical inputs and outputs collapse into one. So "the next
    row" means "the next time anything changed", which is what "then" means in
    a specification -- not "one clock later", which the specification does not
    state and Phases 3-6 stopped this pipeline from asserting.
    """
    body = w.body
    if not body:
        return None, w.edge, (
            f"nothing follows the activation at edge {w.edge}; the trace ends "
            f"there, so {what} could not be observed either way")
    # NEVER SILENT. `##1` is defined at the row after the trigger, so the
    # caller's `False` cannot be honoured without making this a different
    # operator -- say so in the verdict rather than answering a question the
    # caller did not ask.
    note = ("" if after_activation else
            "; `after_activation=False` was passed and ignored -- `nexttime` "
            "is `##1` and is defined at the state after the activation")
    row = body[0]
    if holds(row):
        return True, row.get("edge"), f"{what} occurred at the next state{note}"
    return False, row.get("edge"), (
        f"{what} did not hold at the state after edge {w.edge}{note}")


def sequence(w: Window, *steps: Pred, strong: bool = False,
             after_activation: bool = False,
             what: str = "the sequence") -> Verdict:
    """The steps must occur IN ORDER within the window -- SVA `a ##[1:$] b`.

    Each step matches at a row strictly after the previous step's, so this is
    the count-free form: `##[1:$]` between every pair, never `##[2:5]`. What it
    adds over a conjunction of `eventually` calls is exactly the ordering, and
    that is the whole point -- three `eventually`s pass a design that does the
    three things backwards.

    Only 5 of a2-i2c's 105 requirements name an ordered multi-step sequence,
    because bit-level i2c is deliberately low-level. A byte-level or
    protocol-level design is dominated by them, which is why this is here
    before it is needed rather than after.

    Names the step that stalled, because "the sequence did not complete" sends
    a reader to re-read the whole check.

    `after_activation` starts matching at the row AFTER the trigger, so step 1
    cannot be satisfied by the activation row itself -- the same vacuity
    `eventually` guards against, one operator along.
    """
    if not steps:
        return None, w.edge, "no steps given, so there is nothing to decide"
    rows = w.body if after_activation else w.rows
    at = 0
    for n, step in enumerate(steps):
        while at < len(rows) and not step(rows[at]):
            at += 1
        if at >= len(rows):
            if not w.closed and not strong:
                return None, w.edge, (
                    f"{what} reached step {n + 1} of {len(steps)} and the "
                    f"window opening at edge {w.edge} ran to the end of trace")
            return False, w.edge, (
                f"{what} stalled at step {n + 1} of {len(steps)}, in the "
                f"window opening at edge {w.edge}")
        at += 1
    return True, w.edge, f"{what} completed all {len(steps)} steps in order"


def until(w: Window, holds: Pred, release: Pred, *, strong: bool = False,
          after_activation: bool = False,
          what: str = "the condition") -> Verdict:
    """`holds` at every row until `release` occurs -- SVA `until` / `s_until`.

    Distinct from `after(..., until=)`, which DEFINES the window. This asserts
    something about the rows inside one: "SCL stays low until the divider
    ticks" is `until`, where "while SCL is low" is the window.

    Weak, like SVA's: if `release` never occurs, holding throughout is enough.
    `strong=True` is `s_until` and additionally requires the release to happen
    -- reach the end without it and the obligation was never discharged.

    `after_activation` starts at the row after the trigger, for the common
    shape where the release condition is ALREADY true at the activation and
    would otherwise discharge the obligation instantly.

    THE TRIGGER ROW IS TESTED BY DEFAULT HERE, AND SKIPPED BY DEFAULT IN
    `after(..., until=)`. Both are right and the difference is what each word
    is doing: `after`'s `until` DEFINES the window, so a release already true
    at the trigger must not collapse it to nothing; this `until` ASSERTS inside
    a window someone else defined, so it reads every row it is handed and
    `after_activation=True` is how a caller excludes the trigger. Stated at both
    ends because two operators spelled the same way, differing silently, is how
    a check ends up answering a question nobody asked.

    IT IS SVA'S `until`, NOT `until_with`: `holds` need not be true on the row
    where `release` fires, because `release` is tested first. There is no
    `until_with` here -- see `docs/sva-divergence.md`, D8.
    """
    for row in (w.body if after_activation else w.rows):
        if release(row):
            return True, row.get("edge"), (
                f"{what} held until the release at edge {row.get('edge')}")
        if not holds(row):
            return False, row.get("edge"), (
                f"{what} broke at edge {row.get('edge')}, before any release, "
                f"in the window opening at edge {w.edge}")
    if strong:
        return False, w.edge, (
            f"{what} held, but the release never occurred in the window "
            f"opening at edge {w.edge}")
    if not w.closed:
        return None, w.edge, (
            f"{what} held for every row seen, but the window opening at edge "
            f"{w.edge} ran to the end of trace without a release")
    return True, w.edge, f"{what} held and was never released"


def first_match(windows: list[Window]) -> list[Window]:
    """Only the first window -- SVA `first_match`.

    For a requirement about the FIRST time something happens ("the first
    filtered SCL rising edge after reset samples dout"), where folding every
    later occurrence in with `worst` would convict the design for behaviour the
    requirement says nothing about.

    A list rather than one window so it drops into the same comprehension the
    other operators are used from, and so an empty trace stays empty rather
    than becoming `None` for a caller to special-case.
    """
    return windows[:1]


def worst(verdicts: list[Verdict]) -> Verdict:
    """Fold many window verdicts into one, failure first.

    A requirement holding on nine windows and breaking on the tenth is broken,
    and an UNKNOWN outranks a pass for the same reason `_worst` gives one level
    up: a grown evidence set only ever moves a verdict toward worse, so nothing
    can be laundered by adding more of it.

    ON THE ALL-PASSING PATH THE LAST VERDICT IS RETURNED, not the first. The
    failing and unknown paths name the EARLIEST offending window, because the
    first counterexample is the one that explains the rest. A pass has no
    counterexample, so the useful thing to name is the furthest the evidence
    reached -- returning the first window told a reader the requirement held at
    the earliest place it could have, which reads as much weaker evidence than
    was actually gathered.

    EMPTY IS AN ABSTENTION, AND IT DIFFERS FROM SVA DELIBERATELY. `a |-> b`
    with no matching `a` is a VACUOUS PASS in SVA and only `cover property`
    reports the miss. Here it is UNKNOWN, because this pipeline keeps "could
    not answer" separate from a verdict at every gate and a vacuous pass is a
    false green. See `docs/sva-divergence.md`, D1.
    """
    if not verdicts:
        return None, None, "the activation never occurred"
    for ok, edge, detail in verdicts:
        if ok is False:
            return False, edge, detail
    for ok, edge, detail in verdicts:
        if ok is None:
            return None, edge, detail
    return verdicts[-1]
