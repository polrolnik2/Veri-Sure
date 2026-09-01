"""D1: division at authorial boundaries.

Two invariants carry the whole design and are asserted over both real corpora,
not just fixtures:

* **no boundary lands inside a sentence** -- the reason this module exists;
* **units never overlap and no gap carries a word** -- nothing is lost or
  double-claimed, so the partition can replace the coverage gate.

The fixtures below pin the shapes that were got wrong on the way here.
"""

from __future__ import annotations

import pathlib

import pytest

from specflow.divide import Unit, coverage, divide, overlaps, splits_a_sentence

REPO = pathlib.Path(__file__).resolve().parents[1]
VERILOGEVAL = sorted(
    (REPO / "benchmarks" / "verilogeval-v2-ext" / "dataset_spec-to-rtl").glob(
        "Prob*_prompt.txt"
    )
)
CHIPVERILOG = sorted((REPO / "benchmarks" / "chipverilog" / "Des").rglob("description.txt"))


# ------------------------------------------------------------------ fixtures


def test_a_paragraph_splits_at_its_sentence_ends():
    """The floor is the SENTENCE, not the paragraph.

    The paragraph was the floor until an S1 span of `" and glitch filtering."`
    -- 22 characters of a feature list, naming a mechanism and stating no
    behaviour -- became a requirement about a three-sample filter window. With
    the sentence as the unit and a requirement's span the whole unit, that
    fragment cannot be a span, because it is not a unit.
    """
    spec = "The counter counts up. On overflow it saturates rather than wrapping."
    units = divide(spec)
    assert [u.text(spec) for u in units] == [
        "The counter counts up.",
        "On overflow it saturates rather than wrapping.",
    ]
    assert not splits_a_sentence(spec, units)


def test_a_sentence_end_that_is_not_one_does_not_cut():
    """Abbreviations and decimals are why the cut needs a lookahead.

    `i.e.` is followed by a lower-case word and `2.5` by a digit with no space,
    so neither can be mistaken for the end of a sentence.
    """
    spec = "The divider samples at clk_cnt >> 2, i.e. every 2.5 us, and holds."
    assert len(divide(spec)) == 1


def test_a_blank_line_separates_units():
    spec = "The counter counts up.\n\nOn overflow it saturates."
    units = divide(spec)
    assert [u.text(spec) for u in units] == [
        "The counter counts up.",
        "On overflow it saturates.",
    ]


def test_each_list_item_is_its_own_unit():
    spec = "The FSM accepts:\n  - START\n  - STOP\n  - a WRITE of one bit\n"
    kinds = [u.kind for u in divide(spec)]
    assert kinds.count("list_item") == 3


def test_prose_under_a_list_item_continues_it():
    """A wrapped list item is one item, not an item plus a stray paragraph."""
    spec = "  - a WRITE cycle drives SDA according to din and then\n    releases SCL until the bus reads high\n"
    units = divide(spec)
    assert len(units) == 1
    assert "releases SCL" in units[0].text(spec)


def test_an_indented_definition_list_splits_per_line():
    """`fpu_addsub_pipeline` writes a 215-line list with no bullet markers.

    Grouped as prose it was one 11,968-character unit -- the largest in the whole
    ChipVerilog corpus and plainly 215 authorial units. Indentation plus
    one-item-per-line is the author's list markup; it just is not a bullet.
    """
    spec = (
        "Internal reg/wire signals:\n"
        "    reg [1:0] rm_1: Stage-1 copy of the rounding mode.\n"
        "    reg [1:0] rm_2: Stage-2 copy of the rounding mode.\n"
        "    reg [1:0] rm_3: Stage-3 copy of the rounding mode.\n"
        "    reg [1:0] rm_4: Stage-4 copy of the rounding mode.\n"
    )
    units = divide(spec)
    assert len(units) == 5, [u.text(spec) for u in units]
    assert not splits_a_sentence(spec, units)


def test_an_ordinary_paragraph_with_one_indented_line_is_not_a_list():
    """The guard on the rule above: a paragraph with an afterthought is prose.

    The sentence pass cuts it in two, which is the floor doing its job; what
    this pins is that neither piece is a `list_item`, because the indented line
    is an afterthought and not the author's list markup.
    """
    spec = (
        "The controller synchronises both bus inputs through two capture stages.\n"
        "    This is required for metastability.\n"
    )
    units = divide(spec)
    assert [u.kind for u in units] == ["paragraph", "paragraph"]


def test_a_fenced_code_block_is_one_unit():
    spec = "Given:\n\n```\nalways @(posedge clk)\n  q <= d;\n```\n\nThen q follows d.\n"
    kinds = [u.kind for u in divide(spec)]
    assert "code" in kinds
    code = next(u for u in divide(spec) if u.kind == "code")
    assert "q <= d;" in code.text(spec)


def test_a_short_fragment_joins_its_predecessor():
    spec = "The output saturates on overflow.\n\nNote:\n"
    units = divide(spec)
    assert len(units) == 1


def test_a_sentence_cut_keeps_the_line_indent_it_starts_on():
    """The pin on the sentence pass's own boundary arithmetic.

    A piece that begins on a fresh line must start immediately after the
    newline, indent included, exactly as `_split_indented_list` sets its units.
    Stripping the indent moves the boundary into the middle of a line, which is
    precisely what `splits_a_sentence` exists to reject -- and it did, twice, on
    the i2c spec before this was fixed.
    """
    spec = (
        "    scl_oen: Active-low SCL output enable.\n"
        "        - `0`: drive SCL low\n"
        "        - `1`: release SCL so the pull-up drives it high\n"
        "    output sda_o: Constant-low SDA drive value.\n"
    )
    units = divide(spec)
    assert not splits_a_sentence(spec, units), [u.text(spec) for u in units]


