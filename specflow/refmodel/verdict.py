"""The mechanical verdict for one requirement, and the party it accuses.

The judge's `verdict` field was an OPINION -- what one reader
concluded from reading the model. This is a different object: the outcome of
screening, computed from evidence, with a remediation route attached. The two
coexist for now; only this one is derived from something that ran.

Why it exists. `trust.screen` already distinguishes unexercised from over-strict
from vacuous, and buries the distinction in prefix-matched strings inside
`Screened.discarded` (`trust.py:106-121`) that nothing downstream reads. Blocking
meanwhile is opinion-only -- `blocks` is `self.verdict in BLOCKING`
(`judge.py:98`) and `to_issue` never looks at the oracle -- so a requirement
whose oracle was discarded still blocks, and reaches the model agent as prose it
cannot act on. On `f-i2c` r0 that was 30 requirements: every one of them had a
known cause, and none of the causes survived to anywhere that could act.

So the value here is not the vocabulary. It is that each verdict names WHO must
fix it, which is what turns 30 unrouteable blocks into 30 routed ones.

NAMING. `NOT_EXERCISED` here is not `schema.TestpointStatus.NOT_EXERCISED`.
That one means "the cocotb test produced no record" (`run.py:81-88`,
`gate.py:73`) -- a testpoint that did not run. This one means "the clause's
activation condition never occurred in the stimulus" -- a testpoint that ran
fine and did not stage the scenario. Two different claims; the older name is
left alone because renaming it would migrate the on-disk results schema for a
cosmetic gain.
"""

from __future__ import annotations

from typing import Literal

#: Seven mechanical outcomes plus one transitional. `AMBIGUOUS` exists only
#: while the judge still forms opinions; it is retired when verdicts stop being
#: an LLM's output at all, because there is then nothing left to be undetermined
#: about.
Verdict = Literal[
    "CONFORMS",        # activation fired, oracle passed
    "VIOLATES",        # activation fired, oracle failed
    "NOT_EXERCISED",   # the stimulus loop DID NOT RUN -- see ABANDONED
    "UNOBSERVABLE",    # the resolution pass DID NOT RUN -- see ABANDONED
    "ORACLE_INVALID",  # the check is wrong: over-strict, malformed, or self-contradicting
    "VACUOUS",         # the check demands nothing
    "UNDECIDED",       # nothing decided it, or the retry budget ran out
    "ABANDONED",       # WE could not interpret this requirement -- see below
    "AMBIGUOUS",       # TRANSITIONAL -- the judge could not determine
]

#: WHAT `ABANDONED` CLAIMS, and why it is phrased about us.
#:
#: `UNOBSERVABLE` and `NOT_EXERCISED` are claims about the REQUIREMENT -- that no
#: port shows it, that no stimulus reaches it. Both can be false, and one of them
#: has been measured false at scale: normalisation called 27 of 77 requirements
#: unobservable by reading each one's MECHANISM rather than its effect, and 10 of
#: the 27 already had working checks against real output ports.
#:
#: What is actually known after a bounded attempt is narrower and is about the
#: pipeline: WE COULD NOT TURN THIS REQUIREMENT INTO A CHECK WE CAN EXERCISE.
#: That is what this verdict says, and `abandoned_reason` says which attempt ran
#: out. A disposition that blames the specification for our failure to read it is
#: a claim the evidence does not support.
#:
#: An abandoned requirement LEAVES THE SYSTEM: it is not frozen into the driving
#: set, so the debug loop cannot decide it, `run_all` cannot count it, and the
#: board cannot show it. That is what separates it from a downgraded verdict,
#: which stays in the way while no longer blocking.
#:
#: Two rules stop it becoming a lie, both enforced by the stage that emits it:
#: it leaves the DENOMINATOR of every reported rate, counted beside that rate;
#: and coverage stops claiming it, or the suite reports a requirement covered
#: while nothing checks it.
ABANDONED_REASONS: frozenset[str] = frozenset({
    "no observation route found",      # the indirect-resolution pass came back empty
    "never reached",                   # the stimulus loop exhausted its attempts
    "no check survived repair",        # the oracle repair loop exhausted its rounds
})

