"""[M] Is the frozen oracle set adequate for the model that is about to ship?

`qualify.py:3-22` states the argument this rests on: a suite can cover every
testpoint and still be unable to fail. Satisfying every oracle is the same
claim one level down -- it means something only if the oracles could have
failed the design they just passed.

**Why this runs AFTER the debug loop, not inside it.** `trust.sensitivity` asks
the same question and has to guard itself with "only meaningful for an oracle
that currently PASSES", because one already failing the model has demonstrated
it fires. Inside the loop that guard biases the sample to whatever the broken
model happens to satisfy, and worse, it re-derives its mutants from the CURRENT
source -- so the answer moves as the agent edits. Measured: VACUOUS wandered
16 -> 18 -> 16 on a run whose oracle set was frozen throughout.

After the loop, every trusted oracle passes by construction. All of them are
eligible, none of them needs a guard, and the model is not going to change
underneath the answer. The question is finally the clean one: *this* design is
about to be shipped as the reference for a whole verification suite -- would
these checks have noticed if it were wrong?

A survivor is a finding about the ORACLE, never about the model. It says the
design could be broken in a way this requirement's check would not see, which
is a reason to strengthen the check, and the counterexample is in hand.
"""

from __future__ import annotations

import json
from pathlib import Path

from . import mutate_model
from .oracles import (
    RequirementOracle,
    decide,
    ports_read,
    replay,
    transactional_view,
)
from .trust import MIN_IN_SCOPE, _project, _steps_for

#: Mutants tried per oracle. Bounded for the same reason gate 2 bounds it: the
#: evidence saturates, and an oracle that survives eight in-scope mutants is not
#: going to be convicted by a ninth.
MUTANT_LIMIT = 8

ADEQUATE = "adequate"
INADEQUATE = "inadequate"
UNKNOWN = "unknown"


def adequacy_of(
    oracle: RequirementOracle,
    source: str,
    contract: dict,
    stimulus_by_tp: dict[str, list[dict]],
    *,
    base: str,
    limit: int = MUTANT_LIMIT,
    transactional: bool = True,
) -> tuple[str, str]:
    """`(verdict, detail)` for one oracle against the final model.

    Two filters, and they exclude different things: sites are restricted to
    lines this stimulus actually EXECUTES, so a mutant the scenario could never
    reach is never proposed; and a mutant counts only if it changes the trace
    PROJECTED onto the ports this oracle reads, so one that changes behaviour
    this clause is not about is dropped. The second subsumes the
    equivalent-mutant problem `qualify.py:67` names for G8.
    """
    steps = _steps_for(oracle, stimulus_by_tp)
    if not steps:
        return UNKNOWN, "no stimulus to mutate against"

    ports = ports_read(oracle, contract)
    if not ports:
        return UNKNOWN, "the oracle reads no declared port"

    baseline = replay(source, contract, steps, base=base)
    if baseline.error:
        return UNKNOWN, f"the model {baseline.error}"
    reference = _project(baseline.rows, ports)

    lines = mutate_model.executed_lines(source, contract, steps, base=base)
    in_scope = 0
    survivor = ""
    for mutant in mutate_model.mutants(source, lines=lines, limit=limit):
        run = replay(mutant.source, contract, steps, base=base)
        if run.error:
            # A mutant that breaks the model outright tests nothing about the
            # oracle -- every oracle "fails" a model that will not run.
            continue
        if _project(run.rows, ports) == reference:
            continue                     # invisible to this clause: not evidence
        in_scope += 1
        rows = transactional_view(run.rows) if transactional else run.rows
        if not decide(oracle, rows).failed():
            survivor = survivor or mutant.description
    if in_scope < MIN_IN_SCOPE:
        return UNKNOWN, (
            f"only {in_scope} mutant(s) changed anything this oracle can see; "
            f"{MIN_IN_SCOPE} are needed before silence means inadequacy")
    if survivor:
        return INADEQUATE, f"survived {survivor}"
    return ADEQUATE, f"caught every one of {in_scope} mutants it could observe"


def assess(
    oracles: list[RequirementOracle],
    source: str,
    contract: dict,
    stimulus_by_tp: dict[str, list[dict]],
    *,
    base: str,
    limit: int = MUTANT_LIMIT,
    transactional: bool = True,
) -> dict[str, tuple[str, str]]:
    """`{req_uid: (verdict, detail)}` over the whole trusted set."""
    return {
        o.req_uid: adequacy_of(o, source, contract, stimulus_by_tp,
                               base=base, limit=limit,
                               transactional=transactional)
        for o in oracles
    }


def inadequate(report: dict[str, tuple[str, str]]) -> dict[str, str]:
    """The oracles a strengthening round should be spent on, and why."""
    return {uid: detail for uid, (level, detail) in report.items()
            if level == INADEQUATE}


def write(run_dir: Path, report: dict[str, tuple[str, str]], round_: int = 0) -> Path:
    """Reported, not gated. Its rate has to be measured before it decides anything."""
    path = Path(run_dir) / "specflow" / f"adequacy_r{round_}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    counts: dict[str, int] = {}
    for level, _ in report.values():
        counts[level] = counts.get(level, 0) + 1
    path.write_text(json.dumps({
        "counts": counts,
        "by_requirement": {u: {"verdict": v, "detail": d}
                           for u, (v, d) in sorted(report.items())},
    }, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


