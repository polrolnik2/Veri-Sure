"""D1: divide the specification at boundaries its author already chose.

The decomposition this replaces was **generative** -- the model read the spec and
invented requirements, choosing its own granularity -- and on every real spec run
so far that granularity collapsed the same way:

    i2c_master_bit_ctrl   24 requirements, one claiming 15,709 of 15,714 chars
    or1200_ctrl           31 requirements, one claiming the whole spec

One catch-all blankets the specification and satisfies the coverage gate on its
own. That is the cheapest correct answer to "is any spec text unclaimed?", so it
is the answer the incentive produces. Two attempts to forbid it by threshold were
tried and reverted: a 24-character span minimum rejected the half adder's
legitimate ``' - output cout'``, and a distinct-span ban rejected one sentence
legitimately constraining two ports. No threshold separates a large honest
requirement from a large evasive one.

Division removes the choice instead of penalising it. The partition is built by
this module, so granularity stops being the model's to pick, and spans become
*offsets* rather than transcriptions -- which also retires the failure that hard
-failed a node earlier: a faithful 14,842-character quote rejected over two
missing spaces of list indentation.

**Where this module stops, and why.** It cuts at blank lines, list items,
headings, table rows and SENTENCE ENDS -- boundaries a human put there
deliberately, plus the end of one of their sentences -- and never inside a
sentence, which `splits_a_sentence` asserts over both corpora.

The sentence was not always the floor, and the argument against it was real.
Measured on the two specs above, of the sentences that follow another sentence
inside one paragraph:

    i2c_master_bit_ctrl   42 of 147   28%   open with a back-reference
    or1200_ctrl           20 of 132   15%

"A filtered STOP during any active non-STOP command **also** asserts al" is not
a standalone requirement; "also" points at the sentence a sentence-splitter just
cut it away from. **That argument is about a script**, and the classifier reading
these units is not one: it holds the whole specification in a cached prefix, it
is told to resolve the reference in its restatement, and `continues_previous`
chains a unit onto the one before it.

What moved the floor down was the other side of the ledger. The classifier could
subdivide a unit and attribute a requirement to the piece, and on c1-i2c it did:
121 of 127 spans were narrower than a unit, 41 began mid-sentence, and REQ-0002
through REQ-0010 were one feature-list sentence cut at its commas into nine noun
phrases. The last of them, `" and glitch filtering."`, became a requirement
asserting a three-sample filter window that those 22 characters do not mention.
A back-reference the classifier can resolve is a smaller cost than a span that
states nothing, so the floor is the sentence and the classifier no longer
subdivides: `s1_classify.to_requirements` records the WHOLE UNIT as a
requirement's span.

The result is a floor, not a partition: the classifier may read one unit as
several obligations and may chain adjacent units, but every requirement it
produces is attributed to a whole unit, and it cannot merge distant units into
one span. The catch-all becomes unavailable rather than discouraged.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .s1_requirements import normalize_spec

#: A markdown-ish list item: bullet or numbered, at any indentation.
_LIST_ITEM = re.compile(r"^[ \t]*(?:[-*+•]|\(?\d+[.)]|[a-z][.)])\s+\S")
#: A setext or ATX heading, or a bare line that is clearly a section title.
_HEADING = re.compile(r"^[ \t]*(?:#{1,6}\s+\S|=+\s*$|-{3,}\s*$)")
#: A pipe table row.
_TABLE_ROW = re.compile(r"^[ \t]*\|.*\|[ \t]*$")
#: A fenced code block delimiter.
_FENCE = re.compile(r"^[ \t]*(?:```|~~~)")


@dataclass(frozen=True)
class Unit:
    """One authorial unit: a span of the normalised spec, and what shape it is.

    `kind` is descriptive, not a verdict. Deciding whether a unit states
    behaviour is the classifier's job; this module only reports the shape of the
    text, which is a fact about the document rather than a judgement about it.
    """

    start: int
    end: int
    kind: str  # "paragraph" | "list_item" | "heading" | "table_row" | "code"

    @property
    def length(self) -> int:
        return self.end - self.start

    def text(self, spec: str) -> str:
        """This unit's text. `spec` may be raw or normalised; offsets always
        index the normalised form, so it is normalised here rather than trusted.

        Taking the caller's word for it was a silent-corruption bug: a raw
        VerilogEval prompt begins with a blank line, so every offset came back
        shifted by one and the returned text was quietly wrong rather than
        obviously wrong."""
        return normalize_spec(spec)[self.start:self.end]


def _line_kind(line: str) -> str:
    if _HEADING.match(line):
        return "heading"
    if _TABLE_ROW.match(line):
        return "table_row"
    if _LIST_ITEM.match(line):
        return "list_item"
    return "paragraph"



#: Shapes a sentence cut applies to. A heading is not prose, a table row's
#: periods are not sentence ends, and code is not English -- splitting any of
#: them at `.` produces fragments no reader would recognise as units.
_PROSE_KINDS = ("paragraph", "list_item")

#: A sentence terminator followed by whitespace and a capital or a digit, OR by
#: a line break. The first lookahead is what keeps "clk_cnt >> 2. Whenever"
#: apart from "i.e. when" and from a decimal point: an abbreviation is followed
#: by a lower-case word, and `2.5` has no space.
#:
#: The line-break alternative is there because a specification's own names are
#: lower case. On i2c the port glossary reads
#:
#:     scl_i:External I2C SCL line input ... and read sampling.
#:     sda_i:External I2C SDA line input ...
#:
#: and the capital-letter lookahead refuses the boundary before `sda_i`, so one
#: unit ran from the middle of the SCL entry into the SDA entry -- and the seven
#: requirements built on it were attributed to a quote mixing SCL behaviour with
#: an SDA declaration, which is the provenance defect this module exists to
#: prevent. A sentence end followed by a NEWLINE is unambiguous in a way a
#: mid-line one is not: no abbreviation is broken across a line here, and a
#: stray short fragment is joined backwards by `min_words` regardless.
#:
#: Measured before landing: purely additive on i2c (168 -> 172 units, every
#: existing unit start unchanged) and zero splits, overlaps or word-carrying
#: gaps across all 273 specs in both corpora.
_SENTENCE_CUT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9`])|(?<=[.!?])\n(?=[ \t]*\S)")


def _by_sentence(text: str, units: list[Unit], min_words: int) -> list[Unit]:
    """Cut prose units at sentence ends, so a SENTENCE is the floor.

    The module's original argument against this was that 28% of sentences
    following another inside one paragraph open with a back-reference, and a
    SCRIPT cutting there severs the referent. That argument is about a script.
    The classifier reading these units has the whole specification in its cached
    prefix and `continues_previous` to chain a unit onto the one before it --
    which the same docstring already calls "what makes splitting below the
    paragraph safe here".

    What it buys is the invariant the floor was for. With the sentence as the
    unit, an obligation that is a whole unit can no longer be a fragment of one:
    measured on c1-i2c, S1 cut one feature-list sentence into nine noun phrases
    -- "single-bit READ cycles, ", " and glitch filtering." -- and the last of
    them became a requirement asserting a mechanism its span did not contain.

    `min_words` joins backwards exactly as `divide` does, so "i.e." and a short
    trailing clause do not become units of their own.
    """
    out: list[Unit] = []
    for u in units:
        if u.kind not in _PROSE_KINDS:
            out.append(u)
            continue
        body = text[u.start:u.end]
        cuts = [u.start + m.start() for m in _SENTENCE_CUT.finditer(body)]
        if not cuts:
            out.append(u)
            continue
        bounds = [u.start, *cuts, u.end]
        pieces: list[Unit] = []
        for a, b in zip(bounds, bounds[1:]):
            seg = text[a:b]
            if not seg.strip():
                continue
            ws = seg[:len(seg) - len(seg.lstrip())]
            if a == u.start:
                # The parent's own boundary was set by the pass that made it and
                # is authoritative -- an indented list item starts AT its indent,
                # immediately after the newline, and moving past the indent is
                # what `splits_a_sentence` reads as a cut inside a line.
                start = a
            elif "\n" in ws:
                start = a + ws.rindex("\n") + 1
            else:
                start = a + len(ws)
            piece = Unit(start, a + len(seg.rstrip()), u.kind)
            # Too short to stand alone: join it BACKWARDS, the same direction
            # and for the same reason `divide` joins a stray "Note:".
            if pieces and len(seg.split()) < min_words:
                pieces[-1] = Unit(pieces[-1].start, piece.end, pieces[-1].kind)
            else:
                pieces.append(piece)
        out.extend(pieces or [u])
    return out


def divide(spec: str, *, min_words: int = 3) -> list[Unit]:
    """Split `spec` into authorial units, in document order.

    Units are non-overlapping and ordered, and every unit's span is a slice of
    `normalize_spec(spec)` -- the same normalisation the prompt and the gate use,
    so an offset means one thing everywhere. Whitespace between units belongs to
    no unit, which is why the returned spans do not tile the text exactly; that
    residue is reported by `coverage`, never silently ignored.

    `min_words` joins a fragment too short to stand alone to the unit before it,
    so a stray "Note:" or a wrapped table caption does not become a unit of its
    own. It joins backwards rather than forwards because a fragment far more
    often trails the thing it belongs to than precedes it.
    """
    text = normalize_spec(spec)
    if not text:
        return []

    units: list[Unit] = []
    in_fence = False
    fence_start: int | None = None

    # Group consecutive lines of the same shape into one unit, breaking on a
    # blank line, on a change of shape, and always between two list items.
    cur_start: int | None = None
    cur_kind = ""
    cur_end = 0

    def flush() -> None:
        nonlocal cur_start, cur_kind, cur_end
        if cur_start is None:
            return
        body = text[cur_start:cur_end]
        if body.strip():
            units.append(Unit(cur_start, cur_start + len(body.rstrip()), cur_kind))
        cur_start, cur_kind, cur_end = None, "", 0

    for m in re.finditer(r"[^\n]*(?:\n|$)", text):
        line = m.group(0)
        if not line:
            break
        stripped = line.strip()
        start, end = m.start(), m.end()

        if _FENCE.match(line):
            if in_fence:
                units.append(Unit(fence_start or start, end - 1, "code"))
                in_fence, fence_start = False, None
            else:
                flush()
                in_fence, fence_start = True, start
            continue
        if in_fence:
            continue

        if not stripped:                       # blank line: an explicit break
            flush()
            continue

        kind = _line_kind(line)
        # A list item, a heading and a table row each begin a new unit; prose
        # continues the paragraph it is in. A prose line directly under a list
        # item is that item's continuation, which is why it does not flush.
        if kind in ("list_item", "heading", "table_row") or kind != cur_kind:
            if not (kind == "paragraph" and cur_kind == "list_item"):
                flush()
        if cur_start is None:
            cur_start, cur_kind = start, kind
        cur_end = end

    flush()
    if in_fence and fence_start is not None:   # unterminated fence
        units.append(Unit(fence_start, len(text), "code"))

    units = [u for parent in units for u in _split_indented_list(text, parent)]
    # THE SENTENCE IS THE FLOOR. Last, so it cuts what the shape passes above it
    # have already settled -- and after `_split_indented_list`, whose own guard
    # is that a line only begins a unit when the line before ends a sentence.
    units = _by_sentence(text, units, min_words)
    return _join_fragments(text, units, min_words)


def _split_indented_list(text: str, unit: Unit) -> list[Unit]:
    """Split a block that is a list written without list markers.

    Specifications write definition lists two ways, and only one of them carries
    a bullet. `fpu_addsub_pipeline` writes the other:

        Internal reg/wire signals:
            reg [1:0] rm_1: Stage-1 pipeline copy of the rounding mode.
            reg [1:0] rm_2: Stage-2 pipeline copy of the rounding mode.
            ... 215 lines of it

    Grouped as prose that is one 11,968-character unit -- the largest in the
    whole ChipVerilog corpus, and plainly 215 authorial units rather than one.
    The indentation and the one-item-per-line layout are the author's list
    markup; they just are not bullets.

    The split is safe by this module's own rule and is guarded to stay that way:
    a line only begins a new unit when the line before it **ends a sentence**, so
    no boundary can land mid-sentence. Indentation relative to the block's first
    line is what distinguishes this from ordinary wrapped prose, whose
    continuation lines are neither indented nor sentence-terminated.
    """
    body = text[unit.start:unit.end]        # `text` is already normalised here
    lines = body.splitlines(keepends=True)
    if unit.kind != "paragraph" or len(lines) < 4:
        return [unit]

    head_indent = len(lines[0]) - len(lines[0].lstrip())
    indented = [
        i for i, ln in enumerate(lines[1:], 1)
        if ln.strip() and (len(ln) - len(ln.lstrip())) > head_indent
    ]
    # Require the block to be predominantly an indented run, not a paragraph
    # with one indented afterthought.
    if len(indented) < 3 or len(indented) < 0.6 * (len(lines) - 1):
        return [unit]

    out: list[Unit] = []
    start = unit.start
    offset = unit.start
    for i, ln in enumerate(lines):
        offset_end = offset + len(ln)
        nxt = lines[i + 1] if i + 1 < len(lines) else None
        breaks = (
            nxt is not None
            and _SENTENCE_END.search(ln.rstrip())
            and (len(nxt) - len(nxt.lstrip())) > head_indent
            and nxt.strip()
        )
        if breaks:
            end = offset + len(ln.rstrip())
            if text[start:end].strip():
                out.append(Unit(start, end, "list_item"))
            start = offset_end
        offset = offset_end
    if text[start:unit.end].strip():
        out.append(Unit(start, unit.end, "list_item" if out else unit.kind))
    return out or [unit]


def _join_fragments(text: str, units: list[Unit], min_words: int) -> list[Unit]:
    """Absorb prose fragments too short to stand alone into their predecessor.

    **Only prose.** A list item is an authorial unit whatever its length -- the
    author drew that boundary deliberately, and `- START` being two words is not
    evidence they did not mean it. Joining short list items merged `- START` and
    `- STOP` into one unit, erasing a boundary this module exists to preserve.
    """
    out: list[Unit] = []
    for u in units:
        body = text[u.start:u.end]
        joinable = (
            out
            and u.kind == "paragraph"
            and out[-1].kind == "paragraph"
            and len(body.split()) < min_words
        )
        if joinable:
            prev = out[-1]
            out[-1] = Unit(prev.start, u.end, prev.kind)
        else:
            out.append(u)
    return out


# ------------------------------------------------------------------ reporting


_SENTENCE_END = re.compile(r"[.!?;:]\s*$")


def splits_a_sentence(spec: str, units: list[Unit]) -> list[Unit]:
    """Units that begin mid-sentence -- the property this module must never have.

    A boundary is sound if the text before it ends a sentence, ends a line, or is
    the start of the document. Anything else means the divider cut inside a
    sentence, which is exactly the 15-28% failure that sentence-splitting has and
    this module exists to avoid.
    """
    text = normalize_spec(spec)
    bad: list[Unit] = []
    for u in units:
        before = text[:u.start].rstrip()
        if not before:
            continue
        if before.endswith("\n") or text[u.start - 1: u.start] == "\n":
            continue
        if _SENTENCE_END.search(before):
            continue
        bad.append(u)
    return bad


def coverage(spec: str, units: list[Unit]) -> tuple[int, int, list[tuple[int, int]]]:
    """(covered chars, total chars, gaps carrying words).

    Reported, never claimed. Whitespace between units is expected residue; a gap
    containing actual words is a defect in the divider and must be visible rather
    than rounded away.
    """
    text = normalize_spec(spec)
    covered = sum(u.length for u in units)
    gaps: list[tuple[int, int]] = []
    cursor = 0
    for u in sorted(units, key=lambda x: x.start):
        if u.start > cursor and text[cursor:u.start].strip():
            gaps.append((cursor, u.start))
        cursor = max(cursor, u.end)
    if cursor < len(text) and text[cursor:].strip():
        gaps.append((cursor, len(text)))
    return covered, len(text), gaps


def overlaps(units: list[Unit]) -> list[tuple[Unit, Unit]]:
    """Pairs of units whose spans intersect. Must always be empty."""
    out: list[tuple[Unit, Unit]] = []
    ordered = sorted(units, key=lambda u: u.start)
    for a, b in zip(ordered, ordered[1:]):
        if b.start < a.end:
            out.append((a, b))
    return out