#: Who each verdict accuses, and therefore where a repair round should go. This
#: is the whole point of the enum: today every blocking verdict routes to the
#: reference-model agent regardless of cause, so a thin testplan and a wrong
#: model produce the same instruction.
ROUTE: dict[str, str] = {
    "CONFORMS": "none",
    "VIOLATES": "fix the implementation",
    "NOT_EXERCISED": "fix the stimulus",
    "UNOBSERVABLE": "return to spec authoring",
    "ORACLE_INVALID": "regenerate the oracle",
    "VACUOUS": "regenerate the oracle",
    "UNDECIDED": "triage manually",
    # Nobody. That is the point: the attempt ran and ran out, so there is no
    # party left with a move. It is reported, counted, and not handed to anyone.
    "ABANDONED": "none -- reported, not routed",
    "AMBIGUOUS": "triage manually",
}

#: Verdicts that must not reach acceptance. `CONFORMS` is the only clean one.
#: `UNOBSERVABLE` blocks too: a requirement with no observable at the boundary
#: is a hole in the specification, and letting it through is exactly the silent
#: omission this pipeline exists to prevent -- it just routes to a human rather
#: than to an agent.
BLOCKING: frozenset[str] = frozenset(set(ROUTE) - {"CONFORMS"})


#: How a `Screened.discarded` reason maps onto a verdict. Prefix-matched because
#: that is the shape `trust.py` already writes; the prefixes are its own.
_DISCARD_PREFIX: tuple[tuple[str, str], ...] = (
    ("unexercised:", "NOT_EXERCISED"),
    # The MODEL raised mid-replay. The check never got to be wrong, and the
    # design falling over is the cheapest way to make every oracle stop
    # complaining -- so this must reach the party that edited it.
    ("model-broke:", "VIOLATES"),
    ("vacuous:", "VACUOUS"),
    ("over-strict:", "ORACLE_INVALID"),
    ("malformed:", "ORACLE_INVALID"),
    # The check decides something other than the requirement it names. A
    # perfectly well-formed, satisfiable, non-vacuous check of the wrong thing
    # is still a check that cannot discharge this requirement, so it goes back
    # to the party that wrote it.
    ("off-target:", "ORACLE_INVALID"),
    # The oracle contradicts the verdict it shipped with. In the target there is
    # no opinion for it to contradict, so this case disappears; until then the
    # oracle is the thing that cannot be trusted, which is ORACLE_INVALID.
    ("disagreed:", "ORACLE_INVALID"),
)


def of_discard(reason: str) -> str:
    """The verdict a discard reason implies. Unknown prefixes are `UNDECIDED`."""
    for prefix, verdict in _DISCARD_PREFIX:
        if reason.startswith(prefix):
            return verdict
    return "UNDECIDED"


#: Wording an oracle uses when it fails by running out of trace rather than by
#: seeing something wrong. Matched on the DETAIL because the oracle's own
#: `decide` is the only thing that knows it was waiting -- there is no separate
#: signal for "I was still expecting something".
#:
#: Prefix-free substrings, deliberately: an oracle writes this sentence itself
#: and no format is imposed on it, so anchoring would miss most of them.
_TRUNCATED: tuple[str, ...] = (
    "end of trace",
    "before the end of the trace",
    "never asserted",
    "never settled",
    "never returned",
    "no later ",
    "did not complete",
)


def truncated(detail: str) -> bool:
    """Did this oracle fail by REACHING THE END rather than by seeing a defect?

    An oracle asserting "eventually X" against a finite trace has two ways to
    come back False, and they belong to different parties. If X happened and was
    wrong, that is the design. If the trace simply stopped first, that is the
    STIMULUS, and reporting it as `VIOLATES` sends the model agent after an edit
    that cannot exist.

    Measured on w-i2c: of the 15 oracles a KNOWN-GOOD control fails, **seven**
    fail this way -- `"al never asserted before end of trace"`, `"never returned
    both lines to released idle"`. REQ-0066 fails on the LAST EDGE of its trace
    (210 of 210) and REQ-0025 three edges from the end. Those seven are the
    single largest reason the debug loop spent its whole budget without
    converging.

    WORDING ONLY, and an "it failed on the last edge" heuristic was TRIED AND
    REMOVED. It cannot distinguish "the trace ran out while I waited" from "the
    defect happened to be at the end", and it silently reclassified a real
    violation: a fixture whose model drives `y` high on the final row, which the
    oracle correctly failed, came back `NOT_EXERCISED`. That is exactly the
    reclassification-to-flatter-the-numbers this must not do, so the weaker
    signal loses even though it costs two of the seven -- REQ-0066 and REQ-0025
    are no longer caught here.

    What survives is the only evidence that actually separates the two cases:
    absence versus observation. An oracle that ran out of trace says so, because
    it has to describe what it never saw.
    """
    return any(mark in (detail or "").lower() for mark in _TRUNCATED)


