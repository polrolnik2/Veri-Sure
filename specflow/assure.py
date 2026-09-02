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
from .schema import Issue, all_spans

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
        # Core FIRST, then context. `all_spans` is the provenance view: what
        # text this requirement rests on. It is never the deciding view -- what
        # a check must satisfy is `core_span` alone.
        req_spans = all_spans(req)
        if not req_spans:
            issues.append(
                Issue("error", f"requirement.{uid}.obligation",
                      "no obligation span quoted")
            )
            continue

        quoted: list[str] = []
        for i, sp in enumerate(req_spans):
            path = (f"requirement.{uid}.obligation" if i == 0
                    else f"requirement.{uid}.spec_spans[{i - 1}]")
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
            quoted.append(quote)

        # EVIDENCE INCLUDES SUPPORTING SPANS, deliberately. A linked unit can
        # legitimately supply the number a requirement restates -- the filter's
        # interval is stated one sentence away from the filter -- and this
        # module's stated bias is that "the conservative direction is one that
        # enlarges what counts as support", because a false positive here
        # BLOCKS the pipeline. The narrowing is on the other side: a supporting
        # span can only be a whole unit S1 already froze, so this cannot be
        # widened by quoting arbitrary text.
        issues.extend(_unsupported_quantities(
            uid, str(req.get("text") or ""), " \n".join(quoted), spec_text))

    issues.extend(_unattributed(spec_text, spans))
    return issues


#: Number words S1 and the specifications both use interchangeably with digits.
_WORD_NUMBERS = {
    "a": "1", "an": "1", "one": "1", "single": "1", "two": "2", "three": "3",
    "four": "4", "five": "5", "six": "6", "seven": "7", "eight": "8",
    "nine": "9", "ten": "10",
}

#: A quantity is a number AND a unit. The unit is what keeps this narrow: bare
#: numbers are everywhere in a hardware specification -- bit indices, register
#: addresses, state encodings -- and flagging them would make the check noise.
_UNITS = r"(?:clock\s+cycles?|clk\s+cycles?|cycles?|clocks?|bits?|ns|us|ms)"
_QUANTITY = re.compile(
    rf"\b(\d+|{'|'.join(_WORD_NUMBERS)})[\s-]+(?:`?clk`?[\s-]+)?({_UNITS})\b",
    re.I,
)


#: `clk_cnt[15:0]` states a width of 16 as plainly as the words do.
_BIT_RANGE = re.compile(r"\[\s*(\d+)\s*:\s*(\d+)\s*\]")


def _quantities(text: str, *, as_evidence: bool = False) -> set[tuple[str, str]]:
    """Numeric claims in `text`, as `(count, unit)` with words normalised.

    `one clock cycle`, `1 clk cycle` and `a single cycle` all reduce to
    `("1", "cycle")`, because a specification and a requirement written from it
    routinely differ in exactly that way and the difference is not a defect.

    `as_evidence` also reads bit ranges. A span quoting `clk_cnt[15:0]` states
    the width of `clk_cnt`, so a requirement calling it "the 16-bit clk_cnt" is
    attributed -- and without this the check reported two such requirements as
    unsupported, which is the false-positive class G1 cannot afford, since it
    blocks the pipeline. Only the EVIDENCE side reads ranges: the conservative
    direction is one that enlarges what counts as support.
    """
    found: set[tuple[str, str]] = set()
    for number, unit in _QUANTITY.findall(text):
        count = _WORD_NUMBERS.get(number.lower(), number)
        unit = re.sub(r"\s+", " ", unit.lower()).rstrip("s")
        unit = "cycle" if unit in ("clock cycle", "clk cycle", "clock") else unit
        found.add((count, unit))
    if as_evidence:
        for hi, lo in _BIT_RANGE.findall(text):
            found.add((str(abs(int(hi) - int(lo)) + 1), "bit"))
    return found


