"""The deterministic gates. One engine, three links, four defect classes.

Nothing here calls a model. That is the point: an agent must never be the thing
that certifies its own output covered the spec, so every gate is pure code and
`assure.py` is the only module allowed to say a link is clean.

The four defects, and why each direction matters:

* **uncovered** -- a source item nothing covers. The load-bearing direction, and
  the one every surveyed system omits. GoGoTB anchors each coverage bin to a
  named specification behaviour, which is bin -> clause; nothing there checks
  clause -> bin, so its functional-coverage denominator is the model's own
  testpoint list and an omitted clause is invisible rather than penalised.
* **orphaned** -- a cover pointing at an item that does not exist.
* **unwanted** -- coverage of an item that never declared the need. This is the
  anti-padding guard: without it an agent raises its coverage percentage by
  inventing bins nobody asked for.
* **outdated** -- a cover pinned to a superseded revision. This is what makes
  "retract only with evidence" mechanically enforceable rather than a policy.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .ids import IdError, parse_ref
from .schema import Issue

# A gap in spec attribution shorter than this is noise (list punctuation, stray
# words). Tuned to be forgiving: G1 blocks the pipeline, so a false positive
# stalls a node over a bullet character.
_MIN_UNATTRIBUTED_CHARS = 24
_WORDISH_RE = re.compile(r"[A-Za-z0-9]")


@dataclass(frozen=True)
class SourceItem:
    """An artifact that declares what must cover it."""

    uid: str
    rev: int
    needs: tuple[str, ...]


@dataclass(frozen=True)
class TargetItem:
    """An artifact that claims to cover source items."""

    uid: str
    covers: tuple[str, ...]  # raw reference strings, e.g. "REQ-0007@1"


def check_link(
    sources: list[SourceItem],
    targets: list[TargetItem],
    *,
    need_kind: str,
    source_label: str,
    target_label: str,
) -> list[Issue]:
    """Verify one link of the chain. Generic over all three."""
    issues: list[Issue] = []
    by_uid = {s.uid: s for s in sources}

    if len(by_uid) != len(sources):
        seen: set[str] = set()
        for s in sources:
            if s.uid in seen:
                issues.append(
                    Issue("error", f"{source_label}.{s.uid}", "duplicate uid")
                )
            seen.add(s.uid)

    covered: set[str] = set()

    for t in targets:
        if not t.covers:
            issues.append(
                Issue(
                    "error",
                    f"{target_label}.{t.uid}.covers",
                    f"covers nothing; every {target_label} must name a {source_label}",
                    "orphaned",
                )
            )
            continue

        for raw in t.covers:
            try:
                ref = parse_ref(raw)
            except IdError:
                issues.append(
                    Issue(
                        "error",
                        f"{target_label}.{t.uid}.covers",
                        f"malformed reference {raw!r}",
                        "orphaned",
                    )
                )
                continue

            src = by_uid.get(ref.uid)
            if src is None:
                issues.append(
                    Issue(
                        "error",
                        f"{target_label}.{t.uid}.covers",
                        f"references {ref.uid}, which is not a known {source_label}",
                        "orphaned",
                    )
                )
                continue

            if need_kind not in src.needs:
                issues.append(
                    Issue(
                        "error",
                        f"{target_label}.{t.uid}.covers",
                        f"{ref.uid} does not declare needs={need_kind!r}; "
                        f"coverage was not requested",
                        "unwanted",
                    )
                )
                # Still counts as covering it -- the defect is the unrequested
                # coverage, and also reporting `uncovered` would be noise.
                covered.add(ref.uid)
                continue

            if ref.rev is None:
                issues.append(
                    Issue(
                        "warning",
                        f"{target_label}.{t.uid}.covers",
                        f"{ref.uid} referenced without a revision; pin it as "
                        f"{ref.uid}@{src.rev}",
                        "outdated",
                    )
                )
            elif ref.rev != src.rev:
                direction = "superseded" if ref.rev < src.rev else "ahead of"
                issues.append(
                    Issue(
                        "error",
                        f"{target_label}.{t.uid}.covers",
                        f"pinned to {ref.uid}@{ref.rev}, which is {direction} the "
                        f"current revision {src.rev}",
                        "outdated",
                    )
                )

            covered.add(ref.uid)

    for s in sources:
        if need_kind in s.needs and s.uid not in covered:
            issues.append(
                Issue(
                    "error",
                    f"{source_label}.{s.uid}",
                    f"no {target_label} covers it, but it declares needs={need_kind!r}",
                    "uncovered",
                )
            )

    return issues


def check_spec_attribution(spec_text: str, requirements: list[dict]) -> list[Issue]:
    """G1: every requirement quotes the spec verbatim, and no meaningful span of
    spec text goes unclaimed.

    This is the only defence against wholesale omission at the top of the chain.
    Everything downstream measures coverage of the *requirements*; if a spec
    clause never became a requirement, no later gate can notice.
    """
    issues: list[Issue] = []
    spans: list[tuple[int, int]] = []

    for req in requirements:
        uid = req.get("uid", "<no-uid>")
        req_spans = req.get("spec_spans") or []
        if not req_spans:
            issues.append(
                Issue("error", f"requirement.{uid}.spec_spans", "no spec span quoted")
            )
            continue

        for i, sp in enumerate(req_spans):
            path = f"requirement.{uid}.spec_spans[{i}]"
            try:
                # `end` is deliberately unread: the quote's own length
                # defines the span once it is located, so a model that
                # miscounts its end offset is no longer penalised for it.
                start, quote = int(sp["start"]), str(sp["quote"])
            except Exception:  # noqa: BLE001
                issues.append(Issue("error", path, "malformed span"))
                continue

            # The offsets are a HINT, not the check. Requiring the model to
            # compute exact character positions failed 31 times out of 31 on a
            # 14.3KB spec while 30 of those quotes were verbatim and locatable
            # by search -- so the arithmetic rejected good attribution and told
            # the model nothing about what was actually wrong. Worse, it made
            # vacuity cheap: quoting one character satisfies "matches at that
            # range" trivially, and across four repair rounds the model moved
            # from 130-character clauses to 1-character ones because that
            # scored better.
            located = _locate(spec_text, quote, start)
            if located is None:
                issues.append(
                    Issue("error", path, "quote is not verbatim spec text")
                )
                continue

            spans.append(located)

    issues.extend(_unattributed(spec_text, spans))
    return issues


def _locate(spec_text: str, quote: str, hint: int) -> tuple[int, int] | None:
    """Find `quote` in the spec, preferring the occurrence nearest `hint`.

    The hint is the model's own offset. It is used only to disambiguate a quote
    that appears more than once -- never to reject one that is genuinely there.
    """
    if not quote:
        return None
    positions = []
    at = spec_text.find(quote)
    while at != -1:
        positions.append(at)
        at = spec_text.find(quote, at + 1)
    if not positions:
        return None
    best = min(positions, key=lambda p: abs(p - hint))
    return (best, best + len(quote))


def _unattributed(spec_text: str, spans: list[tuple[int, int]]) -> list[Issue]:
    """Report meaningful spec text no requirement claimed."""
    merged: list[list[int]] = []
    for start, end in sorted(spans):
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])

    issues: list[Issue] = []
    cursor = 0
    for start, end in merged + [[len(spec_text), len(spec_text)]]:
        if start > cursor:
            gap = spec_text[cursor:start]
            if len(_WORDISH_RE.findall(gap)) >= _MIN_UNATTRIBUTED_CHARS:
                preview = " ".join(gap.split())[:120]
                issues.append(
                    Issue(
                        "error",
                        f"spec[{cursor}:{start}]",
                        f"no requirement claims this text: {preview!r}",
                        "uncovered",
                    )
                )
        cursor = max(cursor, end)

    return issues


# --- thin adapters, one per link -------------------------------------------


def _sources(items: list[dict]) -> list[SourceItem]:
    return [
        SourceItem(
            uid=i.get("uid", ""),
            rev=int(i.get("rev", 1)),
            needs=tuple(i.get("needs") or ()),
        )
        for i in items
    ]


def _targets(items: list[dict]) -> list[TargetItem]:
    return [
        TargetItem(uid=i.get("uid", ""), covers=tuple(i.get("covers") or ()))
        for i in items
    ]


def assure_requirements_to_testplan(reqs: list[dict], tps: list[dict]) -> list[Issue]:
    """G2."""
    return check_link(
        _sources(reqs),
        _targets(tps),
        need_kind="testplan",
        source_label="requirement",
        target_label="testplan",
    )


def assure_testplan_to_bins(tps: list[dict], bins: list[dict]) -> list[Issue]:
    """G3, coverage half."""
    return check_link(
        _sources(tps),
        _targets(bins),
        need_kind="bin",
        source_label="testplan",
        target_label="bin",
    )


def assure_testplan_to_checks(tps: list[dict], checks: list[dict]) -> list[Issue]:
    """G3, check half. A testplan element with a bin but no check is coverable
    and unverifiable -- reached, and proves nothing."""
    return check_link(
        _sources(tps),
        _targets(checks),
        need_kind="check",
        source_label="testplan",
        target_label="check",
    )


def assure_requirements_to_refmodel(reqs: list[dict], fragments: list[dict]) -> list[Issue]:
    """G4's traceability half: every requirement has a generated fragment."""
    return check_link(
        _sources(reqs),
        _targets(fragments),
        need_kind="refmodel",
        source_label="requirement",
        target_label="fragment",
    )