def of_result(result) -> str:
    """The verdict one decided oracle implies. Three outcomes, no more.

    This is what a turn of the debug loop may conclude once the oracle set
    arrives verified: the design honoured the clause, broke it, or never met
    it. Everything else the enum can say -- the check is wrong, the check
    demands nothing, the requirement has no observable -- was settled by the
    oracle stage before the model existed, and a loop that could re-derive
    those would be re-deriving them against a model it is itself editing. That
    is the measured failure: VACUOUS wandered 16 -> 18 -> 16 with the oracle
    set frozen, because a gate kept re-asking under a moving design.

    A model that raised is `VIOLATES`, not a defect in the check: the oracle
    could not decide because the design fell over, and the party that changed
    it is the one to tell.
    """
    if result.model_broke:
        return "VIOLATES"
    if result.broken:
        # A verified oracle that breaks anyway decided nothing, and nothing
        # here can say why. It is not the model's to answer.
        return "UNDECIDED"
    if result.ok is True:
        return "CONFORMS"
    if result.ok is False:
        # A failure that is really the trace running out is a fact about the
        # STIMULUS, and `NOT_EXERCISED` is the verdict that routes there. This
        # is a reclassification, so it is allowed only because the property is
        # computable from the run -- see `truncated`.
        if truncated(getattr(result, "detail", "") or ""):
            return "NOT_EXERCISED"
        return "VIOLATES"
    return "NOT_EXERCISED"


def classify(
    *,
    discarded: dict[str, str],
    passing: set[str] | frozenset[str],
    failing: set[str] | frozenset[str],
    had_oracle: set[str] | frozenset[str],
    requirements: list[dict],
) -> dict[str, str]:
    """One verdict per requirement, from evidence rather than from an opinion.

    `passing`/`failing` are the trusted oracles' decisions against the model.
    `had_oracle` is every requirement the judge wrote an oracle for at all --
    needed because "the judge produced no oracle" and "the oracle was discarded"
    are different failures, and only the second has a named cause.

    Every requirement gets a verdict, including ones nothing decided. That is
    the property worth having: a requirement absent from this map would be a
    silent subset, which is the failure mode the whole enum exists to remove.
    """
    out: dict[str, str] = {}
    for req in requirements:
        uid = str(req.get("uid") or "")
        if not uid:
            continue
        if uid in failing:
            out[uid] = "VIOLATES"
        elif uid in passing:
            out[uid] = "CONFORMS"
        elif uid in discarded:
            out[uid] = of_discard(discarded[uid])
        elif uid in had_oracle:
            # An oracle that survived screening but decided nothing -- it named
            # no testpoint with stimulus, or its replay could not run. Not a
            # cause anyone can act on, which is what UNDECIDED means.
            out[uid] = "UNDECIDED"
        else:
            out[uid] = "UNDECIDED"
    return out


