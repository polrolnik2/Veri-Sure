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
import re
from pathlib import Path
from typing import NamedTuple

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

#: IN-SCOPE mutants per oracle -- ones that changed something the oracle asserts
#: on. Bounded for the same reason gate 2 bounds it: the evidence saturates, and
#: an oracle that survives eight of them is not going to be convicted by a ninth.
MUTANT_LIMIT = 8

#: CANDIDATES that may be tried to reach `MUTANT_LIMIT`, and a separate number
#: because `mutants()` proposes in deterministic SITE order while the visibility
#: filter runs after. One budget spent before the filter starves whichever
#: oracle the first few executed sites happen not to touch, and it starves it
#: silently -- as UNKNOWN, which reads as "the instrument had nothing to say"
#: rather than "the instrument was not allowed to look".
#:
#: Measured on w-i2c's frozen 58, in-scope budget held at 8:
#:
#:     candidates   adequate  inadequate  unknown   replays   wall
#:              8          3          29       26       384     6s
#:             60          1          42       15      2100    41s
#:
#: 26 -> 15 undecided for 41 seconds of CPU and no model calls. Of the 15 that
#: remain, 11 assert on no declared port -- `liveness`'s finding, not this
#: one's -- so the residue this instrument genuinely cannot decide is 4.
PROPOSAL_LIMIT = 60

ADEQUATE = "adequate"
INADEQUATE = "inadequate"
UNKNOWN = "unknown"

#: Surviving mutants NAMED in the detail. All of them are counted; this bounds
#: how many are quoted, because the detail is embedded verbatim in the
#: strengthening prompt and a list of eight is a worse instruction than three.
SURVIVORS_NAMED = 3

#: How many the count itself is worth reporting over -- see `_survived`.
_SURVIVED = "survived {n} of {m} mutant(s) it could see: {sample}"


#: Disagreeing edges quoted to the oracle author. Three is what fits in an
#: instruction; the count says how many more there were.
DIFFS_QUOTED = 3


class Finding(NamedTuple):
    """One oracle's adequacy: what the artifact records, and what the author gets.

    `detail` and `counterexample` are separate ON PURPOSE and describe the same
    event in two vocabularies, because their readers are allowed to see
    different things. `detail` names the mutation -- "line 21: True becomes
    False" -- which is what a person debugging this pipeline needs. That string
    is useless to the oracle author and was what the strengthening edge used to
    send it: `oracle_gen.build_prompt` "has no parameter that could carry a
    design", so the author was being asked to aim at a line number in a file
    invariant I1 forbids it from ever seeing.

    Measured across the two runs that spent the edge -- t-i2c 51 calls, w-i2c 21
    -- NOT ONE ORACLE MOVED FROM INADEQUATE TO ADEQUATE. And the rejections were
    not the over-strictness the plan predicted; every one reads `vacuous: passed
    all N variant(s) of its own requirement`. Asked to tighten against a
    counterexample it could not locate, the author wrote something WEAKER.

    `counterexample` is the same finding in ports and edges -- `row['edge']` and
    `row['outputs'][port]`, exactly the vocabulary the oracle's own `decide`
    already reads, and observable behaviour rather than a design.
    """

    verdict: str
    detail: str
    counterexample: str = ""