def test_the_split_i2c_filter_sentence_is_now_one_unit():
    """The measured defect this change exists to close.

    On c1-i2c, `divide` put boundaries at 6812 and 7192, and S1 cut inside them
    at 7072 -- mid-clause. REQ-0045 got "...are generated using a majority
    function" and REQ-0046 got "over the three-sample histories.", so neither
    span states the requirement and the pipeline authored checks from both. The
    sentence is one unit now, and no unit boundary falls at 7072.
    """
    path = REPO / "benchmarks/chipverilog/Des/i2c/i2c_master_bit_ctrl/description.txt"
    spec = path.read_text(encoding="utf-8")
    units = divide(spec)
    holding = [u for u in units if u.start <= 7072 < u.end]
    assert len(holding) == 1
    assert holding[0].text(spec) == (
        "The filtered outputs `sSCL` and `sSDA` are generated using a majority "
        "function over the three-sample histories."
    )


def test_offsets_index_the_normalised_spec():
    """Offsets must mean one thing everywhere; `normalize_spec` is that thing."""
    from specflow.s1_requirements import normalize_spec

    spec = "\r\n\r\n  The counter counts up.\n\nIt saturates.\n\n\n"
    text = normalize_spec(spec)
    for u in divide(spec):
        assert text[u.start:u.end] == u.text(spec)
        assert u.text(spec).strip() == u.text(spec)


# ------------------------------------------------------ invariants, both corpora


@pytest.mark.parametrize(
    "paths, label",
    [(VERILOGEVAL, "verilogeval"), (CHIPVERILOG, "chipverilog")],
    ids=["verilogeval", "chipverilog"],
)
def test_no_boundary_falls_inside_a_sentence(paths, label):
    """The property the whole design rests on.

    Sentence-level splitting reaches a similar granularity but severs meaning:
    measured on the two specs we have run, 28% and 15% of within-paragraph
    sentences open with a back-reference. Cutting only where the author cut
    cannot do that, and this asserts it over every spec in both corpora.
    """
    assert paths, f"{label} corpus not found"
    offenders = []
    for p in paths:
        spec = p.read_text(encoding="utf-8", errors="replace")
        bad = splits_a_sentence(spec, divide(spec))
        if bad:
            offenders.append((p.name, [u.text(spec)[:60] for u in bad[:2]]))
    assert not offenders, offenders[:3]


@pytest.mark.parametrize(
    "paths, label",
    [(VERILOGEVAL, "verilogeval"), (CHIPVERILOG, "chipverilog")],
    ids=["verilogeval", "chipverilog"],
)
def test_units_tile_without_overlap_and_lose_no_words(paths, label):
    assert paths, f"{label} corpus not found"
    bad_overlap, bad_gap = [], []
    for p in paths:
        spec = p.read_text(encoding="utf-8", errors="replace")
        units = divide(spec)
        if overlaps(units):
            bad_overlap.append(p.name)
        _, _, gaps = coverage(spec, units)
        if gaps:
            bad_gap.append((p.name, gaps[:2]))
    assert not bad_overlap, bad_overlap[:5]
    assert not bad_gap, bad_gap[:3]


def test_no_spec_collapses_to_a_single_unit():
    """The failure this replaces: one requirement claiming 100% of the spec.

    A multi-paragraph spec reduced to one unit would let the catch-all back in
    through the divider rather than through the model.

    Deliberately *not* asserted as a fraction of the spec. `WB_stage` has one
    genuine 2,745-character prose block out of 4,680 total -- 59% -- and that is
    the author's paragraph, not a defect. A ratio rule here would be the same
    mistake as the reverted `MIN_SPAN_CHARS`: a threshold standing in for a
    property. The property is that authorial boundaries are honoured, and the
    classifier splits within a unit afterwards.
    """
    offenders = []
    for p in CHIPVERILOG + VERILOGEVAL:
        spec = p.read_text(encoding="utf-8", errors="replace")
        paragraphs = [b for b in spec.split("\n\n") if b.strip()]
        units = divide(spec)
        if len(paragraphs) > 1 and len(units) < 2:
            offenders.append((p.parent.name, len(paragraphs), len(units)))
    assert not offenders, offenders[:5]


def test_the_largest_unit_stays_tractable_for_the_classifier():
    """Not a correctness property -- a cost one, and it is reported as such.

    Each unit becomes one small model call, so an outlier unit is an outlier
    call. The first cut produced an 11,968-character unit from
    `fpu_addsub_pipeline`'s unmarked 215-line definition list; splitting that
    brought the corpus maximum to 2,948. The bound below is generous headroom
    over that, and if a new corpus breaches it the right response is to look at
    the shape it found, not to raise the number.
    """
    worst = (0, "")
    for p in CHIPVERILOG + VERILOGEVAL:
        spec = p.read_text(encoding="utf-8", errors="replace")
        for u in divide(spec):
            if u.length > worst[0]:
                worst = (u.length, p.parent.name if p.name == "description.txt" else p.name)
    assert worst[0] < 4000, f"largest unit is {worst[0]} chars in {worst[1]}"


def test_overlaps_and_coverage_detect_what_they_claim_to():
    """Guard the guards: both reporters must fire on a constructed defect."""
    spec = "First sentence here.\n\nSecond sentence here.\n\nThird sentence here.\n"
    good = divide(spec)
    assert not overlaps(good)
    assert not coverage(spec, good)[2]

    a, b = good[0], good[1]
    assert overlaps([a, Unit(a.end - 2, b.end, "paragraph")])
    assert coverage(spec, [a])[2], "a dropped unit must be reported as a gap"
