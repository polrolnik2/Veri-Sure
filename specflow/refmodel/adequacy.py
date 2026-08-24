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
    decide_all,
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
    scope: set[str] | frozenset[str] | None = None,
) -> tuple[str, str]:
    """`(verdict, detail)` for one oracle against the final model.

    Two filters, and they exclude different things: sites are restricted to
    lines this stimulus actually EXECUTES, so a mutant the scenario could never
    reach is never proposed; and a mutant counts only if it changes the trace
    PROJECTED onto the ports this oracle reads, so one that changes behaviour
    this clause is not about is dropped. The second subsumes the
    equivalent-mutant problem `qualify.py:67` names for G8.

    `scope` overrides the ports that second filter projects onto. The default is
    `ports_read`, which is a STRING SCAN and therefore counts a port the oracle
    only triggers on -- measured on the frozen 70, 39% of the ports it projects
    through carry no assertion at all (`liveness.assertion_ports` computes the
    real set). A mutant visible only in a trigger port is one this oracle could
    never have caught, and counting it toward `MIN_IN_SCOPE` spends the evidence
    budget on questions the oracle was not asked.

    MEASURED, AND IT DOES NOT HELP -- the default stays `ports_read`. On the
    frozen 70:

        ports_read        adequate 6 · inadequate 20 · unknown 44
        assertion ports   adequate 6 · inadequate 18 · unknown 46

    Two verdicts moved and both went `inadequate` -> `unknown`. The mechanism is
    the one stated above and it forces this direction: narrowing the filter can
    only REDUCE `in_scope`, so it pushes oracles below `MIN_IN_SCOPE` rather
    than resolving them. The premise was right -- 39% of the ports projected
    through carry no assertion -- and the expected consequence was backwards.

    What that says is where the real limit is. Adequacy's 44 UNKNOWNs are a
    MUTANT SUPPLY problem, not a scoping one: too few mutants land where the
    oracle looks, and no choice of projection creates evidence that was never
    generated. The question "could this oracle fail at all" is answered without
    any mutants by `liveness`, which needs no supply and abstained on none of
    the 70. Adequacy's remaining job is the narrower one it is good at -- would
    this oracle catch a realistic defect of THIS model -- asked of the oracles
    liveness has already shown can fail.

    Kept as an override because it is correct and cheap, and because a design
    with a richer mutant supply may invert the result.
    """
    steps = _steps_for(oracle, stimulus_by_tp)
    if not steps:
        return UNKNOWN, "no stimulus to mutate against"

    ports = set(scope) if scope is not None else ports_read(oracle, contract)
    if not ports:
        return UNKNOWN, ("the oracle asserts on no declared port" if scope
                         is not None else "the oracle reads no declared port")

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
    scope: dict[str, set[str]] | None = None,
) -> dict[str, tuple[str, str]]:
    """`{req_uid: (verdict, detail)}` over the whole trusted set.

    `scope` is per-oracle, keyed by `req_uid` -- `liveness.assertion_ports`
    returns exactly that shape. An oracle absent from it falls back to
    `ports_read`, so a partial map is usable.
    """
    return {
        o.req_uid: adequacy_of(o, source, contract, stimulus_by_tp,
                               base=base, limit=limit,
                               transactional=transactional,
                               scope=(scope or {}).get(o.req_uid))
        for o in oracles
    }


def inadequate(report: dict[str, tuple[str, str]]) -> dict[str, str]:
    """The oracles a strengthening round should be spent on, and why."""
    return {uid: detail for uid, (level, detail) in report.items()
            if level == INADEQUATE}


def write(run_dir: Path, report: dict[str, tuple[str, str]], round_: int = 0,
          *, discrimination: dict | None = None) -> Path:
    """Reported, not gated. Its rate has to be measured before it decides anything."""
    path = Path(run_dir) / "specflow" / f"adequacy_r{round_}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    counts: dict[str, int] = {}
    for level, _ in report.values():
        counts[level] = counts.get(level, 0) + 1
    path.write_text(json.dumps({
        "counts": counts,
        # Whether the set can tell a known-good design from this one at all.
        # `None` means no control was available to ask -- which is not zero.
        "discrimination": discrimination,
        "by_requirement": {u: {"verdict": v, "detail": d}
                           for u, (v, d) in sorted(report.items())},
    }, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path




def discrimination(
    oracles: list[RequirementOracle],
    source: str,
    control: str,
    contract: dict,
    stimulus_by_tp: dict[str, list[dict]],
    *,
    base: str,
    transactional: bool = True,
) -> dict:
    """How many requirements the oracle set decides DIFFERENTLY for two designs.

    The one number that says whether the set is an instrument at all. Not a
    gate, and it must never become one: the control is a proxy for the held-out
    grade, so letting it shape the run tunes the model toward its own scorer.
    This only reports -- exactly as `golden_check` does, and for the same
    reason.

    Measured on n-i2c, and it is why this exists:

        model scoring 30/168 against golden RTL : CONFORMS 46, NOT_EXERCISED 24
        control scoring 168/168                 : CONFORMS 47, NOT_EXERCISED 23

    Identical on 67 of 70. A set of oracles that separates a design failing 138
    of 168 testpoints from one passing all 168 by ONE requirement is not
    measuring the design; it is measuring almost nothing. Every other number the
    pipeline reports about that run -- 46 CONFORMS, a loop that converged, a
    stage that verified 70 oracles -- is true and means nothing without this one
    beside it.

    `VIOLATES` on the control is the harshest column and is reported apart: a
    known-good design failing an oracle says the oracle is wrong, and no amount
    of discrimination redeems that.
    """
    from . import verdict as V

    mine = decide_all(oracles, source, contract, stimulus_by_tp, base=base,
                      transactional=transactional)
    theirs = decide_all(oracles, control, contract, stimulus_by_tp, base=base,
                        transactional=transactional)
    here = {r.req_uid: V.of_result(r) for r in mine}
    there = {r.req_uid: V.of_result(r) for r in theirs}

    differ = sorted(u for u in here if here.get(u) != there.get(u))
    counts: dict[str, int] = {}
    for uid in differ:
        counts[f"{here[uid]} -> {there[uid]}"] = (
            counts.get(f"{here[uid]} -> {there[uid]}", 0) + 1)
    return {
        "oracles": len(here),
        "discriminating": len(differ),
        "identical": len(here) - len(differ),
        "requirements": differ,
        "transitions": counts,
        # A known-good design failing an oracle: the oracle is wrong, and this
        # is not redeemed by any amount of discrimination.
        "control_violates": sorted(u for u, v in there.items()
                                   if v == "VIOLATES"),
    }