def _unsupported_quantities(
    uid: str, text: str, quoted: str, spec_text: str = "",
) -> list[Issue]:
    """A quantity the requirement asserts that its own cited spec text does not.

    Measured on `i2c_master_bit_ctrl`: SEVEN of 72 requirements assert that
    `cmd_ack` is one clock cycle wide, and each cites a span reading only
    "asserts `cmd_ack`" -- no duration at all. The count was carried over from a
    statement elsewhere in the document. REQ-0068, cited from a span that
    likewise says only "asserts `cmd_ack`", did NOT assert a duration -- so the
    same specification produced both readings, which is what a claim arriving
    from outside the evidence looks like. The rate is stable: 3-10% of
    requirements in every recorded run, and the flagged quantity is the same one
    every time.

    Attribution is the whole point of G1. A requirement asserting more than its
    span supports is unfalsifiable: nothing downstream can check the extra claim
    against the specification, and everything downstream treats a requirement as
    given -- so the number becomes an obligation the design is held to that no
    gate can question.

    **Severity is proportionate to which failure it is**, because the two are
    genuinely different. A quantity that appears NOWHERE in the specification
    was invented, and blocks. A quantity the specification states somewhere the
    requirement did not cite is an attribution gap: the evidence exists, it is
    simply not linked, and the fix is to add a span. That warns. Blocking the
    latter would stop a pipeline over a citation while the claim itself is sound
    -- and G1 blocks, so its false-positive cost is the whole run.
    """
    missing = _quantities(text) - _quantities(quoted, as_evidence=True)
    if not missing:
        return []
    elsewhere = _quantities(spec_text, as_evidence=True) if spec_text else set()
    issues: list[Issue] = []
    for quantity in sorted(missing):
        named = f"{quantity[0]} {quantity[1]}"
        if quantity in elsewhere:
            issues.append(Issue(
                "warning", f"requirement.{uid}.text",
                f"asserts {named}. The specification does state it, but not in "
                f"any span this requirement cites -- so the claim is not "
                f"attributable as written. Add the span that states it; a "
                f"requirement may cite several.",
                "unattributed",
            ))
        else:
            issues.append(Issue(
                "error", f"requirement.{uid}.text",
                f"asserts {named}, which appears NOWHERE in the specification. "
                f"A quantity with no source in the document cannot be checked "
                f"against it by anything downstream, and everything downstream "
                f"treats a requirement as given. Drop it, or record the "
                f"question in `underdetermined`.",
                "unattributed",
            ))
    return issues


def _collapse_ws(text: str) -> tuple[str, list[int]]:
    """Whitespace-collapsed projection of `text`, plus each kept char's offset.

    Returned offsets index back into the original, so a match found in the
    projection maps to a real span without re-searching.
    """
    out: list[str] = []
    index: list[int] = []
    prev_space = False
    for i, ch in enumerate(text):
        if ch.isspace():
            if prev_space or not out:
                continue
            out.append(" ")
            index.append(i)
            prev_space = True
        else:
            out.append(ch)
            index.append(i)
            prev_space = False
    return "".join(out), index


def _find_all(haystack: str, needle: str) -> list[int]:
    positions = []
    at = haystack.find(needle)
    while at != -1:
        positions.append(at)
        at = haystack.find(needle, at + 1)
    return positions


def _locate(spec_text: str, quote: str, hint: int) -> tuple[int, int] | None:
    """Find `quote` in the spec, preferring the occurrence nearest `hint`.

    The hint is the model's own offset. It is used only to disambiguate a quote
    that appears more than once -- never to reject one that is genuinely there.

    Matching ignores *runs* of whitespace, and that is a narrowing of the check
    to what it is actually for rather than a softening of it. The check exists to
    catch a fabricated quote -- prose the model invented and attributed to the
    spec -- and a whitespace-insensitive match still catches every one of those,
    because the words must still be the spec's words in the spec's order.

    What it stops rejecting is a faithful quote that differs in indentation. On
    `i2c_master_bit_ctrl` the model reproduced 14,842 characters of spec text and
    lost the entire span to two missing spaces of list indentation at offset
    2474; `difflib` put every one of those 14,842 characters in a matching block.
    The span was rejected, the coverage hole it filled reopened, and the node
    hard-failed after four rounds over whitespace. Attribution is a claim about
    which prose a requirement covers, not a transcription exercise.
    """
    if not quote:
        return None

    positions = _find_all(spec_text, quote)
    if positions:
        best = min(positions, key=lambda p: abs(p - hint))
        return (best, best + len(quote))

    flat_spec, index = _collapse_ws(spec_text)
    flat_quote, _ = _collapse_ws(quote)
    if not flat_quote:
        return None
    flat_positions = _find_all(flat_spec, flat_quote)
    if not flat_positions:
        return None

    # Compare in projection space, so the hint is meaningful either way.
    hint_flat = min(range(len(index)), key=lambda k: abs(index[k] - hint)) if index else 0
    best = min(flat_positions, key=lambda p: abs(p - hint_flat))
    start = index[best]
    end_idx = best + len(flat_quote) - 1
    end = index[end_idx] + 1 if end_idx < len(index) else len(spec_text)
    return (start, end)


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
