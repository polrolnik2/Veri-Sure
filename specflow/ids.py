"""UID minting and revisioned reference parsing.

A UID is `<PREFIX>-<NNNN>`; a *reference* to one is `<PREFIX>-<NNNN>@<rev>`.

The revision in the reference is the whole point. A check that covers
`REQ-0007@1` is still pinned to revision 1 after the requirement is amended to
revision 2, so `assure.py` can report it `outdated` instead of silently keeping
a cover whose meaning changed underneath it. Without the revision, retraction is
a convention nobody can enforce; with it, retraction is a diff.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Artifact prefixes. Kept short because they appear in generated method names
# (`_req_0007`) and in rendered test module names (`test_TP0007.py`).
PREFIX_REQUIREMENT = "REQ"
PREFIX_TESTPLAN = "TP"
PREFIX_BIN = "BIN"
PREFIX_CHECK = "CHK"
PREFIX_TESTCASE = "TC"

_UID_RE = re.compile(r"^(?P<prefix>[A-Z]{2,4})-(?P<num>\d{4,})$")
_REF_RE = re.compile(r"^(?P<uid>[A-Z]{2,4}-\d{4,})(?:@(?P<rev>\d+))?$")


class IdError(ValueError):
    """Malformed UID or reference."""


@dataclass(frozen=True)
class Ref:
    """A pinned reference to a versioned artifact."""

    uid: str
    rev: int | None = None  # None means "any revision" -- only valid in fixtures

    def __str__(self) -> str:
        return self.uid if self.rev is None else f"{self.uid}@{self.rev}"


def mint(prefix: str, n: int) -> str:
    """`mint("REQ", 7) -> "REQ-0007"`. Zero-padded so UIDs sort lexically."""
    if not prefix.isupper() or not (2 <= len(prefix) <= 4):
        raise IdError(f"bad prefix {prefix!r}")
    if n < 0:
        raise IdError(f"negative index {n}")
    return f"{prefix}-{n:04d}"


def is_uid(text: str) -> bool:
    return bool(_UID_RE.match(text or ""))


def prefix_of(uid: str) -> str:
    m = _UID_RE.match(uid or "")
    if not m:
        raise IdError(f"not a uid: {uid!r}")
    return m.group("prefix")


def parse_ref(text: str) -> Ref:
    """`"REQ-0007@2" -> Ref("REQ-0007", 2)`; `"REQ-0007" -> Ref("REQ-0007", None)`."""
    m = _REF_RE.match((text or "").strip())
    if not m:
        raise IdError(f"not a reference: {text!r}")
    rev = m.group("rev")
    return Ref(uid=m.group("uid"), rev=int(rev) if rev is not None else None)


def next_index(existing: list[str], prefix: str) -> int:
    """Lowest free index for `prefix` given the UIDs already minted.

    Deliberately max+1 rather than filling holes: a retired UID must never be
    reused, or an old reference silently re-resolves to a different artifact.
    """
    best = -1
    for uid in existing:
        m = _UID_RE.match(uid or "")
        if m and m.group("prefix") == prefix:
            best = max(best, int(m.group("num")))
    return best + 1


def method_name(req_uid: str) -> str:
    """`REQ-0007 -> _req_0007`, the reference-model fragment name.

    Mechanical both ways, so `validate.py` can check every requirement has a
    fragment by walking the AST for these names.
    """
    m = _UID_RE.match(req_uid or "")
    if not m:
        raise IdError(f"not a uid: {req_uid!r}")
    return f"_{m.group('prefix').lower()}_{m.group('num')}"
