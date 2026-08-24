"""The mechanical verdict for one requirement, and the party it accuses.

`RequirementVerdict.verdict` (`judge.py:58`) is an OPINION -- what one judge
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
    "NOT_EXERCISED",   # activation never fired
    "UNOBSERVABLE",    # no boundary observable exists -- a spec defect
    "ORACLE_INVALID",  # the check is wrong: over-strict, malformed, or self-contradicting
    "VACUOUS",         # the check demands nothing
    "UNDECIDED",       # nothing decided it, or the retry budget ran out
    "AMBIGUOUS",       # TRANSITIONAL -- the judge could not determine
]

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


def to_issue(req_uid: str, v: str, detail: str = ""):
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
    return Issue("error", f"refmodel.{req_uid}.{v.lower()}", message)


def issues(verdicts: dict[str, str], details: dict[str, str] | None = None) -> list:
    """Every blocking verdict as an `Issue`, in requirement order.

    The list `has_errors` reads, so a caller can gate on mechanical verdicts
    exactly as it gates on the judge's today -- which is the one piece of wiring
    that stands between the isolated oracle set and driving the loop.
    """
    out = []
    for uid in sorted(verdicts):
        issue = to_issue(uid, verdicts[uid], (details or {}).get(uid, ""))
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
