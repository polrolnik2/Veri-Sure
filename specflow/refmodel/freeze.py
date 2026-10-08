"""The oracle set, written once and read forever.

The judge-driven loop was measured re-randomising its own metric: no oracle
source was identical between rounds (72 of 77 rewritten r0 to r1, 71 of 77 r1 to
r2), 38 requirements changed verdict per turn, and 100% of those had a rewritten
oracle. CONFORMS went 30, 33, 30 -- a random walk, not convergence. A measure
that moves under the thing being measured cannot report progress, so "N failing
oracles going to zero" meant nothing.

Freezing is what makes it mean something, and a file is what makes freezing
checkable rather than conventional. This is `freeze_denominator`'s discipline
(`specflow/coverage.py:74`) applied one level up: written at entry, read
forever, so the set cannot grow or drift while the loop runs against it.

Two hashes, because two different things can change and only one of them is a
defect.

* `hash` covers what the oracle was ASKED -- the normalized requirement -- plus
  what it ANSWERED: the clause and the decision procedure. A change here means
  the oracle is a different oracle. Within one run that is a bug; across a
  `--reuse` re-entry it means the frozen file is stale for a requirement whose
  text moved.
* `evidence` covers `tp_uids` alone. `add_stimulus` appends a testpoint to an
  oracle's evidence set on purpose (see `session.add_stimulus`), so this changing
  is expected and legitimate -- it is not drift. It is the I7 trigger: an oracle
  that GAINED a testpoint must re-run its own must-fail check, because what it
  was proved against is no longer what it is decided against.

Deliberately NOT in either hash: the reference model. An oracle written from the
requirement alone does not depend on the implementation, which is the whole
reason it can be frozen at all.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .oracles import RequirementOracle


def _digest(payload: object) -> str:
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def content_hash(oracle: RequirementOracle,
                 normalized: dict | None = None) -> str:
    """The question and the answer. `tp_uids` is deliberately excluded."""
    norm = normalized or {}
    return _digest({
        "req_uid": oracle.req_uid,
        "activation": norm.get("activation"),
        "observable": sorted(norm.get("observable") or []),
        "expectation": norm.get("expectation") or "",
        "clause": oracle.clause,
        "source": oracle.source,
    })


def evidence_hash(oracle: RequirementOracle) -> str:
    """What the oracle is decided against. Changes when stimulus is appended."""
    return _digest(sorted(oracle.tp_uids))


def stamp(oracles: list[RequirementOracle],
          normalized: dict[str, dict] | None = None) -> list[RequirementOracle]:
    """Return the same oracles carrying their content hash."""
    norm = normalized or {}
    return [
        o.model_copy(update={"hash": content_hash(o, norm.get(o.req_uid))})
        for o in oracles
    ]


def drift(oracles: list[RequirementOracle],
          frozen: list[RequirementOracle],
          normalized: dict[str, dict] | None = None) -> dict[str, str]:
    """`{req_uid: why}` for every oracle that is not the one frozen.

    Reported, never repaired here. A caller inside one run treats a non-empty
    result as a defect; a caller re-entering with `--reuse` treats it as a
    requirement whose text moved and whose proofs are stale.
    """
    norm = normalized or {}
    was = {o.req_uid: o for o in frozen}
    out: dict[str, str] = {}
    for o in oracles:
        prior = was.get(o.req_uid)
        if prior is None:
            out[o.req_uid] = "not in the frozen set"
            continue
        now = content_hash(o, norm.get(o.req_uid))
        then = prior.hash or content_hash(prior, norm.get(o.req_uid))
        if now != then:
            out[o.req_uid] = f"{then} -> {now}"
    for uid in was:
        if not any(o.req_uid == uid for o in oracles):
            out[uid] = "dropped from the regenerated set"
    return out


def load(path: Path) -> list[RequirementOracle]:
    """The frozen set, or an empty list if nothing was ever frozen here."""
    path = Path(path)
    if not path.exists():
        return []
    try:
        blob = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [RequirementOracle.model_validate(o)
            for o in (blob.get("oracles") or [])]


def freeze(oracles: list[RequirementOracle], path: Path,
           normalized: dict[str, dict] | None = None,
           extra: dict | None = None,
           rewrite: bool = False,
           ) -> tuple[list[RequirementOracle], dict[str, str]]:
    """Write once and return what is frozen, plus any drift against it.

    The FROZEN set wins. Returning the regenerated one on a mismatch would make
    the file a log rather than a freeze, and the loop would go back to measuring
    against something that moves.

    `rewrite` is the one deliberate exception: a strengthening round asked for a
    replacement oracle ON PURPOSE, having been shown a design the old one could
    not catch. That is a new version, not drift, and it re-freezes under a new
    hash so the loop measuring against it can still prove which one it holds.
    Callers must not reach for this to get past a mismatch they did not intend.
    """
    path = Path(path)
    stamped = stamp(oracles, normalized)
    prior = load(path)
    if prior and not rewrite:
        return prior, drift(stamped, prior, normalized)

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({
            "oracles": [
                {**o.model_dump(), "evidence": evidence_hash(o)}
                for o in stamped
            ],
            # The stage's own record travels in the same file, because the
            # trusted set and the reason every other requirement is NOT in it
            # are one artifact: reading either alone is how a silent subset gets
            # missed.
            **(extra or {}),
        }, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8")
    return stamped, {}


def stale_proofs(oracles: list[RequirementOracle],
                 proofs: dict[str, str]) -> list[str]:
    """I7, narrowed to what append-only stimulus can actually invalidate.

    `proofs` maps `req_uid` to the `evidence` hash the must-pass/must-fail legs
    were run against. An oracle whose evidence set has since changed needs those
    legs re-run and nothing else does -- existing stimulus is never edited, so no
    other proof can go stale.
    """
    return sorted(o.req_uid for o in oracles
                  if o.req_uid in proofs
                  and proofs[o.req_uid] != evidence_hash(o))