def _difference(
    base_rows: list[dict], mutant_rows: list[dict], ports: set[str],
    limit: int = DIFFS_QUOTED,
) -> list[str]:
    """Where two traces the oracle could not tell apart actually disagree.

    NEITHER SIDE IS LABELLED, and that is the whole discipline of this function.
    Naming which trace is the conforming one hands the author the reference
    model's behaviour to write its check against -- and the reference model is
    the artifact this oracle exists to judge. The plan already records the
    weaker form of this: a *control* may reject an oracle but never repair one,
    because quoting a known-good trace tunes the oracle to it and the model is
    then tuned to the oracle, so `golden_check` stops being held out. Quoting
    the model's OWN trace is that failure with the loop closed tighter.

    So the author is told only that two designs differ here and its check passed
    both. Which of them violates the requirement has to come from the
    requirement, which is the one source of truth it is allowed.
    """
    out: list[str] = []
    if len(base_rows) != len(mutant_rows):
        # LENGTH IS A DIFFERENCE, and on this design it is the commonest one.
        # Measured on w-i2c REQ-0000: the surviving mutant ran 204 edges where
        # the design it was compared against ran 30, because it never leaves
        # reset, so the transaction never completes and the replay runs to its
        # edge budget. `_project` already counts that -- tuples of different
        # length are unequal -- but zipping the rows positionally finds no
        # disagreeing port in the first 30 and reports nothing.
        #
        # It is also the counterexample most worth sending. A check that cannot
        # notice the run never finished is vacuous in the plainest way there is.
        out.append(f"one runs {len(base_rows)} edges and the other "
                   f"{len(mutant_rows)}, so one of them never finishes")
    for i, base in enumerate(base_rows):
        if len(out) >= limit:
            return out
        if i >= len(mutant_rows):
            break
        edge = base.get("edge", i)
        b_out = base.get("outputs") or {}
        m_out = mutant_rows[i].get("outputs") or {}
        for port in sorted(ports):
            if port not in b_out and port not in m_out:
                continue
            if b_out.get(port) == m_out.get(port) and (
                    port in b_out) == (port in m_out):
                continue
            # `.get` on both sides deliberately: a port PRESENT in one row and
            # ABSENT in the other is a difference `_project` counts, and
            # requiring it in both was the second way this returned nothing.
            out.append(
                f"edge {edge}: {port} is {b_out.get(port)} in one and "
                f"{m_out.get(port)} in the other")
            if len(out) >= limit:
                return out
    return out


def _instruct(diffs: list[str], missed: int, in_scope: int) -> str:
    """What the strengthening round sends the oracle author.

    Phrased as the discrimination it failed rather than as a defect to chase,
    because that is the thing it can actually act on: two traces, both accepted,
    differing at ports this requirement is about. Which one is wrong is a
    question about the requirement, and the requirement is what the author has.
    """
    if not diffs:
        return (f"{missed} of {in_scope} designs that differ at the ports this "
                f"requirement is about all pass your check, but the difference "
                f"is not at an edge this check reads.")
    return ("cannot tell two designs apart. Both pass it, and they differ:\n"
            + "\n".join(f"    {d}" for d in diffs)
            + f"\n  One of them violates this requirement. {missed} of "
            f"{in_scope} such pairs got past this check.")


def _survived(survivors: list[str], in_scope: int) -> str:
    """The reason an inadequate oracle is handed to a strengthening round.

    IT REPORTS THE COUNT, and that is the point. `adequacy_of` used to keep
    `survivor = survivor or mutant.description` -- the FIRST survivor in
    deterministic SITE order -- and site order starts at the top of the file,
    which is where a model's reset and initialisation block lives. So a broad
    failure and a single shared blind spot produced the same report.

    They are not the same, measured on w-i2c's 43 oracles with enough evidence
    to decide. Naming only the first, the population looks concentrated:

        25 oracles  "survived line 21: True becomes False"

    Counting every survivor, it is not concentrated at all -- 253 of 330
    in-scope mutants got past, 24 distinct mutants survived somewhere, and the
    distribution of survivors per oracle is 14 oracles missing all 8 and 11
    missing 7. Exactly one oracle in the set caught everything shown to it.

    This is the artifact the rework plan's §4b item 3 read as evidence: "every
    one cites `survived line 27: 1 becomes 2`". That was true and it was a
    property of the REPORT, not of the population, and it led to a filter that
    fired on 0 of 70.

    It also changes the repair. `_strengthen` embeds this string verbatim --
    "A design that VIOLATES this requirement passes your check: it {why}" -- so
    an oracle that missed seven of eight wrong designs was being told about one.
    """
    sample = "; ".join(survivors[:SURVIVORS_NAMED])
    if len(survivors) > SURVIVORS_NAMED:
        sample += f"; and {len(survivors) - SURVIVORS_NAMED} more"
    return _SURVIVED.format(n=len(survivors), m=in_scope, sample=sample)


