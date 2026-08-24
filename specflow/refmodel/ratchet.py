"""I6: a requirement that was once exercised must not stop being exercised.

The hazard is specific and it is on the MODEL side. Appending stimulus cannot
lose coverage -- nothing existing is edited, and `_worst` ranks a failure above
anything a new testpoint could add -- so the stimulus side needs no ratchet at
all. But whether a scenario occurs is a joint property of the stimulus and the
design: a state-dependent activation fires only if the model enters the state,
so an edit that stops it entering the state un-fires an activation the stimulus
still drives, and the oracle goes from VIOLATES to NOT_EXERCISED.

That is a strictly worse outcome scored as a better one. `session.failing()`
counts `ok is False` and not `ok is None`, so the failing count DROPS, and
before `distance()` was fixed `note_best` recorded it as a new best -- making a
requirement unverifiable scored as fixing it.

`distance()` closes it inside one session. This closes it ACROSS turns and
across iterations, where no session state survives: the record of what has ever
been exercised lives in a file, in `freeze_denominator`'s style
(`specflow/coverage.py:74`) -- written at entry, only ever grown, never rewritten
downward.

What it buys is attribution rather than blocking. NOT_EXERCISED already blocks,
and it already routes to the stimulus. But a requirement whose scenario fired in
an earlier turn and does not fire now has nothing wrong with its stimulus: the
stimulus is unchanged and it worked. The party that changed is the model, and
the ratchet is the only thing that knows the difference.
"""

from __future__ import annotations

import json
from pathlib import Path

from ..schema import Issue

#: The verdicts that mean the clause's scenario actually occurred. Everything
#: else -- NOT_EXERCISED, and every verdict about the ORACLE rather than the
#: run -- says nothing about whether the design reached the state, so none of
#: them may enter or leave the ratchet.
EXERCISED = frozenset({"CONFORMS", "VIOLATES"})

#: Only this verdict can be a regression. An oracle that became ORACLE_INVALID
#: or VACUOUS stopped deciding for a reason that has nothing to do with the
#: design reaching a state, and blaming the model for it would send the repair
#: loop after code that may be perfectly correct.
LOST = "NOT_EXERCISED"


def read(path: Path | str) -> set[str]:
    path = Path(path)
    if not path.exists():
        return set()
    try:
        blob = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return set()
    return set(blob.get("exercised") or [])


def note(path: Path | str, verdicts: dict[str, str]) -> list[str]:
    """Record what is exercised now; return what STOPPED being exercised.

    Monotone by construction: the file is the union of everything ever seen, so
    a turn cannot shrink it and an agent cannot shrink it by any route. The
    return value is the interesting half -- the requirements this turn lost.
    """
    path = Path(path)
    seen = read(path)
    now = {uid for uid, v in verdicts.items() if v in EXERCISED}
    lost = sorted(uid for uid in seen - now if verdicts.get(uid) == LOST)

    grown = seen | now
    if grown != seen or not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"exercised": sorted(grown)}, indent=2) + "\n",
            encoding="utf-8")
    return lost


def issues(lost: list[str]) -> list[Issue]:
    """One blocking issue naming the MODEL, beside the untouched verdicts.

    The verdict stays NOT_EXERCISED, because that is what happened: the oracle
    saw nothing. Rewriting it to VIOLATES would route correctly and report
    falsely -- the oracle did not fail, it went silent -- and this codebase does
    not buy a route with a lie. So the route arrives as a second issue instead,
    and both are true at once: the stimulus staged nothing this turn, and the
    reason it staged nothing is an edit.
    """
    if not lost:
        return []
    return [Issue(
        "error", "refmodel.exercised",
        f"{len(lost)} requirement(s) stopped being exercised by stimulus that "
        f"has not changed: {', '.join(lost)}. The scenario occurred in an "
        f"earlier turn and does not now, and stimulus is append-only, so what "
        f"changed is the design: it stopped reaching the state. Restore that "
        f"first. An unverifiable requirement is worse than a failing one, not "
        f"better -- and the failing count going down because a scenario "
        f"stopped occurring is not progress.")]