#: Verdicts a caller may downgrade from `error` to `warning`.
#:
#: ONLY `ABANDONED`, and the restriction is the point. Every other blocking
#: verdict accuses someone who can act -- the model, the stimulus, the oracle
#: author -- so downgrading it would let a build pass with work outstanding that
#: something in this pipeline was about to do. `ABANDONED` is the one where the
#: work was done: a bounded attempt ran, exhausted itself, and recorded what it
#: tried. `ROUTE` sends it nowhere because there is nowhere left to send it.
#:
#: THE SOFTENING MUST BE EARNED. `ABANDONED` is emitted only by a stage that ran
#: an attempt and carries the record proving it, so it cannot be reached by
#: skipping the work. That is why `UNOBSERVABLE` and `NOT_EXERCISED` are NOT
#: here any more: reaching either now means the resolution pass or the stimulus
#: loop did not run, which is a harness defect and exactly what should halt a
#: build. Without that split the gate rewards not trying -- measured on z-i2c,
#: which reported `stimulus_added: 0` on all three turns while 33 oracles sat at
#: `NOT_EXERCISED`, with nothing in the artifact distinguishing "staged four
#: times, never reached" from "nobody tried".
#:
#: Measured, which is why this exists at all: on s-i2c the reference-model gate
#: failed with 34 issues of which only 9 were the loop's. Seven could not be
#: cleared by any amount of debugging, so the build halted permanently on
#: something no turn of any loop would ever fix.
#:
#: What a downgrade does NOT do is hide it. The requirement stays in
#: `dispositions` with its reason, is counted on the face of the gate, and
#: leaves the denominator of every rate rather than quietly passing. The
#: objection is to SILENT omission; an itemised warning that names the
#: requirement and what was attempted is the opposite of silent.
#:
#: `UNOBSERVABLE` CAME OUT WHEN THE RESOLUTION PASS LANDED. It was here while
#: nothing could give a blind requirement a route to try, because removing it
#: then would have enforced no principle and merely halted builds on
#: requirements nothing could resolve -- the exact s-i2c failure the downgrade
#: was added to fix. `normalize.resolve_indirect` now asks every one of them
#: whether the behaviour is visible through another requirement's port, so a
#: requirement that still has none has been ASKED, and the honest disposition
#: for it is `ABANDONED`, not a softened claim that no port shows it.
DOWNGRADABLE: frozenset[str] = frozenset({"ABANDONED"})


def to_issue(req_uid: str, v: str, detail: str = "", *,
             advisory: frozenset[str] | set[str] = frozenset()):
    """One `Issue` per blocking verdict, naming the party that must act.

    This is what `judge.to_issue` (`judge.py:708`) does for an OPINION, and the
    difference is the whole point of the enum. The judge's issue says what one
    reader concluded and hands every one of them to the reference-model agent,
    whatever the cause -- so a thin testplan and a wrong model arrive as the same
    instruction. This one carries the route, so `NOT_EXERCISED` reads as "fix the
    stimulus" and cannot be mistaken for an accusation against the model.

    Returns None for `CONFORMS`, mirroring `judge.to_issue` returning None for
    `met`: the acceptance asymmetry is unchanged, and nothing here certifies
    anything. What certifies is the must-pass/must-fail gates and the suite.
    """
    from ..schema import Issue

    if v not in BLOCKING:
        return None
    route = ROUTE.get(v, "triage manually")
    message = f"{v}: {route}"
    if detail.strip():
        message += f" -- {detail.strip()}"
    severity = "warning" if v in (set(advisory) & DOWNGRADABLE) else "error"
    return Issue(severity, f"refmodel.{req_uid}.{v.lower()}", message)


def issues(verdicts: dict[str, str], details: dict[str, str] | None = None,
           *, advisory: frozenset[str] | set[str] = frozenset()) -> list:
    """Every blocking verdict as an `Issue`, in requirement order.

    The list `has_errors` reads, so a caller can gate on mechanical verdicts
    exactly as it gates on the judge's today -- which is the one piece of wiring
    that stands between the isolated oracle set and driving the loop.
    """
    out = []
    for uid in sorted(verdicts):
        issue = to_issue(uid, verdicts[uid], (details or {}).get(uid, ""),
                         advisory=advisory)
        if issue is not None:
            out.append(issue)
    return out


def counts(verdicts: dict[str, str]) -> dict[str, int]:
    """Every verdict counted, including the zeroes.

    Zeroes are kept deliberately. `over_strict: 0` once meant "never looked" and
    read as "none found" (`trust.py:99-104`); a key that appears only when
    non-zero repeats that mistake one level up.
    """
    out = {v: 0 for v in ROUTE}
    for verdict in verdicts.values():
        out[verdict] = out.get(verdict, 0) + 1
    return out


def blocking(verdicts: dict[str, str]) -> list[str]:
    return sorted(uid for uid, v in verdicts.items() if v in BLOCKING)