def adequacy_of(
    oracle: RequirementOracle,
    source: str,
    contract: dict,
    stimulus_by_tp: dict[str, list[dict]],
    *,
    base: str,
    limit: int = MUTANT_LIMIT,
    propose: int = PROPOSAL_LIMIT,
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

    SCOPING AND SUPPLY ARE ONE FIX, and that is why each measured badly alone.
    Narrowing the projection can only REDUCE `in_scope`, so against a proposal
    budget of 8 it pushes oracles under `MIN_IN_SCOPE` instead of resolving
    them -- measured, and recorded here for a while as "it does not help":

        frozen 70, 8 candidates    ports_read   6 adequate · 20 inadequate · 44 unknown
                                   asserts_on   6           · 18            · 46

    Raising the candidate budget alone has the opposite defect. It resolves
    almost everything and manufactures convictions doing it, because a mutant
    visible only in a port the oracle TRIGGERS on is one it could never have
    caught. On w-i2c's 58, `ports_read` at 60 candidates reads 2 / 54 / 2 --
    and 9 of those 54 are oracles the paired configuration withdraws, one in
    four of the shipped instrument's convictions.

    Together they behave. w-i2c's 58, shipped (`ports_read`, 8) against paired
    (`asserts_on`, 60):

        inadequate -> inadequate  29        unknown  -> inadequate  11
        inadequate -> unknown      9        adequate -> inadequate   2

    The 11 are supply the old budget never spent; the 9 are convictions on
    mutants the oracle was never asked about. Both directions matter, because
    `adequacy_rounds` sends an inadequate oracle back to be STRENGTHENED, and
    strengthening a check against a defect it does not cover is exactly the
    over-strictness that §6's oscillation risk is made of.

    The two instruments then partition cleanly rather than overlapping. Every
    one of the 42 paired convictions lands on an oracle `liveness` independently
    calls live; of the 15 it leaves undecided, 6 are dead-oracle and 3
    dead-stimulus -- already convicted, harder, by an instrument that needs no
    mutants at all -- and 11 assert on no declared port. Adequacy abstaining
    there is correct: it must not re-report a finding liveness owns.
    """
    steps = _steps_for(oracle, stimulus_by_tp)
    if not steps:
        return Finding(UNKNOWN, "no stimulus to mutate against")

    ports = set(scope) if scope is not None else ports_read(oracle, contract)
    if not ports:
        return Finding(UNKNOWN, "the oracle asserts on no declared port"
                       if scope is not None
                       else "the oracle reads no declared port")

    baseline = replay(source, contract, steps, base=base)
    if baseline.error:
        return Finding(UNKNOWN, f"the model {baseline.error}")
    reference = _project(baseline.rows, ports)

    lines = mutate_model.executed_lines(source, contract, steps, base=base)
    in_scope = 0
    survivors: list[str] = []
    diffs: list[str] = []
    for mutant in mutate_model.mutants(source, lines=lines, limit=propose):
        if in_scope >= limit:
            break                        # the evidence has saturated
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
            survivors.append(mutant.description)
            # The REPLAY is the counterexample, not the mutation. Taken from the
            # first survivor only: the author is being asked to make one
            # discrimination it failed to make, and three edges of one pair is
            # an instruction where thirty edges of eight pairs is a haystack.
            if not diffs:
                diffs = _difference(baseline.rows, run.rows, ports)
    if in_scope < MIN_IN_SCOPE:
        return Finding(UNKNOWN, (
            f"only {in_scope} mutant(s) changed anything this oracle can see; "
            f"{MIN_IN_SCOPE} are needed before silence means inadequacy"))
    if survivors:
        return Finding(INADEQUATE, _survived(survivors, in_scope),
                       _instruct(diffs, len(survivors), in_scope))
    return Finding(
        ADEQUATE, f"caught every one of {in_scope} mutants it could observe")


def assess(
    oracles: list[RequirementOracle],
    source: str,
    contract: dict,
    stimulus_by_tp: dict[str, list[dict]],
    *,
    base: str,
    limit: int = MUTANT_LIMIT,
    propose: int = PROPOSAL_LIMIT,
    transactional: bool = True,
    scope: dict[str, set[str]] | None = None,
) -> dict[str, tuple[str, str]]:
    """`{req_uid: (verdict, detail)}` over the whole trusted set.

    `scope` is per-oracle, keyed by `req_uid`. Passing one keeps the old
    behaviour that an oracle absent from it falls back to `ports_read`, so a
    partial map stays usable.

    **The default derives it**, from `liveness` against the same design being
    mutated -- not from the oracle stage's report, which was taken against the
    witness, and which ports a check decides on is a property of the trace it
    sees. `adequacy_of` says why the pairing is load-bearing; the short version
    is that `ports_read` is a string scan, 59% of the ports it projects through
    carry no assertion on w-i2c, and every mutant visible only in one of those
    is a conviction the oracle could not have earned.
    """
    cannot_fail: dict[str, str] = {}
    if scope is None:
        from . import liveness as _L
        report = _L.assess(oracles, source, contract, stimulus_by_tp,
                           base=base, transactional=transactional)
        scope = _L.assertion_ports(report)
        # AND THE DEAD ONES STILL HAVE TO BE ROUTED. Deriving the scope is what
        # makes them fall out: an oracle that asserts on nothing projects onto
        # nothing, so the mutant sweep has no evidence and answers UNKNOWN --
        # and `inadequate()` is what feeds the strengthening edge, so under the
        # old `ports_read` default these were convicted and repaired, and under
        # the new one they would silently stop being. A check that cannot fail
        # is not an absence of evidence about strength; it is the strongest
        # evidence of weakness there is.
        #
        # `liveness.dead` is relayed rather than re-derived, including its
        # deliberate exclusion of DEAD_STIMULUS -- that check demonstrably CAN
        # fail, so it is a testplan finding and sending it to the oracle author
        # would have them strengthen what was never the problem.
        cannot_fail = _L.dead(report)
    return {
        o.req_uid: (
            Finding(INADEQUATE, cannot_fail[o.req_uid],
                    cannot_fail[o.req_uid])
            if o.req_uid in cannot_fail
            else adequacy_of(o, source, contract, stimulus_by_tp,
                             base=base, limit=limit, propose=propose,
                             transactional=transactional,
                             scope=scope.get(o.req_uid))
        )
        for o in oracles
    }


def inadequate(report: dict[str, tuple[str, str]]) -> dict[str, str]:
    """The oracles a strengthening round should be spent on, and why."""
    return {uid: (rec[2] if len(rec) > 2 and rec[2] else rec[1])
            for uid, rec in report.items() if rec[0] == INADEQUATE}


def strength(report: dict[str, tuple[str, str]]) -> dict[str, int]:
    """One number for how much this oracle set actually demands.

    The verdict counts do not carry it. "48 inadequate" says 48 oracles let
    SOMETHING past and nothing about how much: an oracle that missed one of
    eight and one that missed eight of eight are the same row. Summing the
    survivors gives the rate, and on w-i2c that rate is 253 of 330 -- 76% of
    the wrong designs each oracle was shown went by unnoticed.

    Parsed back out of the detail rather than threaded through the return type,
    which is a narrow thing to do and stays honest only because `_survived` in
    this same module is the one writer of the string being read. Nothing
    outside decides on it, and a detail that does not match simply does not
    count.
    """
    shown = missed = 0
    for rec in report.values():
        level, detail = rec[0], rec[1]
        if level == INADEQUATE:
            m = re.match(r"survived (\d+) of (\d+) ", detail)
            if m:
                missed += int(m.group(1))
                shown += int(m.group(2))
        elif level == ADEQUATE:
            m = re.search(r"every one of (\d+) ", detail)
            if m:
                shown += int(m.group(1))
    return {"mutants_shown": shown, "mutants_missed": missed,
            "missed_pct": (100 * missed // shown) if shown else 0}


def write(run_dir: Path, report: dict[str, tuple[str, str]], round_: int = 0,
          *, discrimination: dict | None = None) -> Path:
    """Reported, not gated. Its rate has to be measured before it decides anything."""
    path = Path(run_dir) / "specflow" / f"adequacy_r{round_}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    counts: dict[str, int] = {}
    for rec in report.values():
        counts[rec[0]] = counts.get(rec[0], 0) + 1
    path.write_text(json.dumps({
        "counts": counts,
        "strength": strength(report),
        # Whether the set can tell a known-good design from this one at all.
        # `None` means no control was available to ask -- which is not zero.
        "discrimination": discrimination,
        "by_requirement": {
            u: {"verdict": r[0], "detail": r[1],
                **({"counterexample": r[2]} if len(r) > 2 and r[2] else {})}
            for u, r in sorted(report.items())},
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
