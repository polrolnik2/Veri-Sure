"""The prompt shape every fanned-out stage must have, defined once.

A stage that runs one call per item is only affordable if every one of those
calls opens with a byte-identical block the provider caches. Measured live, that
is a 97% hit on a ~5,240-token prefix; lose it and the stage costs ~30x more
while succeeding, validating and gating exactly as before. Nothing notices.

So the ordering is not left to each stage to remember:

    [ shared block ][ SENTINEL ][ item ][ previous answer ][ gate failures ]

`compose` is the only way a fanned-out prompt gets built, and
`tests/test_specflow_cache.py` asserts the property over every stage that uses
it. Two things follow from the order and both have already gone wrong somewhere
in this repo:

* **nothing per-item may appear before the sentinel** -- not an index, not a uid,
  not a count. "Requirement 5 of 137" in a header is the whole cache, gone.
* **repair material appends after the item**, so round 1 still opens with round
  0's prefix. `run_stage` hands `build_prompt` both `issues` and `previous`,
  which gives a caller two ways to prepend by accident.
"""

from __future__ import annotations

import hashlib
import json
import logging

from .schema import Issue
from .stage import gate_failures_block, previous_answer_block

logger = logging.getLogger(__name__)

#: Ends the shared block. A literal marker rather than an implicit boundary, so
#: a test can assert *where* prompts diverge instead of merely that they do.
PREFIX_SENTINEL = "\n</shared_context>\n"

#: The provider caches from 1024 tokens up, in 128-token increments. BELOW IT
#: NOTHING CACHES AT ALL -- not a smaller discount, none -- so a stage whose
#: shared block is short pays full price on every call while looking, in the
#: artifacts, exactly like a stage that caches perfectly.
#:
#: Found the hard way. `correspondence.build_prompt` puts the specification
#: ahead of the requirement expressly "so the shared prefix stays cacheable
#: across the fan-out", and its only caller never passed `spec` -- leaving
#: `SYSTEM` alone at ~471 tokens. Measured on a2-i2c: 12% cached over 315
#: calls, against 65-83% for every other fan-out.
CACHE_FLOOR_TOKENS = 1024

#: ~4 characters per token. Deliberately crude: this decides whether to WARN,
#: and a stage sitting near enough to the floor for the estimate to matter is
#: one worth looking at regardless.
_CHARS_PER_TOKEN = 4

#: Prefixes already warned about, by hash. One line per distinct shared block,
#: not one per item -- a 300-call fan-out would otherwise bury its own warning.
_warned: set[str] = set()


def _warn_if_under_floor(shared: str) -> None:
    """A shared block too short to cache is a silent 100% miss. Say so."""
    tokens = len(shared) // _CHARS_PER_TOKEN
    if tokens >= CACHE_FLOOR_TOKENS:
        return
    key = hashlib.sha256(shared.encode("utf-8")).hexdigest()[:16]
    if key in _warned:
        return
    _warned.add(key)
    logger.warning(
        "shared prompt prefix is ~%d tokens, under the %d-token cache floor: "
        "every call in this fan-out pays full price. Move per-design constants "
        "(the specification, the contract) into the shared block.",
        tokens, CACHE_FLOOR_TOKENS)


def shared_block(*sections: tuple[str, str]) -> str:
    """The cached head: `(tag, body)` pairs, then the sentinel.

    Nothing here may vary between the items of one stage.
    """
    parts = []
    for tag, body in sections:
        parts.append(f"<{tag}>\n{body.rstrip()}\n</{tag}>")
    return "\n\n".join(parts) + PREFIX_SENTINEL


def compose(
    shared: str,
    item: str,
    *,
    issues: list[Issue] | None = None,
    previous: str | None = None,
) -> str:
    """Assemble one item's prompt in the only order that preserves the cache."""
    _warn_if_under_floor(shared)
    parts = [shared, item]
    if previous:
        parts.append(previous_answer_block(previous))
    if issues:
        parts.append(gate_failures_block(issues))
    return "\n\n".join(parts)


def json_block(tag: str, value) -> str:
    """A tagged JSON block with **stable key order**.

    `sort_keys` is not cosmetic here. An unsorted dump can reorder between calls
    without changing a character of meaning, which breaks the shared prefix and
    costs the stage its cache -- silently, since the artifacts are identical.
    """
    return f"<{tag}>\n{json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True)}\n</{tag}>"
