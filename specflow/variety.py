"""Authoring INTO the design space: the generation-stage variety lever.

**THE PROBLEM THIS EXISTS FOR.** Selection is a filter, so it can only lose
span, and the corpus subsampling says where its offset has to come from: over
100 -> 464 bodies span climbs 37.2% -> 81.6% and is still climbing, while
blindness saturates (the first 100 bodies buy 26 points, the last 164 buy 2.7)
and audit is flat (21.6% -> 18.9%). **Volume buys span; selection buys
blindness.** So a set that is both broad and sharp needs more DISTINCT bodies
per requirement, and the two ways tried so far do not produce them:

  resampling one prompt   among pairs where both bodies are SOUND, 69% are
                          identical and 4% complementary. Resampling samples one
                          interpretation; it does not produce another.
  a different STIMULUS    pre-registered at >=40% = lever, <15% = closed.
  route to a scenario     Delivered 1 of 20 = 5% fully caught, with 15 of 20 new
                          testpoints fully blind. Reaching the scenario was
                          never the problem.

**THE COORDINATE SYSTEM IS THE DESIGN POPULATION, NOT THE TEXT.** Seven
independently written spec-derived designs fall into seven equivalence classes,
all 21 pairs `DIFFERS` under a bounded reset-constrained miter that reads no
known-good design. So "two checks are different" means *some spec-admissible
design tells them apart*, and blindness is the disagreement cells nothing
adjudicates -- measured, the same 169-check set is 0% blind on 61 testpoints and
100% blind on 70, with 8 of 10 ports carrying disagreements in both classes.

**THE POPULATION IS A POINTER, NOT AN ORACLE, AND THAT IS THE WHOLE DESIGN.**
`brief` is handed a LOCATION -- the requirement, the driven inputs, the port and
the testpoint the current set adjudicates nothing on. It is not handed the
designs' source, it is not handed the values they produced, and it is never told
that either of them is correct. There is no parameter through which any of that
could arrive, which is the same structural enforcement `variants.build_prompt`
uses.

WHY, MEASURED. Presenting two behaviours and asking which the spec means makes
them the answer set, when the spec may imply a third value or may not constrain
that port at all -- and it reproduces the pathology the witness gate was deleted
for: "it has no authority to say the oracle is wrong... telling an author 'an
independent implementation fails your check' does not make the check more
correct, **it makes the check agree with the witness**. Measured on h-i2c:
over-strictness 27 -> 15, convictions 2 -> 16." A disagreement says only WHERE
the spec is under-determined by the current set. What belongs there comes from
the spec.

**THE NULL IT HAS TO BEAT.** A round of re-authoring checks -- 39 calls, WITH a
witness in the prompt -- reached 0 cells newly reached, "the rewrites' objections
were a strict subset of what the set already caught". That round handed the
author a design to agree with; this hands it a location and no design, and that
distinction is the entire hypothesis. It is also a 0.69% sample of a
5,656-disagreement residue belonging to a set that was 99.8% blind BY
CONSTRUCTION, so it does not transfer as a flat zero -- but it is the nearest
prior and the bar is the stimulus round's 5%, not 0.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

Rows = Sequence[Mapping[str, object]]


@dataclass(frozen=True)
class Cell:
    """One place two spec-admissible designs behave differently.

    `(testpoint, port, left, right)` -- deliberately NOT the two values. A cell
    is a coordinate, and everything downstream that touches an author takes a
    cell, so the values have nowhere to travel.
    """

    testpoint: str
    port: str
    left: str
    right: str

    @property
    def pair(self) -> tuple[str, str]:
        return (self.left, self.right)


def cells(rows_by_design: Mapping[str, Mapping[str, Rows]],
          outputs: Sequence[str]) -> tuple[Cell, ...]:
    """Every `(testpoint, port, pair)` the population disagrees on.

    Port granularity, not testpoint granularity, because that is the resolution
    blindness is defined at and the resolution an author can be pointed to. A
    testpoint where two designs differ says "somewhere in here"; a port says
    where to look.

    A design missing a testpoint contributes no cell for it: absence is not
    disagreement, and counting it as one would manufacture cells out of a
    replay that never ran -- the same conflation `must_fail` had to remove when
    never-triggered replays were counted as evidence.
    """
    designs = tuple(sorted(rows_by_design))
    found: list[Cell] = []
    for tp in sorted({tp for rows in rows_by_design.values() for tp in rows}):
        present = [d for d in designs if rows_by_design[d].get(tp)]
        for port in outputs:
            seen: dict[str, str] = {}
            for d in present:
                rows = rows_by_design[d][tp]
                seen[d] = "|".join(
                    str((r.get("outputs") or {}).get(port)) for r in rows)
            for i, a in enumerate(present):
                for b in present[i + 1:]:
                    if seen[a] != seen[b]:
                        found.append(Cell(testpoint=tp, port=port,
                                          left=a, right=b))
    return tuple(found)


def separates(cell: Cell, verdict: Mapping[str, bool | None]) -> bool:
    """Does this check tell the cell's two designs APART?

    **POLARITY-CORRECTED, AND THAT IS NOT THE SAME AS THE RECORDED BLINDNESS
    NUMBER.** The scorecard defines set blindness as the share of disagreement
    cells where no check "objects to either", which a check convicting BOTH
    designs satisfies while separating nothing -- and objecting to both sides is
    exactly how a blindness score was gamed once before. Constriction needs
    separation: different verdicts, not merely an objection.

    An abstention on either side is not a separation. `decide` returns None
    exactly when the clause's scenario never occurred, and silence from a check
    that was shown nothing says nothing about the design.
    """
    left, right = verdict.get(cell.left), verdict.get(cell.right)
    if left is None or right is None:
        return False
    return left != right


def separates_at(cell: Cell,
                 verdict_by_testpoint: Mapping[str, Mapping[str, bool | None]],
                 ) -> bool:
    """`separates`, ASKED WHERE THE CELL IS -- which is the whole point of a cell.

    **`separates` IS HANDED A CELL AND READS TWO OF ITS FOUR FIELDS.** It takes
    `cell.left` and `cell.right` and ignores `cell.testpoint` and `cell.port`,
    so a check that tells two designs apart ANYWHERE scores as adjudicating
    EVERY cell of that pair. `cells` says in its own docstring that it works at
    "port granularity, not testpoint granularity, because that is the
    resolution blindness is defined at" -- and then blindness is computed at
    pair granularity, which is coarser than either.

    Measured on the first probe-bearing run, 151 checks over three designs:
    **ONE check separating pair (0, 1) somewhere marked all 966 of that pair's
    cells adjudicated, across 268 testpoints and 8 ports.** Blindness read
    **0.0%** of 3,530 cells on 14 separations in total. At the resolution below
    the same set and the same replays read **97.0%**.

    So this is not a stricter predicate; it is the same predicate stopped from
    generalising a verdict to testpoints the check was never run against.

    **THE PORT IS STILL NOT CONSULTED, AND THAT IS A LIMIT, NOT AN OVERSIGHT.**
    A replay yields one verdict per `(check, design, testpoint)`: `decide`
    reads a whole trace and returns a single answer, so no attribution of that
    answer to one of eight ports exists to read. Inventing one -- crediting the
    ports a check's `observable` names -- would be the suite grading its own
    reach, which is the circularity this module exists to avoid. The honest
    resolution is `(testpoint, pair)`, and cells on different ports of one
    testpoint stand or fall together.
    """
    per = verdict_by_testpoint.get(cell.testpoint) or {}
    left, right = per.get(cell.left), per.get(cell.right)
    if left is None or right is None:
        return False
    return left != right


def blind_at(population_cells: Sequence[Cell],
             verdicts_by_testpoint: Mapping[
                 str, Mapping[str, Mapping[str, bool | None]]],
             ) -> tuple[Cell, ...]:
    """`blind`, at `(testpoint, pair)` resolution. See `separates_at`.

    `verdicts_by_testpoint` is `check -> testpoint -> design -> verdict`, one
    entry per replay actually performed. A check absent from a testpoint
    separates nothing there, which is the same rule `separates` applies to an
    abstention: silence from a check that was shown nothing says nothing.

    **KEPT BESIDE `blind` RATHER THAN REPLACING IT**, for the reason
    `objects_to_either` is kept: every blindness figure recorded on this branch
    -- 20.8%, 50.0%, 40.4%, 99.8%, and "blindness solved" -- was computed by
    `blind`, and silently changing what the name means would make the record
    incomparable instead of correcting it. Report both; never quote one as the
    other.
    """
    return tuple(
        c for c in population_cells
        if not any(separates_at(c, t) for t in verdicts_by_testpoint.values()))


def objects_to_either(cell: Cell, verdict: Mapping[str, bool | None]) -> bool:
    """The RECORDED blindness predicate, kept so numbers stay comparable.

    Weaker than `separates` on purpose: this is the definition behind every
    published blindness figure in this project (t = 0 at 99.8%, t = 6 at 40.4%,
    CEIL2 at 56.9%), and a new predicate would silently make them
    incomparable. Report both; never quote one as the other.
    """
    return verdict.get(cell.left) is False or verdict.get(cell.right) is False


def blind(population_cells: Sequence[Cell],
          verdicts: Mapping[str, Mapping[str, bool | None]],
          *, polarity_corrected: bool = True) -> tuple[Cell, ...]:
    """The cells no check in the set adjudicates -- the authoring targets.

    `verdicts` is `check_id -> design -> verdict`. Set blindness COMPOSES:
    adding a check can only close holes, which is why it is scored over the set
    and not per check. Scoring it per check produced the defect that motivated
    the set-level definition: "adding 17 checks each measured less blind than
    its parent took the blind-check count from 121 to 136 -- because a set gains
    a blind check whenever it gains a check. Rejection is a union, so a metric
    that worsens when you add a check is measuring the denominator."
    """
    speaks = separates if polarity_corrected else objects_to_either
    return tuple(
        c for c in population_cells
        if not any(speaks(c, v) for v in verdicts.values()))


def constricting(blind_cells: Sequence[Cell],
                 accepted: Sequence[str], *,
                 both: bool = False) -> tuple[Cell, ...]:
    """The blind cells whose closure could change the ACCEPTED set.

    **MEASURED, AND IT IS WHY RANKING BY MASS IS THE WRONG TARGET.** The E4
    pilot closed 96 of 249 blind cells soundly -- blindness 56.0% -> 14.6% from
    two checks -- and moved the accepted set by nothing: 3 designs, 3 classes,
    diameter 0.015, all unchanged. The cells it closed lay between designs the
    set had ALREADY rejected, so separating them adjudicated a difference that
    changed no verdict.

    A cell can only move the accepted set if one of its designs is still in it:
    closing the cell convicts exactly one of the pair, and convicting an
    already-rejected design changes nothing.

    **REPORT WITH THIS. DO NOT TARGET WITH IT.** "Already rejected" is the
    SUITE'S opinion about an UNVERIFIED design, and using it to choose what to
    author filters evidence about the suite by the suite's own verdicts -- the
    same circularity as the faithfulness gates this module exists to replace,
    arrived at through arithmetic instead of prose. None of these designs is
    known correct; a disagreement is just a disagreement.

    **AND IT IS FRAGILE AND NON-MONOTONE, WHICH IS THE DISQUALIFYING PART.**
    Measured on the pilot's own set: of eight rejections, **one check
    (`reauthor43:REQ-0101`) carries five**, and dropping it alone takes the
    accepted set from `h, q, s` to `h, n, p, q, s, y`. So the ranking is a
    function of one unverified check whose whole claim to soundness is sparing
    one control on seven testpoints. Removing a bad check makes previously
    "worthless" cells valuable again -- the triage depends on DEFECTS in the
    artifact it is triaging evidence about.

    What it is legitimately for: explaining an outcome after the fact. It is
    what showed that pilot 1 closed 96 cells and moved nothing, because its
    checks convicted only designs other checks had already convicted. That is a
    true statement about the set as it stands, and it survives.

    **`both=True` IS THE GUARANTEED-CONSTRICTING SUBSET, AND IT IS SMALL.** Of
    the pilot's 249 blind cells, **169 touch an accepted design but only 23 have
    BOTH accepted** -- 12 on `sda_oen`, 9 on `scl_oen`, 2 on `busy`, over the
    pairs (h,q) 11, (q,s) 10, (h,s) 2. Those 23 are the only cells where a check
    that closes them MUST reject a design that is currently surviving, because
    whichever side it convicts was accepted a moment ago.

    Touching one accepted design is necessary and not sufficient, and the pilot
    is the demonstration: its checks convicted `d, r, y` and `y`, every one
    already rejected. That is how 96 cells closed and nothing moved.
    """
    keep = set(accepted)
    if both:
        return tuple(c for c in blind_cells
                     if c.left in keep and c.right in keep)
    return tuple(c for c in blind_cells if c.left in keep or c.right in keep)


def ranked(blind_cells: Sequence[Cell],
           accepted: Sequence[str] | None = None) -> tuple[tuple[str, int], ...]:
    """Blind cells collapsed to `(port, count)`, heaviest first.

    Authoring targets are ports, not individual cells: the same output blind on
    forty cells is one question to an author, and forty briefs would buy forty
    near-copies of one check -- the failure mode this module exists to avoid.
    Measured on the store write-through path, blindness collects at 5x on four
    ports, so the mass is concentrated enough for this to matter.

    **`accepted` IS A DIAGNOSTIC WEIGHTING, NOT AN AUTHORING TARGET.** It counts
    a cell twice when both its designs are still accepted, once when one is, and
    not at all when neither is. That is useful for explaining why a round of
    authoring did or did not move the accepted set. It is NOT a way to choose
    cells to author at: see `constricting` for why -- the weighting reads the
    suite's verdicts about unverified designs, one check carries five of eight
    rejections in the measured case, and removing a bad check re-values cells it
    had zeroed. Rank authoring targets by mass, which reads only the designs.
    """
    keep = set(accepted) if accepted is not None else None
    tally: dict[str, int] = {}
    for c in blind_cells:
        if keep is None:
            weight = 1
        else:
            weight = (c.left in keep) + (c.right in keep)
        if weight:
            tally[c.port] = tally.get(c.port, 0) + weight
    return tuple(sorted(tally.items(), key=lambda kv: (-kv[1], kv[0])))


def brief(cell: Cell, *, requirement: str, activation: str,
          driven: Mapping[str, object]) -> str:
    """What the author is told. A LOCATION AND A REQUIREMENT. Nothing else.

    **THE PARAMETERS ARE THE ENFORCEMENT.** There is no argument here through
    which a design's source, a design's observed values, or a claim that either
    design is right could arrive -- the same structural guarantee
    `variants.build_prompt` relies on rather than an instruction not to look.
    `cell` carries a port and two design NAMES; the names are never rendered.

    The author is told that the requirement applies here and that nothing in the
    suite currently decides this port in this scenario. What the port should do
    is for the specification to say.
    """
    driven_text = ", ".join(f"{k}={v}" for k, v in sorted(driven.items()))
    return (
        f"REQUIREMENT\n{requirement.strip()}\n\n"
        f"WHEN IT APPLIES\n{activation.strip()}\n\n"
        f"THE GAP\nIn the scenario driven by {driven_text or '(no inputs)'}, "
        f"nothing in the current suite decides the output port `{cell.port}` at "
        f"testpoint {cell.testpoint}. Readings of this specification that are "
        f"each defensible come apart there, which means the specification's "
        f"answer for `{cell.port}` is not being checked.\n\n"
        f"WRITE THE CHECK that decides `{cell.port}` in this scenario, FROM THE "
        f"REQUIREMENT ABOVE. You are not being asked to choose between two "
        f"behaviours and you are not being shown any implementation: if the "
        f"requirement does not constrain `{cell.port}` here, say so in "
        f"`reasoning` and write no check. A check invented to fill this gap is "
        f"worse than an honest report that the specification is silent."
    )


def every_blindness_figure_on_this_branch_was_measured_per_PAIR() -> str:
    """The resolution defect, found by a cell leg that authored nothing.

    A run configured with `cell_budget=12`, a population of three spec-derived
    designs and 3,530 disagreement cells produced zero cell checks and zero
    prompts. The leg was reached, the budget arrived and the targets came back
    empty, because blindness read 0.0%.

    Driver: `docs/evidence/e4c_blindness_resolution.py`. Zero model calls --
    the probe run's own artifacts, its own three designs and its own first
    drafts, replayed.
    """
    return (
        "**`separates` IS HANDED A CELL AND READS TWO OF ITS FOUR FIELDS.** It "
        "takes `cell.left` and `cell.right`; `cell.testpoint` and `cell.port` "
        "reach it and are never consulted. So a check that tells two designs "
        "apart ANYWHERE scores as adjudicating EVERY cell of that pair, and "
        "`blind` -- which every recorded blindness figure on this branch goes "
        "through -- works at PAIR granularity. `cells` says in its own "
        "docstring that it works at 'port granularity, not testpoint "
        "granularity, because that is the resolution blindness is defined "
        "at'.\n\n"
        "**MEASURED ON THE FIRST PROBE-BEARING RUN.** 151 first drafts, three "
        "designs, 3,530 cells over 8 ports:\n\n"
        "    pair     cells   testpoints   checks that separate it ANYWHERE\n"
        "    (0,1)      966          268   1\n"
        "    (0,2)     1568          394   7\n"
        "    (1,2)      996          349   6\n\n"
        "**ONE check separating (0,1) somewhere closed all 966 of that pair's "
        "cells.** Fourteen separations in total closed all 3,530. Blindness: "
        "**0.0%**. At `(testpoint, pair)` -- the resolution a replay actually "
        "has -- the same set, the same designs and the same replays read "
        "**97.0%**, over 388 testpoints and all eight ports.\n\n"
        "**THE PORT IS STILL NOT CONSULTED, AND THAT IS A LIMIT RATHER THAN A "
        "CHOICE.** `decide` reads a whole trace and returns one answer per "
        "`(check, design, testpoint)`, so no attribution of that answer to one "
        "of eight ports exists to read. Crediting the ports a check's "
        "`observable` names would be the suite grading its own reach. Cells on "
        "different ports of one testpoint stand or fall together.\n\n"
        "**WHAT IT RETRACTS.** Every blindness number this branch recorded is "
        "a per-pair number, including 'blindness solved' on the full-pipeline "
        "run and the 20.8% that made `placement` the best triple on the board. "
        "They are not wrong about what they measured; they measured a coarser "
        "thing than their name says. `blind` is kept unchanged beside "
        "`blind_at` for exactly the reason `objects_to_either` was kept: "
        "silently redefining a name makes a record incomparable instead of "
        "correcting it. Report both; never quote one as the other.\n\n"
        "**THE DRIVER NO LONGER PRINTS 97.0%, AND THAT IS A SECOND FIX, NOT A "
        "RETRACTION OF THIS ONE.** Both numbers above were taken with each "
        "check replayed only against its own `tp_uids`. Widening that scope -- "
        "see `a_check_is_replayed_where_the_stimulus_goes` -- takes the same "
        "set to 12.8% on the same 3,530 cells. The per-PAIR reading stays 0.0% "
        "either way, because collapsing to the pair discards the coordinate "
        "the scope acts on.\n\n"
        "**AND IT EXPLAINS THE NULL THAT WAS ABOUT TO BE REPORTED.** The plan "
        "pre-registers <=15% fully caught as closing the authoring-at-cells "
        "line. This run would have reported zero -- not because authoring "
        "failed, but because the instrument said there was nothing to author "
        "at. A lever cannot be falsified by a run that never fired it."
    )


def a_check_is_replayed_where_the_stimulus_goes() -> str:
    """The second half of the blindness defect: scope, not just resolution.

    Driver: `docs/evidence/e4c_blindness_resolution.py` and the reach
    measurement beside it. Zero model calls -- replays of the probe run's own
    three designs against its own frozen set and its own first drafts.
    """
    return (
        "**A CHECK WAS REPLAYED ONLY AGAINST ITS OWN `tp_uids` -- MEDIAN 2 OF "
        "499.** A cell at TP-0400 can only be separated by a check replayed at "
        "TP-0400, so a suite whose checks are each pinned to two testpoints is "
        "blind almost everywhere BY CONSTRUCTION, whatever the checks say.\n\n"
        "Measured on the probe run, 3,530 cells at `(testpoint, pair)`:\n\n"
        "    set                     on own tp_uids   replayed everywhere\n"
        "    TRUSTED 96                       96.9%                 22.3%\n"
        "    all 151 first drafts             97.0%                 12.8%\n\n"
        "**THE RESTRICTION WAS ALWAYS REDUNDANT.** A check is a `decide(trace)` "
        "function that says for itself when it applies: `decide` returns None "
        "exactly when the clause's scenario never occurred, and that is the "
        "third state the whole module exists to keep. `tp_uids` was a second, "
        "cruder gate on top of it -- and a coarser one, since the testplan's "
        "`covers` attachment is a model's opinion about relevance while an "
        "abstention is a fact about the trace.\n\n"
        "**IT IS THE HONEST SCOPE FOR OVER-STRICTNESS TOO, AND THAT IS THE "
        "SAME MEASUREMENT READ TWICE.** A check that fires where it should not "
        "is exactly a check that convicts a design somewhere its requirement "
        "does not govern. Narrowing the replay hides that rather than fixing "
        "it, which is this tree's own 'over-strictness and vacuity as one "
        "defect with two signs' arriving through the harness instead of "
        "through the prose. It costs: replaying everywhere, 46 of the lost "
        "requirements' corpus bodies are refuted by the whole population "
        "where the narrow scope found 14.\n\n"
        "**AND IT MADE THE THREE INSTRUMENTS AFFORDABLE.** Refutation, cell "
        "blindness and `placement` each replayed the population for "
        "themselves; at the wide scope that is 3 x 499 replays per instrument "
        "per round. `_population_tables` builds all three shapes from one pass."
    )


def a_blind_set_is_usually_a_set_with_no_teeth() -> str:
    """Why a suite that reaches everywhere still separates nothing.

    Driver: `docs/evidence/e4d_why_the_set_is_blind.py`. Zero model calls --
    104 frozen checks replayed against seven spec-derived designs over 366
    testpoints, from the run's own artifacts.
    """
    return (
        "**BLINDNESS WAS 55.1% AND NOT ONE BLIND CELL SAT WHERE NO CHECK "
        "REACHED.** Every testpoint carrying a cell had a median of 39 checks "
        "deciding on it and a maximum of 77; the median check decided on 76 "
        "testpoints of 366. The set spoke everywhere. It agreed everywhere.\n\n"
        "13,019 (check, testpoint) decisions:\n\n"
        "    decided   convicted    count    share\n"
        "          7           0    11204    86.1%\n"
        "          6           0      593     4.6%\n"
        "          7           1      197     1.5%   <- mixed\n"
        "          7           2      105     0.8%   <- mixed\n\n"
        "**MIXED DECISIONS: 404 OF 13,019 = 3.1%, AND ONLY A MIXED DECISION "
        "SEPARATES ANYTHING.** Passing all seven separates nothing; convicting "
        "all seven separates nothing. **76 of the 104 checks never told any "
        "two of the seven apart, anywhere** -- against 22,315 places where two "
        "of them produce different traces on a declared output.\n\n"
        "**SO BLINDNESS IS NOT A REACH PROBLEM AND MORE CHECKS DO NOT FIX IT.** "
        "It was read as one twice: first as `tp_uids` being too narrow, which "
        "was real and took blindness 97% -> 12.8%, and then as needing more "
        "bodies, which it does not. The residue is a sensitivity problem, and "
        "the only moves that touch it are a stronger assertion inside the same "
        "window and a check authored AT a cell.\n\n"
        "**IT IS ALSO WHAT ONE HALF OF AN INSTRUCTION BUYS.** The set above "
        "was written by authors told that the failure mode is 'fires in the "
        "wrong place' and to make the window exactly as narrow as the "
        "situation is. They complied: audit went to 0 of 17 judgeable and the "
        "suite went inert. Over-strictness and vacuity, one defect with two "
        "signs, at set level -- and the stage had a blocking instrument for "
        "one sign and nothing at all for the other."
    )


def blindness_constricts_but_stalls_far_from_equivalence() -> str:
    """E4b, run on the nine spec-derived designs that survived the data loss.

    The plan asserted that reducing blindness constricts the design space toward
    equivalence and nothing measured it: the one set that reached a single design
    of seven at audit 0 was selected BY the reference, so it said nothing about
    what blindness optimisation does. This measures it directly.

    Driver: `docs/evidence/e4b_constriction.py`. Zero model calls -- replays and
    set arithmetic. Checks are added greedily by blind cells closed, so blindness
    falls monotonically by construction and the question is what the other three
    columns do.
    """
    return (
        "Nine designs, 445 disagreement cells over eight declared outputs, 15 of "
        "39 surviving checks deciding on at least one design, and the known-good "
        "control for the audit column only.\n\n"
        "**AT CONTROLLED AUDIT = 0** -- only the 9 of 15 checks that spare the "
        "control:\n\n"
        "    checks   blind%   accepts   classes   diameter\n"
        "         0   100.0%         9         8      0.108\n"
        "         1    58.2%         7         6      0.092\n"
        "         2  **56.0%**       6         5      0.085\n\n"
        "**ALL THREE FALL MONOTONICALLY, SO THE ASSUMPTION HOLDS IN DIRECTION.** "
        "Cardinality, equivalence-class count and diameter all drop as blindness "
        "drops, and classes fall 8 -> 5, so it is separating classes rather than "
        "merely shedding duplicates within one.\n\n"
        "**AND THEN IT STALLS, WHICH IS THE RESULT.** 249 of the 445 cells stay "
        "blind and **no sound check in this corpus closes any of them** -- 7 "
        "sound checks left unused. Five equivalence classes are still accepted. "
        "Blindness reduction at audit 0 does not reach equivalence here; it runs "
        "out of sound material at just over half the cells.\n\n"
        "**IT STALLS AT 56.0% AND CEIL2 STALLS AT 56.9%.** CEIL2 was selected BY "
        "the reference, on a different module, a different corpus and a "
        "different stimulus. Two procedures landing within a point of each other "
        "says ~56% is the **sound-check ceiling on this kind of corpus**, not an "
        "artifact of how CEIL2 was picked. It is also `no_sound_subset_of_this_"
        "corpus_forces_equivalence` arriving from the other direction.\n\n"
        "**DROP THE AUDIT CONSTRAINT AND IT CONSTRICTS ALL THE WAY -- PAST THE "
        "RIGHT ANSWER.** Allowing every deciding check: blindness 100% -> 14.6%, "
        "accepts 9 -> 1, classes 8 -> 1, diameter 0.108 -> **0.000**. One "
        "equivalence class, exactly the target -- except the FIRST check added "
        "convicts the control, so the surviving class **excludes the known-good "
        "design**. That is the screened set's failure reproduced: over-strictness "
        "and vacuity as one defect with two signs, at set level.\n\n"
        "**WHAT IT MEANS FOR THE PLAN.** Blindness is a real constriction lever "
        "and the risk was worth quantifying: it works, and it is bounded by the "
        "supply of SOUND discriminating checks, which this corpus exhausts at "
        "56%. So the lever that matters is not a better filter over these checks "
        "-- selection is already at its ceiling -- but more sound checks that "
        "speak at the 249 cells nothing currently adjudicates. That is E4's "
        "target, and this is the measurement that justifies aiming there.\n\n"
        "**THE STALL IS THE SUPPLY OF SOUND CHECKS, NOT THE ORDERING.** Greedy "
        "could have been the binding constraint. It is not: **200 random "
        "orderings of the nine sound checks all reach exactly 56.0%**. The set "
        "is exhausted, not the heuristic.\n\n"
        "**AND THE RESIDUE IS BROAD, NOT ONE BAD PORT** -- which is what makes "
        "it an authoring target rather than a bug:\n\n"
        "    port        blind cells   of total\n"
        "    sda_oen           96        175   54.9%\n"
        "    scl_oen           85        151   56.3%\n"
        "    cmd_ack           60         96   62.5%\n"
        "    busy               7         15   46.7%\n"
        "    dout               1          8   12.5%\n\n"
        "Three ports carry 241 of the 249, each roughly 55-63% blind.\n\n"
        "**THE SIX UNSOUND CHECKS ARE WORTH 41.3 POINTS OF BLINDNESS** -- 56.0% "
        "with them excluded, 14.6% with them in. That is the audit/blindness "
        "trade stated at set level on real data, and it is not incidental: **the "
        "checks that separate designs are largely the same checks that convict "
        "the control.** A check here is either discriminating and unsound or "
        "sound and blind, which is `soundness_and_blindness_are_one_knob` "
        "arriving from the design side rather than the selection side.\n\n"
        "**SCOPE, and it is narrow.** Nine designs of one module family; seven "
        "synthetic testpoints written for this experiment rather than a run's "
        "testplan; equivalence is TRACE equivalence over those testpoints, not a "
        "miter; and 15 deciding checks is a small corpus. The monotone "
        "direction survives all of that, and the 56.0% survives the ordering "
        "objection specifically -- 200 random orderings reach it -- but not "
        "the corpus size: nine sound checks exhausting at 56% says what THESE "
        "nine reach, not what a larger sound set would."
    )


@dataclass(frozen=True)
class Constriction:
    """What a check set does to the design space. The headline, not the triple.

    **SPAN / AUDIT / BLINDNESS ARE PROXIES FOR THIS.** Sufficiency is directly
    measurable without a reference -- if two designs both satisfy the set and
    are not equivalent to each other, the set does not force equivalence -- and
    both familiar failures are one quantity read at two ends: the screened
    114-check set accepts 1 of 7 at audit 10, the unanimous 89-check set accepts
    7 of 7 at audit 0.

    `admits_the_control` is the half that makes the rest meaningful and is
    `None` when no control was supplied. **Accepting exactly one class is a
    success only if the correct design is in it** -- otherwise it is the
    screened set's failure wearing a good number, which is exactly what E4b
    reproduced: dropping the audit constraint took classes 8 -> 1 and diameter
    to 0.000 while the first check added convicted the control.
    """

    accepted: tuple[str, ...]
    classes: int
    #: max pairwise disagreement fraction within the accepted set: how far from
    #: equivalence, graded, where the class count is only a cardinality
    diameter: float
    blind: float
    admits_the_control: bool | None


def constrict(population_cells: Sequence[Cell],
              verdicts: Mapping[str, Mapping[str, bool | None]],
              rows_by_design: Mapping[str, Mapping[str, Rows]],
              outputs: Sequence[str],
              *, control: Mapping[str, bool | None] | None = None,
              ) -> Constriction:
    """Read a check set as a constriction of the design space.

    A design is ACCEPTED when no check in the set convicts it. Rejections union
    -- "a design is rejected when ANY of 114 members objects" -- so adding
    checks constricts monotonically and the risk being measured is always
    over-constriction, never under.

    Equivalence here is TRACE equivalence over the testpoints supplied, which is
    a bounded approximation of the miter and says so: two designs identical on
    this stimulus may still differ elsewhere, so `classes` is a LOWER bound on
    how many the set really admits.
    """
    accepted = tuple(sorted(
        d for d in rows_by_design
        if not any(v.get(d) is False for v in verdicts.values())))

    def signature(design: str) -> tuple:
        rows = rows_by_design[design]
        return tuple(
            (tp, tuple(str((r.get("outputs") or {}).get(p))
                       for r in rows.get(tp, ()) for p in outputs))
            for tp in sorted(rows))

    worst = 0.0
    for i, a in enumerate(accepted):
        for b in accepted[i + 1:]:
            diff = total = 0
            for tp in sorted(set(rows_by_design[a]) & set(rows_by_design[b])):
                for ra, rb in zip(rows_by_design[a][tp], rows_by_design[b][tp]):
                    for p in outputs:
                        total += 1
                        if ((ra.get("outputs") or {}).get(p)
                                != (rb.get("outputs") or {}).get(p)):
                            diff += 1
            worst = max(worst, diff / total if total else 0.0)

    holes = blind(population_cells, verdicts)
    return Constriction(
        accepted=accepted,
        classes=len({signature(d) for d in accepted}),
        diameter=worst,
        blind=len(holes) / len(population_cells) if population_cells else 0.0,
        admits_the_control=(
            None if control is None
            else not any(control.get(c) is False for c in verdicts)),
    )


#: The stage name calls are recorded under. One per PORT, not per cell: forty
#: briefs for one blind port buys forty near-copies, which is what `ranked`
#: exists to prevent.
STAGE = "variety"

PARSE_ERROR = "Parse Error: "


@dataclass(frozen=True)
class Authored:
    """One reply. `source` empty means the author declined, which is a RESULT.

    **DECLINING HAS TO BE CHEAP OR THE GAP GETS FILLED WITH AN INVENTION.** The
    brief says so and this records it: a requirement that does not constrain the
    port is a finding about the SPECIFICATION, and the measured alternative is a
    model asked for something impossible complying rather than refusing -- the
    same reason `declines_discrimination` exists at all, and the reason
    `route_shows_issue` stopped demanding a discrimination in prose.
    """

    port: str
    source: str
    reasoning: str = ""

    @property
    def declined(self) -> bool:
        return not self.source.strip()


def author_at(targets: Sequence[tuple[str, Cell]],
              *, requirement_of, activation_of, driven_of, port,
              parse, round_: int = 0) -> tuple[Authored, ...]:
    """Ask for one check per blind PORT. Never raises.

    `targets` is `(req_uid, cell)` -- the requirement whose check is missing and
    the coordinate it is missing at. Everything the author sees goes through
    `brief`, which has no parameter for a design, its values, or a claim that
    either is right.

    A call that fails is a fact about the call, not about the specification: it
    comes back declined with the error in `reasoning`, exactly as
    `correspondence.review_one` treats an unreachable model, so a gateway
    outage cannot read as "the spec is silent here".
    """
    out: list[Authored] = []
    for uid, cell in targets:
        text = brief(cell, requirement=requirement_of(uid),
                     activation=activation_of(uid), driven=driven_of(cell))
        try:
            reply = port.complete(stage=f"{STAGE}_{cell.port}", round_=round_,
                                  prompt=text)
        except Exception as exc:  # noqa: BLE001
            out.append(Authored(port=cell.port, source="",
                                reasoning=f"{PARSE_ERROR}{exc!r}"))
            continue
        try:
            source, reasoning = parse(reply)
        except Exception as exc:  # noqa: BLE001
            out.append(Authored(port=cell.port, source="",
                                reasoning=f"{PARSE_ERROR}{exc!r}"))
            continue
        out.append(Authored(port=cell.port, source=source, reasoning=reasoning))
    return tuple(out)


def closed_by(authored_verdicts: Mapping[str, Mapping[str, bool | None]],
              was_blind: Sequence[Cell]) -> dict[str, tuple[Cell, ...]]:
    """Which of the previously-blind cells each new check actually closes.

    **THE ONLY NUMBER THIS PASS MAY BE JUDGED ON.** Not how many checks came
    back, not how many ran: how many cells that nothing adjudicated are now
    adjudicated, polarity-corrected. The prior round to beat re-authored with a
    witness in the prompt and reached "0 cells newly reached -- the rewrites'
    objections were a strict subset of what the set already caught", so a
    subset is the null however the count looks.
    """
    return {cid: tuple(c for c in was_blind if separates(c, v))
            for cid, v in authored_verdicts.items()}


def authoring_at_cells_closes_blindness_soundly_and_does_not_constrict() -> str:
    """E4, piloted live at THREE model calls. Driver: `docs/evidence/e4_pilot.py`,
    replies at `docs/evidence/e4-pilot-authored.json`.

    Pre-registered before the calls: <=15% of the residue closed ends the line;
    the stimulus round's comparable bar was 5%; the nearest prior -- re-authoring
    WITH a witness in the prompt -- reached 0 cells newly reached.
    """
    return (
        "Three blind ports, one call each, briefed with a LOCATION and the "
        "specification. No design, no observed values, no claim that either "
        "reading is right.\n\n"
        "    port       outcome                       closes   of   convicts control\n"
        "    sda_oen    DECLINED                          --   96                 --\n"
        "    scl_oen    authored                          66   85              FALSE\n"
        "    cmd_ack    authored                          30   60              FALSE\n\n"
        "**96 of 249 = 38.6% OF THE RESIDUE, AT AUDIT 0**, against a kill "
        "threshold of 15% and a nearest prior of 0. At SET level, with the nine "
        "sound checks already applied: **blindness 56.0% -> 14.6% from two "
        "checks**, 41.3 points.\n\n"
        "**AND 14.6% IS EXACTLY WHAT THE SIX CONTROL-CONVICTING CHECKS REACHED.** "
        "The same discrimination, bought without the over-strictness. That is "
        "the first thing on this project to get off "
        "`soundness_and_blindness_are_one_knob` rather than move along it, and "
        "it is the plan's thesis: the checks were not in the corpus, and no "
        "filter over the corpus could have found them.\n\n"
        "**THE DECLINE IS A RESULT, NOT A MISS.** `sda_oen` came back with no "
        "check and a reason -- the specification does not constrain that port in "
        "that scenario, because the driven command is not one the spec "
        "documents. That is a SPECIFICATION finding, and the brief exists to "
        "make it cheap: a model asked for something impossible complies rather "
        "than refuses, and an invented check would have been scored as closure "
        "here.\n\n"
        "**AND THE HALF THAT DID NOT WORK, WHICH MATTERS MORE THAN THE HALF THAT "
        "DID.** The constriction columns did not move at all: accepted designs "
        "3 -> 3, classes 3 -> 3, diameter 0.015 -> 0.015. **Blindness fell 41 "
        "points and the design space did not narrow by one design.** The cells "
        "the new checks closed lie between designs the set had ALREADY "
        "rejected, so separating them adjudicates a difference that changes no "
        "verdict. This is E4b's second pre-registered outcome arriving on the "
        "generation side: **blindness reduction and constriction are not the "
        "same quantity, and a blindness figure alone would have reported this "
        "round as a large success.**\n\n"
        "So the lever works on the leg it was aimed at and the leg it was aimed "
        "at is not sufficient. The next target is cells that separate designs "
        "still ACCEPTED -- rank the residue by whether closing it would change "
        "the accepted set, not by cell mass, which is what `ranked` does today.\n\n"
        "**SCOPE.** Two authored checks; nine designs of one module; seven "
        "synthetic testpoints; trace equivalence, not a miter; the audit is one "
        "control on those testpoints, so 'does not convict the control' is much "
        "weaker than a run's audit column. The 38.6% is a pilot, not a rate."
    )


def the_cells_that_would_constrict_are_the_ones_no_author_can_decide() -> str:
    """Three live pilots, nine model calls total. Drivers at
    `docs/evidence/e4_pilot.py` and `e4_pilot_constricting.py`.

    Pilot 1 ranked blind cells by MASS. Pilots 2 and 3 ranked by
    `constricting(..., both=True)` -- the 23 cells where both surviving designs
    disagree, so a check closing one must shrink the accepted set.
    """
    return (
        "    pilot  target            authored  declined  closes  constricts\n"
        "      1    by cell mass           2/3       1/3      96        NONE\n"
        "      2    must-shrink, cmd=4     0/3       3/3       0        NONE\n"
        "      3    must-shrink, cmd named 2/3       1/3       0        NONE\n\n"
        "**PILOT 1 IS THE POSITIVE AND IT IS REAL:** 96 of 249 cells closed at "
        "audit 0, blindness **56.0% -> 14.6%** from two checks -- the same "
        "blindness the six control-convicting checks reached, bought without "
        "the over-strictness.\n\n"
        "**AND IT CONSTRICTED NOTHING.** Its checks convicted `d, r, y` and "
        "`y`, every one already rejected. Accepted designs 3 -> 3, classes "
        "3 -> 3, diameter 0.015 unchanged.\n\n"
        "**PILOT 2 WAS MY DEFECT, NOT THE SPEC'S, AND PILOT 3 PROVES IT.** All "
        "three declines cited the numeric `cmd` value -- the specification names "
        "commands and never gives an encoding, so the author was asked to decode "
        "something the spec does not state. Naming the command took authoring "
        "from 0 of 3 to 2 of 3. **A decline cannot be read as a specification "
        "finding until the brief has been ruled out**, and here it was the brief "
        "twice.\n\n"
        "**PILOT 3 IS THE RESULT.** Given a correct brief at the cells where the "
        "surviving designs actually disagree, the author writes checks that "
        "**convict nobody** -- vacuous, blindness unchanged at 56.0% -- or "
        "declines, as `busy` did: 'the requirement only defines busy in terms of "
        "START and STOP detection'. Not one discriminating check in three "
        "attempts.\n\n"
        "**SO THE CONTRAST IS THE FINDING.** The cells between designs the set "
        "has ALREADY rejected are authorable and close in bulk. The 23 cells "
        "that would actually narrow the design space produce declines and "
        "vacuities. **The easy blindness is reachable by generation and the "
        "constricting blindness is not**, and that is the pre-registered kill "
        "condition arriving in its most informative form: the three surviving "
        "equivalence classes look specification-admissible, which is the finding "
        "this project exists to surface rather than a failure of the lever.\n\n"
        "**PILOT 4 RAN THE SAME THREE CELLS ON THE BIG MODEL, AND IT IS THE "
        "STRONGEST FORM OF THE RESULT.** `gpt-5.6-luna`, same brief:\n\n"
        "    sda_oen   authored -- convicts 8 of 9 designs INCLUDING all three\n"
        "              accepted, AND convicts the control\n"
        "    scl_oen   declined -- 'the specification is silent: it states that\n"
        "              an unsupported NOP command leaves the FSM idle, but it\n"
        "              does not define the ...'\n"
        "    busy      declined -- 'the specification does not constrain busy at\n"
        "              TP-arb; busy is history-dependent ...'\n\n"
        "So the stronger author declines with SPECIFIC citations of what the "
        "spec does and does not say, and where it does author, the only check "
        "that separates the surviving designs **also convicts the known-good "
        "control**. That is `soundness_and_blindness_are_one_knob` at its "
        "sharpest point: at the 23 cells that would constrict, the choice is a "
        "decline or an over-strict check, and there was no third option in six "
        "attempts across two models.\n\n"
        "**TOGETHER: two models, six attempts, ZERO sound discriminating checks "
        "at the constricting cells** -- while pilot 1 got two sound checks "
        "closing 96 cells at the non-constricting ones. The asymmetry is the "
        "result.\n\n"
        "**WHAT WOULD STILL OVERTURN IT.** One attempt per port and no repair "
        "round -- and the record says a stronger author helped on REPAIR, not on "
        "generation, which is the untried half; the whole 15KB specification "
        "passed as the requirement instead of a normalized one with a real "
        "activation; seven synthetic testpoints; 23 cells over three pairs. "
        "**A decline still means these authors could not find it, not that it "
        "is not there** -- but it is now two authors, and the big one refused "
        "by quoting the specification back."
    )


def the_constriction_ranking_was_gating_on_unverified_artifacts() -> str:
    """A RETRACTION of this module's own targeting refinement, caught by the
    user asking why a rejected design's disagreements should count for less.

    After the E4 pilot closed 96 cells and moved the accepted set by nothing,
    `constricting` and `ranked(accepted=...)` were added to aim authoring at
    cells whose closure would shrink that set. That ranking is circular and the
    measurement below shows it is fragile as well.
    """
    return (
        "**IT FILTERS EVIDENCE ABOUT THE SUITE USING THE SUITE'S OWN "
        "VERDICTS.** 'Already rejected' is not a fact about a design; it is the "
        "opinion of checks that are themselves under test, about designs none "
        "of which is verified. A disagreement between two spec-derived designs "
        "is a place the specification admits two behaviours and the suite "
        "adjudicates nothing, whatever the suite currently thinks of either "
        "design. This is the same circularity as the faithfulness gates this "
        "module was built to replace, reached through arithmetic instead of "
        "prose.\n\n"
        "**AND IT RESTS ON ONE CHECK.** Of the eight rejections that produced "
        "the accepted set `h, q, s`:\n\n"
        "    reauthor43:REQ-0101   carries 5\n"
        "    reauthor43:REQ-0075   carries 2\n"
        "    reauthor43:REQ-0073   carries 1\n\n"
        "Dropping REQ-0101 alone takes the accepted set to **`h, n, p, q, s, "
        "y`** -- three designs change status on one check's verdict, and that "
        "check's entire claim to soundness is sparing one control over seven "
        "testpoints written for the experiment.\n\n"
        "**WHICH MAKES THE RANKING NON-MONOTONE, and that is the disqualifying "
        "property.** Removing a BAD check re-values cells the ranking had "
        "zeroed. A target ranking that improves when the artifact under test "
        "gets worse is measuring the artifact, not the gap.\n\n"
        "**WHAT SURVIVES.** The arithmetic as an EXPLANATION: pilot 1's checks "
        "convicted `d, r, y` and `y`, all of which other checks already "
        "convicted, so 96 cells closed and the accepted set did not move. That "
        "is a true statement about the set as it stands and it stands. What is "
        "withdrawn is using it to choose what to author. **Rank targets by "
        "disagreement mass**, which reads only the designs.\n\n"
        "**AND IT PUTS THE E4 NULL BACK IN DOUBT, WHICH IS THE REAL COST.** "
        "Pilots 2-4 aimed at the 23 'must-shrink' cells and found no sound "
        "discriminating check in six attempts. Those 23 were selected by this "
        "ranking. If REQ-0101 is over-strict then the population was the wrong "
        "one, and the null is a null about a set chosen by a possibly-bad "
        "check rather than about authoring."
    )


def holds_over(inputs: Mapping[str, object], rows: Rows) -> int:
    """The longest run of consecutive rows the activation holds on. 0 if never.

    **THE MECHANICAL VERSION OF THE QUESTION `_names_a_window` ASKS LEXICALLY.**
    That screen compares the requirement TEXT against the normalized FORM and
    warns when they disagree about a span. It is a faithfulness instrument, it
    is 45% precise by its own calibration, and its docstring says the
    distinction it wants "depends on whether the activation outlasts its own
    trigger -- not on the word. No lexical split separates them."

    No lexical split does. A REPLAY does: run the activation's own `inputs`
    predicate along a trace and see how many consecutive rows satisfy it. One
    row is an instant and the form is right to carry no close condition. Several
    is a span, and a form with an empty `until` over it has flattened something
    real -- which is the defect, rather than the warning that gestures at it.

    Reads only spec-derived designs, like everything else here. A value is
    matched against the row's outputs first and its inputs second, which is the
    lookup order the authored checks use.
    """
    best = run = 0
    for row in rows:
        out = row.get("outputs") or {}
        ins = row.get("inputs") or {}
        if all(str(out.get(k, ins.get(k))) == str(v) for k, v in inputs.items()):
            run += 1
            best = max(best, run)
        else:
            run = 0
    return best


def flattened_a_span(activation: Mapping[str, object],
                     rows_by_design: Mapping[str, Mapping[str, Rows]],
                     *, at_least: int = 2) -> bool:
    """Did this form drop a span the designs actually exhibit?

    True when the activation carries no close condition AND its own predicate
    holds over `at_least` consecutive rows somewhere in the population. The
    check built from such a form reads one row where the behaviour occupies
    several -- "fails every design or passes every design depending only on
    which way the port sat at that instant", whose two symptoms are
    over-strictness and vacuity.

    An activation with no `inputs` is not judged: there is no predicate to run,
    so absence of evidence is reported as no finding rather than as a pass.
    """
    if activation.get("windowed") or activation.get("until"):
        return False
    inputs = activation.get("inputs") or {}
    if not inputs:
        return False
    return any(holds_over(inputs, rows) >= at_least
               for design in rows_by_design.values()
               for rows in design.values())



def the_window_screen_is_precise_where_it_can_be_checked_and_blind_elsewhere() -> str:
    """Measured against the mechanical test: 79% agreement, and a coverage gap.

    `_names_a_window` does not gate -- `has_errors` counts only
    `severity == "error"` and `run_stage` repairs only on `has_errors`, so the
    warning ships and blocks nothing. It is still a FAITHFULNESS instrument: it
    asks whether the normalized form is faithful to the requirement's PROSE and
    answers by matching words. `flattened_a_span` asks whether the form is
    faithful to what the DESIGNS DO and answers by replay. Running both over the
    same forms is the first time either has been checked against anything.
    """
    return (
        "**115 NORMALIZED FORMS OF `i2c_master_bit_ctrl`, 9 SPEC-DERIVED "
        "DESIGNS, ZERO MODEL CALLS.**\n\n"
        "    LEXICAL    warns                     62 of 115   53.9%\n"
        "    MECHANICAL can judge at all          37 of 115   32.2%\n"
        "               flattened a real span     26 of 37    70.3%\n\n"
        "    agree (warned AND flattened)         19\n"
        "    warned but NOT flattened             43   -- of which 38 are\n"
        "                                              not judgeable at all\n"
        "    flattened but NOT warned              7\n\n"
        "**ON THE 24 FORMS BOTH INSTRUMENTS CAN JUDGE, THEY AGREE ON 19 = "
        "79%.** That is the number that says something about the screen, and it "
        "is far better than the figure I had been quoting it at. The screen is "
        "not noise; where there is a predicate to run against it, it is right "
        "about four times in five.\n\n"
        "**THE 45% IS PRECISION AGAINST A DIFFERENT TARGET, AND I MISREAD IT.** "
        "`_WINDOW_WORDS` records `sequential + co-extensive  fires 73/105  "
        "recall 80%  precision 45%` -- calibrated against *a2-i2c's 41 "
        "known-bad CHECKS*, over-strict plus vacuous. That is precision at "
        "predicting a bad OUTCOME. `flattened_a_span` asks about the FORM: did "
        "this activation drop a span the designs exhibit. A form can flatten a "
        "span and still yield a check that happens to pass, and a bad check has "
        "many other ways to be bad. So the two numbers are not the same "
        "quantity, and **deflating E3's form-level count by a check-level "
        "precision, as I did, is a category error** -- it multiplied a count of "
        "forms by the hit rate of a different question.\n\n"
        "**THE REAL GAP IS COVERAGE, AND IT BELONGS TO `inputs`.** The "
        "mechanical test is silent on 78 of 115 forms because their activation "
        "carries no `inputs` predicate to run -- including **38 of the 62 the "
        "screen warns about**, so on the majority of its own warnings there is "
        "nothing to check it against. `Activation.inputs` is present 'only when "
        "the condition can be stated as input values', and a state-dependent "
        "activation legitimately has none. That is not a defect in either "
        "instrument; it is the measurement saying that two thirds of this "
        "module's forms cannot be audited against the designs at all from the "
        "activation alone.\n\n"
        "**AND THE SCREEN HAS FALSE NEGATIVES, WHICH NOTHING PREVIOUSLY "
        "MEASURED.** 7 forms flattened a span the designs exhibit while naming "
        "no window word. Its recorded recall of 80% is against the same "
        "known-bad-check target; against span-flattening on the judgeable "
        "subset it is 19 of 26 = 73%.\n\n"
        "**NEITHER GATES, AND THE MECHANICAL ONE MUST NOT START.** It reads "
        "spec-derived designs, so it says where the specification is "
        "under-determined by the form -- not which form is correct. Its use is "
        "to RANK forms for re-normalization and to size the residual, which is "
        "the use the lexical screen is kept for, under the same rule: reporting "
        "is the right use of a screen, and blocking on one is how a "
        "faithfulness gate gets built by accident."
    )


def refuted_by_the_population(
        verdicts: Mapping[str, Mapping[str, bool | None]],
        *, quorum: int | None = None) -> tuple[str, ...]:
    """Checks that convict EVERY spec-admissible design they decide on.

    **THE DUAL OF `vacuous:`, AND THE PIPELINE BLOCKS ONLY ONE SIGN.** A check
    nothing can move is `DEAD_ORACLE` and blocks. A check that convicts
    everything is the same defect with the other sign -- "over-strictness and
    vacuity as one defect with two signs" -- and nothing stops it. The argument
    is not statistical: the specification admits at least seven equivalence
    classes and the correct design is one of them, so a check convicting the
    whole admissible population has convicted the correct design too, unless
    the specification is unsatisfiable.

    **GOLDEN-FREE, and structurally so** -- the only argument is `verdicts`
    over spec-derived designs. There is no parameter a reference could arrive
    through, which is the same enforcement `brief` uses.

    **AND IT COSTS NO BLINDNESS, WHICH IS WHY IT IS FREE RATHER THAN A TRADE.**
    A check convicting both sides of every pair SEPARATES nothing: `separates`
    is False on every cell it touches, so removing it cannot open a cell that
    was closed. Measured on the 37-check unbiased set -- audit 50% -> 22%,
    blindness unmoved at 15.5%, `effective_size` 9 -> 8.

    `quorum` is how many designs it must have decided on to be judged; the
    default is ALL of them. A check deciding on two of nine and convicting both
    has not met the population, and calling that a refutation would convict it
    for the stimulus's silence -- the conflation `min_decides` documents.
    """
    designs = {d for per in verdicts.values() for d in per}
    need = len(designs) if quorum is None else quorum
    out = []
    for cid, per in verdicts.items():
        decided = [v for v in per.values() if v is not None]
        if len(decided) >= need and decided and all(v is False for v in decided):
            out.append(cid)
    return tuple(sorted(out))
