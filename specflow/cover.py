"""The SHIPPED set: the fewest bodies that separate every cell the pool separates.

**EVERY SELECTION RULE MEASURED ON THIS BRANCH TRADES ONE COLUMN FOR ANOTHER, AND
THIS ONE CANNOT, BY CONSTRUCTION.** `FRONTIER.md` reduces the frontier to one
sentence: the checks that convict a correct design are also the checks that
separate the population. A filter that drops objectors takes separators with
them; a filter that drops checks objecting where designs AGREE still loses the
few cells such a check separates.

The question none of those rules asks is whether a body separates any cell that
no other kept body separates. If not, dropping it leaves the separated SET
unchanged -- so blindness is identical -- and one fewer body is one fewer chance
to convict a correct design, because rejections union:

    keep bodies greedily, always the one separating the most cells not yet
    separated, until none separates anything new; then give every requirement
    that lost all its bodies its best single contributor back, so span holds.

  * **BLINDNESS IS PRESERVED EXACTLY.** Greedy set cover changes how MANY sets
    are used, never which cells their union holds.
  * **SPAN IS PRESERVED** by the per-requirement floor.
  * **AUDIT CAN ONLY FALL OR STAY**: the kept set is a subset of the pool, and a
    subset of objectors cannot convict more.

**POPULATION-ONLY, AND THAT IS THE WHOLE LICENCE.** Cells come from the
spec-derived designs; each body's separation comes from replaying it against
them. No control, no witness and no reference design is read, so this cannot be
gating on the grade. It is deterministic given its inputs -- ties go to the
earlier body in pool order, and the floor breaks its ties on a key that ends in
the body's own name -- so the same run always ships the same set.

Measured first as a driver (`docs/evidence/e6_cover.py`, `COVER.md`) on the
frozen `full2` corpus: the pool's blindness held to four places while audit fell
from 4 of 45 to 1 of 38. It lives here so that a run ships the set itself rather
than leaving the selection to whoever scores it afterwards.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

from . import variety as V


@dataclass(frozen=True)
class Cover:
    """What the cover kept, and the numbers that say why."""

    #: Body keys, in the order they were taken: greedy picks first, then floor.
    kept: tuple[str, ...]
    #: How many of `kept` the greedy cover chose.
    greedy: int
    #: How many the span floor restored -- requirements whose every body was
    #: redundant to the cover.
    floored: int
    #: Disagreement cells in the population, and how many the POOL separates.
    #: The cover separates exactly the same number; `separated_by_cover` is
    #: recorded so that claim is checked on every run rather than asserted.
    cells: int
    separated_by_pool: int
    separated_by_cover: int


def separation(cells: Sequence, by_tp: Mapping[str, Mapping]) -> dict[str, frozenset]:
    """`body -> the cells it separates`, one body at a time.

    `variety.separates_at` is the shipped predicate, and asking it with a single
    body's table gives exactly that body's contribution -- the same instrument
    the scorecard's blindness column is computed with, so the cover and the card
    cannot disagree about what a body separates.
    """
    return {key: frozenset(c for c in cells if V.separates_at(c, table))
            for key, table in by_tp.items()}


def greedy_cover(order: Sequence[str], sep_of: Mapping[str, frozenset],
                 req_of: Mapping[str, str],
                 convictions: Mapping[str, int]) -> tuple[list[str], int]:
    """`(kept, how many the greedy step chose)`. Pure; see the module docstring.

    `order` is the pool order and decides ties, so a body only displaces an
    earlier one by separating strictly more. The floor chooses, per requirement
    left without a body, the one separating the most cells, then the one the
    population convicts least, then the lower key -- the second key is
    `max_convictions` used as a tie-break INSIDE a requirement, never as a
    global filter, so it can only choose among bodies that separate equally
    and cannot cost a cell.
    """
    remaining = set().union(*(sep_of.get(k, frozenset()) for k in order))
    kept: list[str] = []
    taken: set[str] = set()
    while remaining:
        best, gain = None, 0
        for key in order:
            if key in taken:
                continue
            g = len(sep_of.get(key, frozenset()) & remaining)
            if g > gain:
                best, gain = key, g
        if best is None:
            break
        kept.append(best)
        taken.add(best)
        remaining -= sep_of[best]
    chosen = len(kept)

    have = {req_of[k] for k in kept}
    for key in order:
        uid = req_of[key]
        if uid in have:
            continue
        best = min((k for k in order if req_of[k] == uid),
                   key=lambda k: (-len(sep_of.get(k, ())),
                                  convictions.get(k, 0), k))
        kept.append(best)
        have.add(uid)
    return kept, chosen


def select(held: Mapping, req_of: Mapping[str, str], population: Sequence[str],
           contract: dict, stimulus_by_tp: dict, *, base: str,
           transactional: bool = True) -> Cover | None:
    """The cover of `held` (body key -> `RequirementOracle`) over `population`.

    `None` when there is no population to cover against -- fewer than two
    designs, or two that agree everywhere. Then no body can be shown redundant,
    and shipping the pool unchanged is the only answer that does not invent a
    reason to drop something.
    """
    from .oracles_stage import _population_rows, _population_tables

    outputs = [str(p.get("name")) for p in (contract.get("io") or [])
               if p.get("dir") == "output" and p.get("name")]
    rows_by_design = _population_rows(
        list(population), contract, stimulus_by_tp, base=base,
        transactional=transactional)
    if len(rows_by_design) < 2:
        return None
    cells = V.cells(rows_by_design, outputs)
    if not cells:
        return None
    verdicts, by_tp, _obj = _population_tables(
        dict(held), list(population), contract, stimulus_by_tp, base=base,
        transactional=transactional)
    sep_of = separation(cells, by_tp)
    convictions = {k: sum(1 for x in (verdicts.get(k) or {}).values()
                          if x is False) for k in held}
    kept, chosen = greedy_cover(list(held), sep_of, req_of, convictions)
    pool = set().union(*sep_of.values()) if sep_of else set()
    mine = set().union(*(sep_of.get(k, frozenset()) for k in kept))
    return Cover(kept=tuple(kept), greedy=chosen, floored=len(kept) - chosen,
                 cells=len(cells), separated_by_pool=len(pool),
                 separated_by_cover=len(mine))
