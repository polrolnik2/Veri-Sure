"""What the suite has REACHED, read off recorded replays. No model calls.

The staging loop's model of an abstention is "the stimulus never got the design
into the state the check is waiting for", and it has exactly one response: mint
another testpoint. Triaging k1's 25 never-firing checks against recorded
internals tests that model directly, and it is the wrong response most of the
time -- of the 15 whose requirement names a state, 11 had the state REACHED on
the check's own testpoints and the check stayed silent anyway. That is a defect
in the check, not in the stimulus, and staging harder cannot fix it.

The loop could not tell those apart because it could not see the one fact that
decides it: whether the state was entered. `decide()` reads `row["outputs"]`,
and the state was not there. Once a state is a declared probe it IS there, and
this module is the arithmetic over those rows.

WHAT EVERY ROW HERE IS, stated once because it is easy to forget downstream.
`stage_unexercised` runs before any RTL exists, so every row this module reads
comes from replaying the WITNESS -- a Python model an LLM wrote from the
requirements and the contract. The pool, the mined relation and every "P rose on
tp_0007 at edge 12" are the witness's transitions, not the design's, and the
witness/golden divergence is measured at 12.8% of port-samples across 6 of 10
ports. That is the same footing every other oracle-stage verdict already stands
on -- a check's pass/fail, `must_fail`, `liveness` all replay against the witness
-- so a probe observed on the witness is no less grounded than an output observed
on it. But it is not the design, and nothing here may be read as if it were.

NOTHING HERE ASSIGNS `UNREACHABLE`, and nothing here may. A probe that is never
observed is a staging target, not a discard: absence from a sample is not proof
of absence from the design. The only authority for unreachability is a
k-induction proof on the GENERATED RTL (`unreach.discharge_bin`), which cannot
run until RTL exists and therefore never runs in the oracle stage.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .refmodel.base import probe_names

#: An edge is quotable as *how this state was entered* only above both. Rises
#: because one observation is not a relation, and precision because a conjunction
#: mined over a branchy transition keeps only the intersection of its branches --
#: measured on k1, every transition that ENTERS a state mines clean (`in_cload <-
#: in_idle` 99.9%, `in_lrefill3 <- in_cload` 100%) while `in_idle` overall sits at
#: 11.8%, because golden exits CLOAD to IDLE four ways. A stimulus author never
#: needs a recipe for the state it is leaving, so the low-precision half is
#: simply not quoted.
MIN_RISES = 5
MIN_PRECISION = 0.90


@dataclass(frozen=True)
class Observation:
    """One testpoint that reached one probe, and how soon."""

    tp_uid: str
    first_edge: int
    held: int
    rises: int


@dataclass(frozen=True)
class Edge:
    """A mined transition INTO a state. Annotation, never a recipe.

    There is no edge into a state that has never risen, which is the whole reason
    adjacency for an unobserved state is the stimulus author's call and not this
    module's: mining needs a rise of B to mine an edge into B.
    """

    frm: str
    to: str
    requires: dict
    rises: int
    precision: float
    source: str = "witness"


@dataclass
class Relation:
    edges: list[Edge] = field(default_factory=list)

    def into(self, probe: str) -> list[Edge]:
        return sorted((e for e in self.edges if e.to == probe),
                      key=lambda e: (-e.rises, e.frm))


def rows_for(witness: str, stimulus_by_tp: dict[str, list[dict]],
             contract: dict, *, base: str = "step") -> dict[str, list[dict]]:
    """Replay every testpoint against the witness and KEEP the rows.

    This exists because nothing in the oracle stage keeps them.
    `unexercised_against` and `_decides` both call `replay()` and return
    verdicts, discarding the rows, so the pool cannot be built "from rows it
    already has" -- it needs this one added pass. Replay is Python against the
    witness with no model call; on k1 it is 60 testpoints.

    RAW per-edge rows, deliberately not `transactional_view`. Two things here
    need edge adjacency that compression destroys: mining reads row i-1 against
    row i, and `stimulus_prefix` maps a rising edge back to a stimulus step by
    cumulative duration. Checks still decide over the compressed view; these are
    two different questions about the same replay.
    """
    from .refmodel.oracles import replay

    out: dict[str, list[dict]] = {}
    for tp_uid, steps in sorted((stimulus_by_tp or {}).items()):
        if not steps:
            continue
        run = replay(witness, contract, steps, base=base)
        if run.error:
            continue
        out[tp_uid] = run.rows
    return out


def _is_high(row: dict, name: str) -> bool:
    return bool((row.get("outputs") or {}).get(name))


def observed(rows_by_tp: dict[str, list[dict]],
             probes: list[str]) -> dict[str, list[Observation]]:
    """The pool: every probe, and every testpoint that reached it.

    Sorted so the SHORTEST reproducer comes first. That is the one handed to a
    stimulus author, because a shorter prefix leaves more room to extend and
    less to misread.

    A never-observed probe is an empty list and nothing more. It is not a
    discard and carries no hypothesis -- it is the strongest staging signal
    there is, and the only thing the oracle stage is entitled to say.
    """
    pool: dict[str, list[Observation]] = {p: [] for p in probes}
    for tp_uid, rows in sorted(rows_by_tp.items()):
        for probe in probes:
            first: int | None = None
            rises = 0
            prev = False
            for row in rows:
                now = _is_high(row, probe)
                if now and not prev:
                    rises += 1
                    if first is None:
                        first = int(row.get("edge", 0))
                prev = now
            if first is None:
                continue
            pool[probe].append(Observation(
                tp_uid, first, _held_from(rows, first, probe), rises))
    for probe in pool:
        pool[probe].sort(key=lambda o: (o.first_edge, o.tp_uid))
    return pool


def _held_from(rows: list[dict], first_edge: int, probe: str) -> int:
    """How many consecutive edges the probe stayed high from its first rise."""
    held = 0
    started = False
    for row in rows:
        if int(row.get("edge", -1)) < first_edge:
            continue
        if _is_high(row, probe):
            held += 1
            started = True
        elif started:
            break
    return held


def mine(rows_by_tp: dict[str, list[dict]], probes: list[str]) -> Relation:
    """The transition relation, keyed on `(from, to)`, with holdout precision.

    TWO measured decisions are baked in, and both were wrong the first time.

    STATE AT i-1, INPUTS AT i. The first attempt read the inputs from the same
    edge as the FROM state and produced conditions that were necessary but 1.3
    to 25% precise: `biudata_valid` dropped out of every recipe entirely, being
    edge-triggered and high on 16 of 81 rises at the earlier edge against 81 of
    81 at the later one. Wrong here, the artifact is worthless while looking
    entirely plausible.

    KEYED ON `(from, to)`, not on the destination alone. Splitting by source is
    what makes every ENTERING transition mine clean; it does not rescue a state
    with several exits, and it is not asked to.
    """
    tps = sorted(rows_by_tp)
    train = {t: rows_by_tp[t] for t in tps[0::2]}
    holdout = {t: rows_by_tp[t] for t in tps[1::2]} or train

    rel = Relation()
    for to in probes:
        by_source: dict[str, list[dict]] = {}
        for rows in train.values():
            for frm, inputs in _rises(rows, to, probes):
                by_source.setdefault(frm, []).append(inputs)
        for frm, samples in sorted(by_source.items()):
            # The conjunction: every (input, value) pair common to EVERY rise.
            common = dict(samples[0])
            for s in samples[1:]:
                common = {k: v for k, v in common.items() if s.get(k) == v}
            if not common:
                continue
            hits, matches = 0, 0
            for rows in holdout.values():
                h, m = _score(rows, frm, to, common, probes)
                hits += h
                matches += m
            rel.edges.append(Edge(
                frm=frm, to=to, requires=common, rises=len(samples),
                precision=(hits / matches) if matches else 0.0))
    return rel


def _rises(rows: list[dict], to: str, probes: list[str]):
    """`(from_state, inputs)` for every rise of `to` in one testpoint."""
    for i in range(1, len(rows)):
        if _is_high(rows[i], to) and not _is_high(rows[i - 1], to):
            frm = next((p for p in probes
                        if p != to and _is_high(rows[i - 1], p)), "")
            yield frm, dict(rows[i].get("inputs") or {})


def _score(rows: list[dict], frm: str, to: str, requires: dict,
           probes: list[str]) -> tuple[int, int]:
    """`(hits, matches)` for one mined edge over one held-out testpoint."""
    hits = matches = 0
    for i in range(1, len(rows)):
        prev_ok = _is_high(rows[i - 1], frm) if frm else not any(
            _is_high(rows[i - 1], p) for p in probes)
        if not prev_ok:
            continue
        ins = rows[i].get("inputs") or {}
        if any(ins.get(k) != v for k, v in requires.items()):
            continue
        matches += 1
        if _is_high(rows[i], to) and not _is_high(rows[i - 1], to):
            hits += 1
    return hits, matches


def gate_reachability(edge: Edge) -> bool:
    """May this edge be quoted to a stimulus author as how a state is entered?

    A mined edge is an ANNOTATION on a stimulus that really ran, never a recipe
    to build one from. Below the thresholds it is simply omitted: the prefix
    still goes over, unexplained, which is strictly better than an explanation
    that is wrong.
    """
    return edge.rises >= MIN_RISES and edge.precision >= MIN_PRECISION


def stimulus_prefix(stimulus: list[dict], rise_edge: int) -> list[dict]:
    """The steps up to and including the one that reached the state, plus one.

    The extra step is the one that HELD the state, so the author sees what kept
    it there rather than only what entered it.

    Edges map to steps by cumulative duration. If a stimulus's step boundaries
    cannot be recovered the WHOLE stimulus is returned rather than a guess --
    nothing is lost, only room to extend.
    """
    if rise_edge < 0:
        return list(stimulus or [])
    edges = 0
    for idx, step in enumerate(stimulus or []):
        span = _duration(step)
        if span is None:
            return list(stimulus or [])
        edges += span
        if edges > rise_edge:
            return list(stimulus[: idx + 2])
    return list(stimulus or [])


def _duration(step: dict) -> int | None:
    for key in ("hold", "duration", "edges", "cycles"):
        if key in (step or {}):
            try:
                return max(1, int(step[key]))
            except (TypeError, ValueError):
                return None
    # A step with no stated duration is one edge, which is the runtime's own
    # default; `until` steps have no fixed length and are the case that gives up.
    return None if (step or {}).get("until") else 1


def own_reached(tp_uids: list[str], pool: dict[str, list[Observation]]) -> list[str]:
    """The pool states THIS check's own testpoints reached.

    These are the ones whose full prefixes go into the hint. Every other pool
    state is listed with its span and tp_uid and can be asked for by name on a
    retry -- the block stays readable, and the states most likely to be relevant
    are the ones this check's own stimulus already touched.
    """
    mine_ = set(tp_uids or [])
    return sorted(p for p, obs in pool.items()
                  if any(o.tp_uid in mine_ for o in obs))


def schedule(waiting: dict[str, list[str]],
             pool: dict[str, list[Observation]]) -> list[str]:
    """Which abstaining checks to stage, in order. Deterministic.

    `waiting` maps a requirement uid to the probes its window names.

    Only checks whose target is UNOBSERVED schedule at all: one whose probe the
    pool already has routes elsewhere -- to the check author if its own
    testpoints reached it, or to the stimulus author with that reproducer if
    another testpoint did.

    The order is dependents descending, then uid. A success on the state with
    the most checks waiting unblocks the most, and the pool is monotone, so the
    order decides how much every later author gets to see. There is deliberately
    no depth or distance term: neither exists for a state nothing has reached,
    and "hand over the deepest state" is a chain heuristic that picks the wrong
    branch on a fork -- k1 forks at CLOAD and CSTORE, at the same depth.
    """
    unobserved = {p for p, obs in pool.items() if not obs}
    target: dict[str, str] = {}
    for uid, probes in (waiting or {}).items():
        want = sorted(set(probes or []) & unobserved)
        if want:
            target[uid] = want[0]
    dependents: dict[str, int] = {}
    for probe in target.values():
        dependents[probe] = dependents.get(probe, 0) + 1
    return sorted(target,
                  key=lambda u: (-dependents[target[u]], target[u], u))


def waiting_on(normalized_entry: dict, probes: list[str]) -> list[str]:
    """The probes a check needs REACHED before it can decide anything.

    Read from the normalized activation, which is the one thing that says what
    a check watches without executing it. Three window fields and the effect:

    * `opens_on` / `until` / `aborts_on` -- what scopes the window. A window
      keyed on a state cannot open until the state is entered.
    * `observable` -- what the check asserts. Included because the scope rule
      was withdrawn to a default: a transition obligation states its effect ON
      the state ("the FSM advances to LREFILL3"), so a check whose asserted
      effect is a probe needs that state reached just as surely as one whose
      window is.

    `activation.inputs` is deliberately NOT read: those are drivable input ports
    by construction, and a probe can never be among them.
    """
    want = set(probes or ())
    if not want:
        return []
    act = (normalized_entry or {}).get("activation") or {}
    found: set[str] = set()
    for field_ in ("opens_on", "until", "aborts_on", "sustains"):
        for clause in (act.get(field_) or []):
            if isinstance(clause, dict):
                found |= (set(clause) & want)
    found |= (set((normalized_entry or {}).get("observable") or []) & want)
    return sorted(found)


def budget_for(waiting: dict[str, list[str]], pool: dict[str, list[Observation]],
               *, per_state: int, cap: int) -> int:
    """Size the staging budget PER STATE, not per check.

    One testpoint that reaches P serves every check waiting on P, so N checks
    blocked on one unobserved state need one allocation between them, not N. On
    k1 the eight SREFILL4 dependents burned three attempts each and went
    `ABANDONED` eight times over; here they share three.

    A check whose window names NO probe keeps its own allocation. That bucket is
    not empty -- on k1, 10 of the 25 abstainers name no state at all -- and
    nothing about this change reaches them, so nothing about their budget should
    change either.

    Checks waiting on a state the pool ALREADY has do not schedule and are not
    counted: they route to the check author, whose own testpoints reached the
    state, or take the existing reproducer. Neither spends a discovery attempt.
    """
    unobserved = {p for p, obs in (pool or {}).items() if not obs}
    states: set[str] = set()
    legacy = 0
    for probes in (waiting or {}).values():
        named = set(probes or [])
        if not named:
            legacy += 1
            continue
        blocked = named & unobserved
        if blocked:
            states |= blocked
    return min(cap, max(1, len(states) + legacy) * per_state)


def to_json(*, states: dict, pool: dict[str, list[Observation]],
            relation: Relation, hypotheses: dict | None = None,
            proofs: dict | None = None, path: Path | None = None) -> dict:
    """The artifact. `observed` is the pool; `proofs` is the only authority.

    `hypotheses` is what the probe stage was licensed by a spec span to SUSPECT;
    `proofs` is what a prover on the generated RTL established, with the
    assumption set it was proved under. Nothing here assigns `UNREACHABLE`
    except a `proofs` entry, and there is deliberately no list derived from the
    sample: a state absent from every replay is a staging target.

    There is no `schedule` list either. Per-attempt outcomes extend
    `stage_unexercised`'s existing per-requirement `record`, which is already
    persisted, rather than being duplicated into a second place that can drift.
    """
    doc = {
        "states": states,
        "edges": [
            {"from": e.frm, "to": e.to, "requires": e.requires,
             "rises": e.rises, "precision": round(e.precision, 4),
             "source": e.source, "quotable": gate_reachability(e)}
            for e in sorted(relation.edges, key=lambda e: (e.to, e.frm))
        ],
        "observed": {p: [asdict(o) for o in obs] for p, obs in sorted(pool.items())},
        "unreached_from_pool": sorted(p for p, obs in pool.items() if not obs),
        "hypotheses": hypotheses or {},
        "proofs": proofs or {},
        "note": ("pool, relation and every edge here are the WITNESS's replays, "
                 "not the design's; hypotheses are spec spans; only a proofs "
                 "entry disposes, and only a prover on generated RTL writes one"),
    }
    if path is not None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(json.dumps(doc, indent=1, sort_keys=True) + "\n",
                              encoding="utf-8")
    return doc


def states_from(contract: dict) -> dict:
    """`states` for the artifact: each probe with what licenses it.

    The spans are copied in so the pool table in a stimulus hint can show each
    state's spec text without the hint having to reach back into the contract.
    """
    out: dict = {}
    for p in (contract.get("io") or []):
        if p.get("dir") != "probe" or not p.get("name"):
            continue
        out[str(p["name"])] = {
            "spec_term": p.get("spec_term") or p.get("notes") or "",
            "licensed_by": list(p.get("licensed_by") or []),
            "spans": list(p.get("spans") or []),
        }
    return out


def probes_of(contract: dict) -> list[str]:
    """The contract's probe names. One reader, so the order never diverges."""
    return probe_names(contract)
