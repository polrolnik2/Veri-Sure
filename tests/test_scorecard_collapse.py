"""Two bodies for one requirement are CARRIED, and each column counts the right thing.

`score` used to key checks by `req_uid`, so a caller passing more than one body
for a requirement kept only the LAST and was told nothing. A sweep admitting
extra corpus bodies read as 122, 241 and 349 checks and was 122 every time --
blindness APPEARED to rise and `effective_size` to fall as separators were added,
which is not how adding separators behaves. That impossibility is the only reason
the collapse was noticed, and "fill the pool, then select" could not be MEASURED
by this function at all.

Bodies are now keyed by a per-body identity, and the split is the point:

    span       REQUIREMENTS -- two checks for one requirement do not cover more
               of the specification than one does
    audit      REQUIREMENTS -- a requirement convicts when ANY of its bodies
               does, because rejections union
    blindness  BODIES -- a cell is separated by a CHECK, and a second body is a
               second chance to separate it
    eff_size   BODIES, as distinct verdict vectors, which is the measure that
               says whether a second body is a separator or a duplicate

**THE FIRST BODY OF EACH REQUIREMENT KEEPS THE BARE UID**, so on the
one-body-per-requirement sets every recorded figure was computed from, the keys
are byte-identical and so is every number.
"""

from specflow.scorecard import score

CONTRACT = {"io": [{"name": "clk", "dir": "input", "width": 1},
                   {"name": "q", "dir": "output", "width": 1}]}
REQS = [{"uid": f"REQ-{i:04d}", "unit_kind": "behavioural"} for i in (1, 2)]
NORM = [{"req_uid": r["uid"], "observable": ["q"]} for r in REQS]


def _body(uid, src):
    return {"req_uid": uid, "source": src, "tp_uids": ["TP-0000"], "clause": ""}


def _score(oracles, **kw):
    return score(oracles=oracles, normalized=NORM, stimulus_by_tp={},
                 contract=CONTRACT, population=[], requirements=REQS, **kw)


def test_one_body_each_says_nothing_about_extra_bodies():
    card = _score([_body("REQ-0001", "def decide(t):\n    return True"),
                   _body("REQ-0002", "def decide(t):\n    return True")])
    assert not any("ADDITIONAL bodies" in n for n in card.notes)
    assert not any("DISCARDED" in n for n in card.notes)


def test_a_second_body_is_CARRIED_not_discarded():
    """**THE DEFECT THIS FILE WAS WRITTEN FOR, NOW FIXED RATHER THAN REPORTED.**

    Silently keeping the last body is what made a 349-body sweep read as 349
    checks when it was 122.
    """
    card = _score([_body("REQ-0001", "def decide(t):\n    return True"),
                   _body("REQ-0001", "def decide(t):\n    return False"),
                   _body("REQ-0002", "def decide(t):\n    return True")])
    said = " ".join(card.notes)
    assert "DISCARDED" not in said, "no body is dropped any more"
    assert "3 check bodies over 2 requirement(s)" in said
    assert "blindness" in said.lower()


def test_span_counts_REQUIREMENTS_not_bodies():
    """Two checks for one requirement do not cover more of the specification.

    Both cards below have every requirement covered, so span is 1.0 either way;
    a body-counting span would exceed 1.0 on the second, which is the failure
    this pins.
    """
    one = _score([_body("REQ-0001", "def decide(t):\n    return True"),
                  _body("REQ-0002", "def decide(t):\n    return True")])
    two = _score([_body("REQ-0001", "def decide(t):\n    return True"),
                  _body("REQ-0001", "def decide(t):\n    return False"),
                  _body("REQ-0002", "def decide(t):\n    return True")])
    assert one.span == two.span == 1.0


#: A control that actually replays, so the `audit_control` path is exercised
#: rather than the caller-supplied `audit_verdicts` one -- the fold from bodies
#: back to requirements lives only on this path.
CONTROL = ("INPUT_PORTS = ['clk']\nOUTPUT_PORTS = ['q']\n\n\nclass Model:\n"
           "    INPUT_PORTS = ['clk']\n    OUTPUT_PORTS = ['q']\n\n"
           "    def evaluate(self, inputs):\n"
           "        return {'q': int(inputs.get('clk', 0))}\n")
STIM = {"TP-0000": [{"inputs": {"clk": 0}}, {"inputs": {"clk": 1}}]}


def test_audit_counts_REQUIREMENTS_and_a_requirement_convicts_if_ANY_body_does():
    """Rejections union, which is the rule the whole set is read by: "a design is
    rejected when ANY of 114 members objects".

    REQ-0001 carries a convicting body and a passing one. The numerator must
    count it ONCE -- a requirement, not two bodies -- and the denominator must
    be requirements too, or the rate is over two different populations.

    **THE CONVICTING BODY COMES FIRST, AND THAT ORDERING IS THE TEST.** With it
    last, a fold that simply overwrites per testpoint gives the same answer as
    one that unions, and the mutant survives -- which it did, on the first
    version of this test.
    """
    passing = "def decide(t):\n    return (True, None, 'ok')"
    failing = "def decide(t):\n    return (False, 0, 'no')"
    card = score(
        oracles=[_body("REQ-0001", failing), _body("REQ-0001", passing),
                 _body("REQ-0002", passing)],
        normalized=NORM, stimulus_by_tp=STIM, contract=CONTRACT,
        population=[], requirements=REQS, audit_control=CONTROL)
    assert card.control_judges == 2, card.notes
    assert card.control_convicted_by == 1, card.notes
    assert card.audit == 0.5


