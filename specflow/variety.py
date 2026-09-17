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


def ranked(blind_cells: Sequence[Cell]) -> tuple[tuple[str, int], ...]:
    """Blind cells collapsed to `(port, count)`, heaviest first.

    Authoring targets are ports, not individual cells: the same output blind on
    forty cells is one question to an author, and forty briefs would buy forty
    near-copies of one check -- the failure mode this module exists to avoid.
    Measured on the store write-through path, blindness collects at 5x on four
    ports, so the mass is concentrated enough for this to matter.
    """
    tally: dict[str, int] = {}
    for c in blind_cells:
        tally[c.port] = tally.get(c.port, 0) + 1
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
