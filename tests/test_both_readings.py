"""One property under BOTH temporal readings is the conjunction of two.

`effect_follows` is a single decision about a requirement -- does the effect follow
the trigger? -- so a body calling the same operator on the same window with
`after_activation=True` and again with `False` has not transcribed a reading, it has
taken the conjunction. It reports FAIL if EITHER fails, and is therefore strictly
stronger than either alone, which no requirement states.

**Provable from the source, with no design and no reference**, which is the same
standing as the `TO_END` refusal that already ships.

AND THE POPULATION TEST THAT ALMOST KEPT THIS OUT WAS APPLIED INCONSISTENTLY. The
shape matches 2 bodies on `full2` and both convict the known-good design, which
looked like gating on the grade -- but the shipped `TO_END` refusal matches 3 of
which 2 convict, and those are not different kinds of evidence. What separates a
structural refusal from grade-gating is whether its STATEMENT needs the grade.
"""

from specflow.refmodel.oracles import RequirementOracle, well_formed
from specflow.refmodel.temporal import both_readings

CONTRACT = {"io": [{"name": "clk", "dir": "input", "width": 1},
                   {"name": "q", "dir": "output", "width": 1}]}
PLAN = [{"uid": "TP-0000", "req_uid": "REQ-0001"}]

#: The shape, as a frozen body actually wrote it: compute `|->`, report that
#: failure, and reach the `|=>` reading only when the stricter one passed.
DOUBLED = (
    "from specflow.refmodel.temporal import TO_END, after, throughout, worst\n"
    "\n"
    "\n"
    "def decide(trace):\n"
    "    def hi(row):\n"
    "        return row['outputs'].get('q') == 1\n"
    "    windows = after(trace, hi, until=lambda r: r['outputs'].get('q') == 0)\n"
    "    out = []\n"
    "    for w in windows:\n"
    "        strict = throughout(w, hi, after_activation=False)\n"
    "        if strict[0] is False:\n"
    "            out.append(strict)\n"
    "            continue\n"
    "        out.append(throughout(w, hi, after_activation=True))\n"
    "    return worst(out)\n")

SINGLE = DOUBLED.replace(
    "        strict = throughout(w, hi, after_activation=False)\n"
    "        if strict[0] is False:\n"
    "            out.append(strict)\n"
    "            continue\n", "")


def test_the_same_operator_on_the_same_window_both_ways_is_FLAGGED():
    assert both_readings(DOUBLED) == ["throughout"]


def test_one_reading_is_not_flagged():
    assert both_readings(SINGLE) == []


def test_two_DIFFERENT_windows_are_two_claims_and_not_this():
    """Keyed on the window expression as written. A body asserting `|->` about one
    situation and `|=>` about another has made two claims about two situations,
    which is not the conjunction of two readings of one."""
    src = ("def decide(trace):\n"
           "    a = throughout(w1, p, after_activation=False)\n"
           "    b = throughout(w2, p, after_activation=True)\n"
           "    return worst([a, b])\n")
    assert both_readings(src) == []


def test_two_DIFFERENT_operators_are_not_this_either():
    """An invariant and an existential read different row sets -- `governed`/`extent`
    against `body`/`rows` -- so the same flag means opposite things to them and one
    of each is not a doubled claim."""
    src = ("def decide(trace):\n"
           "    a = throughout(w, p, after_activation=False)\n"
           "    b = eventually(w, p, strong=True, after_activation=True)\n"
           "    return worst([a, b])\n")
    assert both_readings(src) == []


def test_a_NON_CONSTANT_flag_is_not_flagged():
    """`after_activation=follows` is a variable, and guessing what it will be at
    replay is not a static judgement this may make."""
    src = ("def decide(trace, follows=True):\n"
           "    a = throughout(w, p, after_activation=follows)\n"
           "    b = throughout(w, p, after_activation=False)\n"
           "    return worst([a, b])\n")
    assert both_readings(src) == []


def test_a_SYNTAX_ERROR_yields_nothing_rather_than_raising():
    """`well_formed` has a static screen ahead of this one; a body that does not
    parse is its finding, not this function's."""
    assert both_readings("def decide(:\n") == []


def test_well_formed_REFUSES_it_and_says_which_operator():
    o = RequirementOracle(req_uid="REQ-0001", tp_uids=["TP-0000"], clause="c",
                          source=DOUBLED)
    why = well_formed(o, CONTRACT, PLAN)
    assert why and "throughout" in why
    assert "after_activation=True" in why and "False" in why
    assert "single decision" in why, (
        "the objection must say WHY, or a repair round has nothing to act on")


def test_well_formed_ACCEPTS_the_single_reading():
    o = RequirementOracle(req_uid="REQ-0001", tp_uids=["TP-0000"], clause="c",
                          source=SINGLE)
    assert well_formed(o, CONTRACT, PLAN) is None