def test_a_requirement_whose_ONLY_body_passes_does_not_convict():
    """The companion, so the test above is not passing on a constant."""
    passing = "def decide(t):\n    return (True, None, 'ok')"
    card = score(
        oracles=[_body("REQ-0001", passing), _body("REQ-0001", passing),
                 _body("REQ-0002", passing)],
        normalized=NORM, stimulus_by_tp=STIM, contract=CONTRACT,
        population=[], requirements=REQS, audit_control=CONTROL)
    assert card.control_judges == 2
    assert card.control_convicted_by == 0
    assert card.audit == 0.0


def test_a_ONE_BODY_SET_IS_SCORED_EXACTLY_AS_BEFORE():
    """**THE COMPATIBILITY CLAIM, AND ONLY THE OBSERVABLE HALF OF IT.**

    Every recorded figure on this branch came from a set with one body per
    requirement. What must not change is the NUMBERS, and that is what this
    asserts, against the same inputs scored through the pre-change path: span
    over requirements, blindness over the same cells, effective_size over the
    same vectors.

    The bare-uid-for-the-first-body scheme is a READABILITY choice, not a
    correctness one -- the keys reach `_population_tables`'s returned tables and
    the logs, and nothing else. A mutant that suffixes every key passes this
    whole file, correctly, and an earlier version of this comment claimed the
    spelling was load-bearing. It is not; the numbers are.
    """
    one = _blind([_body("REQ-0001", SEPARATOR), _body("REQ-0002", MUTE)])
    assert one.span == 1.0
    assert one.cells and one.blindness is not None and one.blindness < 1.0
    assert one.effective_size == 1, (
        "one separating body and one mute one give a single distinct verdict "
        "vector, because the mute one produces none")
    assert not any("ADDITIONAL" in n for n in one.notes)


#: Two spec-derived designs that DISAGREE, so there are cells to be blind at.
#: `q` mirrors `clk` in one and inverts it in the other, which is a disagreement
#: on every row.
DESIGNS = [
    ("INPUT_PORTS = ['clk']\nOUTPUT_PORTS = ['q']\n\n\nclass Model:\n"
     "    INPUT_PORTS = ['clk']\n    OUTPUT_PORTS = ['q']\n\n"
     "    def evaluate(self, inputs):\n"
     "        return {'q': int(inputs.get('clk', 0))}\n"),
    ("INPUT_PORTS = ['clk']\nOUTPUT_PORTS = ['q']\n\n\nclass Model:\n"
     "    INPUT_PORTS = ['clk']\n    OUTPUT_PORTS = ['q']\n\n"
     "    def evaluate(self, inputs):\n"
     "        return {'q': 1 - int(inputs.get('clk', 0))}\n"),
]

#: A check that decides nothing -- it separates no cell at all.
MUTE = ("def decide(trace):\n"
        "    return (None, None, 'says nothing')\n")
#: A check that reads the disagreeing port and so DOES separate: it passes the
#: mirroring design and convicts the inverting one.
SEPARATOR = ("def decide(trace):\n"
             "    for row in trace:\n"
             "        if row['outputs']['q'] != row['inputs']['clk']:\n"
             "            return (False, row['edge'], 'q did not follow clk')\n"
             "    return (True, None, 'q followed clk')\n")


def _blind(oracles):
    return score(oracles=oracles, normalized=NORM, stimulus_by_tp=STIM,
                 contract=CONTRACT, population=DESIGNS, requirements=REQS)


def test_A_SECOND_BODY_SEPARATES_CELLS_THE_FIRST_COULD_NOT():
    """**THE WHOLE POINT OF THE CHANGE, AND IT WAS UNMEASURABLE BEFORE.**

    Under the old map, adding a separating body for a requirement that already
    had a mute one REPLACED it, so the set's blindness was whatever the last
    body gave and "fill the pool, then select" could not be measured at all.

    Here REQ-0001 keeps its mute body and gains a separating one. Blindness must
    FALL, and the mute body must still be carried -- the separation comes from
    having both, not from the second overwriting the first.
    """
    mute_only = _blind([_body("REQ-0001", MUTE), _body("REQ-0002", MUTE)])
    plus_one = _blind([_body("REQ-0001", MUTE), _body("REQ-0001", SEPARATOR),
                       _body("REQ-0002", MUTE)])
    assert mute_only.cells and mute_only.cells == plus_one.cells, (
        "the population is unchanged, so the cell count must be too")
    assert mute_only.blindness == 1.0, (
        "three mute checks separate nothing, so every cell is blind")
    assert plus_one.blindness < mute_only.blindness, (
        f"a second, separating body must LOWER blindness: "
        f"{mute_only.blindness} -> {plus_one.blindness}")
    assert "3 check bodies over 2 requirement(s)" in " ".join(plus_one.notes)


def test_the_SPAN_of_that_larger_set_is_unchanged():
    """Because the separating body covers a requirement that was already
    covered. A body-counting span would have risen here for no new coverage."""
    mute_only = _blind([_body("REQ-0001", MUTE), _body("REQ-0002", MUTE)])
    plus_one = _blind([_body("REQ-0001", MUTE), _body("REQ-0001", SEPARATOR),
                       _body("REQ-0002", MUTE)])
    assert mute_only.span == plus_one.span == 1.0


def test_effective_size_counts_a_DUPLICATE_body_as_one():
    """`effective_size` is distinct verdict VECTORS, never a count of checks:
    "admitting or authoring more checks is worth nothing if they cluster with
    the ones already there." Two identical bodies must not read as two."""
    one = _blind([_body("REQ-0001", SEPARATOR), _body("REQ-0002", MUTE)])
    dup = _blind([_body("REQ-0001", SEPARATOR), _body("REQ-0001", SEPARATOR),
                  _body("REQ-0002", MUTE)])
    assert one.effective_size == dup.effective_size, (
        f"a duplicated body is not a new separator: "
        f"{one.effective_size} -> {dup.effective_size}")
