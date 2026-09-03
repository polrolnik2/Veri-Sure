"""An instrument that reads the same for every input is not an instrument.

`test_adequacy.py` asks whether an oracle would notice a different MODEL, and
needs the mutation operator to produce one it can see -- on `n-i2c` 44 of 70
oracles never got three. These pins are for the question asked directly on the
trace, where the difference is constructed rather than hoped for.
"""

from __future__ import annotations

from specflow.refmodel import liveness
from specflow.refmodel.oracles import RequirementOracle

CONTRACT = {"io": [
    {"name": "clk", "dir": "input", "width": 1},
    {"name": "a", "dir": "input", "width": 4},
    {"name": "y", "dir": "output", "width": 8},
    {"name": "hit", "dir": "output", "width": 1},
    {"name": "pin", "dir": "output", "width": 1},
]}

#: `y` accumulates, `hit` pulses, `pin` never moves -- the three cases the
#: verdict has to tell apart.
MODEL = """\
from specflow.refmodel.base import RefModel


class Model(RefModel):
    OUTPUT_PORTS = ['y', 'hit', 'pin']
    LATENCY_CYCLES = 0

    def reset(self):
        self.n = 0
        self.k = 0

    def step(self, i):
        if not hasattr(self, 'n'):
            self.reset()
        self.k = self.k + 1
        self.n = self.mask(self.n + i['a'], 8)
        return {'y': self.n, 'hit': 1 if self.k == 3 else 0, 'pin': 0}
"""

STIM = {"TP-0000": [{"a": 3}, {"a": 5}, {"a": 7}, {"a": 1}, {"a": 2}, {"a": 6}]}

#: Reproduces the design's rule, so any change to `y` fails it. Live NEAR.
SHARP = """\
def decide(trace):
    total = 0
    for row in trace:
        total = (total + row['inputs']['a']) % 256
        if row['outputs']['y'] != total:
            return False, row['edge'], 'y does not follow the rule'
    return True, 0, 'y followed the rule'
"""

#: Can fail -- but only above 200, and `y` never exceeds 24 here. The check is
#: sound and this stimulus cannot decide it: a testplan finding, not the
#: author's, and the distinction only exists because FAR is tried separately.
FAR_THRESHOLD = """\
def decide(trace):
    for row in trace:
        if row['outputs']['y'] > 200:
            return False, row['edge'], 'y too large'
    return True, 0, 'y stayed small'
"""

#: Reads `y`, decides on nothing. The shape 11 CONFORMS verdicts had.
VACUOUS = """\
def decide(trace):
    for row in trace:
        _ = row['outputs']['y']
    return True, 0, 'looked at y and concluded nothing'
"""

#: Asserts only on a port the design holds constant. Route: the stimulus.
ON_A_CONSTANT = """\
def decide(trace):
    for row in trace:
        if row['outputs']['pin'] != 0:
            return False, row['edge'], 'pin moved'
    return True, 0, 'pin held'
"""

#: TRIGGERS on `hit`, ASSERTS on `y`. `ports_read` cannot tell these apart and
#: reports both; this must report only `y`.
TRIGGER_AND_ASSERT = """\
def decide(trace):
    total = 0
    for row in trace:
        total = (total + row['inputs']['a']) % 256
        if row['outputs']['hit'] == 1 and row['outputs']['y'] != total:
            return False, row['edge'], 'y wrong when hit'
    return True, 0, 'ok'
"""


def _oracle(source: str, uid: str = "REQ-0001", tps=("TP-0000",)):
    return RequirementOracle(req_uid=uid, tp_uids=list(tps),
                             clause="y accumulates a", source=source)


def _assess(source: str, uid: str = "REQ-0001", tps=("TP-0000",)) -> dict:
    report = liveness.assess([_oracle(source, uid, tps)], MODEL, CONTRACT,
                             STIM, base="step")
    return report[uid]


def test_an_oracle_that_can_fail_is_live():
    record = _assess(SHARP)
    assert record["verdict"] == liveness.LIVE, record["detail"]
    assert "y" in record["asserts_on"]


def test_an_oracle_that_decides_nothing_is_dead():
    """The measured shape: reads a port, returns True whatever it holds."""
    record = _assess(VACUOUS)
    assert record["verdict"] == liveness.DEAD_ORACLE, record["detail"]


def test_a_check_the_stimulus_never_approaches_accuses_the_testplan():
    """Two causes, two owners, and the split is measured rather than guessed.

    This oracle CAN fail -- driving `y` to the top of its range does it -- and
    the stimulus never takes `y` above 24. Telling the author to strengthen a
    sound check is the misrouting `verdict.ROUTE` exists to stop, one level
    down, and only trying FAR separately can tell this from a check that
    cannot fail at all.
    """
    record = _assess(FAR_THRESHOLD)
    assert record["verdict"] == liveness.DEAD_STIMULUS, record["detail"]
    assert record["asserts_on"] == [] and record["asserts_on_far"] == ["y"]


def test_near_and_far_differ_on_a_one_bit_port_that_moves():
    """The split survives a design whose observable ports are all one bit.

    Worth pinning because the obvious reading is wrong. A one-bit port has only
    one other value, so on a SINGLE row near and far are the same edit -- but
    near flips each row against whatever it holds, preserving the pattern
    inverted, while a far target flattens every row to one value. On a port
    that moves those are different traces, and i2c, whose every observable is
    one bit, still produced three `DEAD_STIMULUS` verdicts.
    """
    assert liveness._targets(1) == [0, 1]
    flat = [{"edge": 0, "inputs": {}, "outputs": {"pin": 0}}]
    assert (liveness._perturb(flat, "pin", 1, None, liveness.NEAR)[0]["outputs"]
            == liveness._perturb(flat, "pin", 1, None, 1)[0]["outputs"])

    moving = [{"edge": i, "inputs": {}, "outputs": {"pin": i % 2}}
              for i in range(4)]
    near = liveness._perturb(moving, "pin", 1, None, liveness.NEAR)
    far = liveness._perturb(moving, "pin", 1, None, 1)
    assert [r["outputs"]["pin"] for r in near] == [1, 0, 1, 0]
    assert [r["outputs"]["pin"] for r in far] == [1, 1, 1, 1]


def test_only_the_authors_dead_oracles_are_handed_back():
    report = liveness.assess(
        [_oracle(VACUOUS, "REQ-0001"), _oracle(FAR_THRESHOLD, "REQ-0002"),
         _oracle(SHARP, "REQ-0003")],
        MODEL, CONTRACT, STIM, base="step")
    assert set(liveness.dead(report)) == {"REQ-0001"}


def test_a_trigger_port_is_not_reported_as_an_assertion():
    """`adequacy` scopes its mutants on `ports_read`, which counts both.

    Measured on the frozen set: 45% of the ports it scopes on carry no
    assertion, so the mutants that count include ones the oracle was never
    able to catch.
    """
    record = _assess(TRIGGER_AND_ASSERT)
    assert record["verdict"] == liveness.LIVE
    assert "hit" in record["reads"], "the trigger port is still READ"
    moved = set(record["asserts_on"]) | set(record["asserts_on_far"])
    assert moved == {"y"}, moved


def test_perturbation_stays_inside_the_declared_width():
    """The illegal-mutant lesson, avoided by construction rather than filtered.

    A one-bit port that receives a literal 2 convicts every oracle that wrote
    `== 1` instead of treating it as a boolean, which is a style difference.
    Here the perturbation is chosen modulo the width, so the value is one an
    implementation could have produced.
    """
    rows = [{"edge": 0, "inputs": {}, "outputs": {"hit": 0, "y": 250}}]
    for port, width, ceiling in (("hit", 1, 2), ("y", 8, 256)):
        for target in [liveness.NEAR, *liveness._targets(width)]:
            moved = liveness._perturb(rows, port, width, None, target)
            if moved is None:
                continue          # already carries that target
            assert 0 <= moved[0]["outputs"][port] < ceiling
            assert moved[0]["outputs"][port] != rows[0]["outputs"][port]


def test_inputs_are_never_perturbed():
    """Changing an input asks a DIFFERENT question of the design.

    An oracle that failed to notice would be right not to, so crediting it with
    liveness for reacting would credit the wrong thing.
    """
    assert "a" not in liveness._widths(CONTRACT)
    record = _assess("""\
def decide(trace):
    for row in trace:
        if row['inputs']['a'] > 99:
            return False, row['edge'], 'a too large'
    return True, 0, 'ok'
""")
    assert record["verdict"] != liveness.LIVE


def test_every_oracle_appears_including_the_ones_nothing_decided():
    """A report that omits what it could not judge reads as a clean result."""
    report = liveness.assess(
        [_oracle(SHARP, "REQ-0001"), _oracle(SHARP, "REQ-0002", ("TP-NONE",)),
         _oracle("def decide(trace):\n    return True, 0, 'ok'\n", "REQ-0003")],
        MODEL, CONTRACT, STIM, base="step")
    assert set(report) == {"REQ-0001", "REQ-0002", "REQ-0003"}
    assert report["REQ-0002"]["verdict"] == liveness.UNKNOWN
    assert "no testpoint" in report["REQ-0002"]["detail"]
    assert report["REQ-0003"]["verdict"] == liveness.UNKNOWN
    assert "no declared output port" in report["REQ-0003"]["detail"]


def test_counts_keep_their_zeroes():
    report = liveness.assess([_oracle(SHARP)], MODEL, CONTRACT, STIM,
                             base="step")
    assert liveness.counts(report) == {
        liveness.LIVE: 1, liveness.DEAD_ORACLE: 0,
        liveness.DEAD_STIMULUS: 0, liveness.UNKNOWN: 0}


def test_a_model_that_will_not_run_is_unknown_not_dead():
    """A broken model is not evidence against a check."""
    report = liveness.assess([_oracle(SHARP)], "def nope(:\n", CONTRACT, STIM,
                             base="step")
    assert report["REQ-0001"]["verdict"] == liveness.UNKNOWN


def test_the_verdict_does_not_depend_on_which_design_it_ran_against():
    """What makes the witness a sufficient stand-in for [O].

    Measured on the frozen 70: identical counts against a generated model
    scoring 30/168 and against the known-good control at 168/168 -- live 44,
    dead-oracle 20, dead-stimulus 3, unknown 3 -- while five oracles reach
    different base verdicts on those two designs and four have different
    assertion port sets. Pinned here on a pair that differ the same way: one
    model satisfies the check and one violates it, and neither can make a
    vacuous oracle able to fail or a sharp one unable to.
    """
    violating = MODEL.replace("'y': self.n", "'y': self.mask(self.n + 1, 8)")
    assert violating != MODEL

    for source in (MODEL, violating):
        report = liveness.assess(
            [_oracle(SHARP, "REQ-0001"), _oracle(VACUOUS, "REQ-0002")],
            source, CONTRACT, STIM, base="step")
        assert report["REQ-0001"]["verdict"] == liveness.LIVE
        assert report["REQ-0002"]["verdict"] == liveness.DEAD_ORACLE

    # and the premise: the two designs really are decided differently
    base = liveness.assess([_oracle(SHARP)], MODEL, CONTRACT, STIM,
                           base="step")["REQ-0001"]["base"]
    other = liveness.assess([_oracle(SHARP)], violating, CONTRACT, STIM,
                            base="step")["REQ-0001"]["base"]
    assert base != other, "otherwise this pins nothing"


# ------------------------------------------- judged before anything happened


CONTRACT_OD = {"io": [
    {"name": "clk", "dir": "input", "width": 1},
    {"name": "cmd", "dir": "input", "width": 4},
    {"name": "scl_oen", "dir": "output", "width": 1},
    {"name": "sda_oen", "dir": "output", "width": 1},
]}

#: Reads both enables, so `ports_read` picks them up.
WATCHES = ("def decide(trace):\n"
           "    for r in trace:\n"
           "        if r['outputs']['scl_oen'] == 1 and r['outputs']['sda_oen']:\n"
           "            return False, r['edge'], 'no prior drive'\n"
           "    return True, 0, 'ok'\n")


def _od(*states):
    return [{"edge": i, "inputs": {}, "outputs": {"scl_oen": a, "sda_oen": b}}
            for i, (a, b) in enumerate(states)]


def _od_oracle():
    from specflow.refmodel.oracles import RequirementOracle

    return RequirementOracle(req_uid="REQ-0070", tp_uids=["TP-0000"],
                             clause="SDA low before SCL released",
                             source=WATCHES)


def test_deciding_at_idle_when_the_scenario_comes_later_accuses_the_od_oracle():
    """Open-drain makes idle and deasserted the same value.

    The control resets to `scl_oen = 1, sda_oen = 1` -- exactly what "release
    the line" tells an oracle to look for -- so a level scan matches edge 0.
    REQ-0070 demands SDA low before SCL release and the control does it at edges
    4 and 5; the oracle finds `scl_oen == 1` at edge 0 and fails.
    """
    from specflow.refmodel.liveness import judged_before_the_scenario

    rows = _od((1, 1), (1, 1), (0, 0), (1, 0))
    why = judged_before_the_scenario(_od_oracle(), rows, CONTRACT_OD, at_edge=0)
    assert why, "an idle match should be accused"
    assert "reset value" in why and "moves" in why


def test_a_reset_defect_is_not_waved_away():
    """The second condition, and the reason it exists.

    A requirement genuinely about the reset state, failing because the reset
    state is wrong, must NOT be excused. Here nothing the oracle reads ever
    moves, so the scenario is not "later in the trace" -- it is absent, and that
    is a different finding with a different owner.
    """
    from specflow.refmodel.liveness import judged_before_the_scenario

    rows = _od((1, 1), (1, 1), (1, 1))
    assert not judged_before_the_scenario(
        _od_oracle(), rows, CONTRACT_OD, at_edge=0)


def test_a_failure_after_things_moved_is_left_alone():
    """Once what it watches has moved, the oracle was judging the scenario."""
    from specflow.refmodel.liveness import judged_before_the_scenario

    rows = _od((1, 1), (0, 0), (1, 0), (1, 1))
    assert not judged_before_the_scenario(
        _od_oracle(), rows, CONTRACT_OD, at_edge=3)


def test_it_is_incomplete_and_that_is_recorded():
    """Measured on w-i2c: it catches 3 of the 15 the control fails, not 5.

    REQ-0003, REQ-0020 and REQ-0065 fail at edges where SOME port they read has
    already moved, so "nothing has moved yet" is too strict for them. Pinned so
    the shortfall is a known property rather than a surprise -- an unknown edge
    is never guessed at either.
    """
    from specflow.refmodel.liveness import judged_before_the_scenario

    rows = _od((1, 1), (0, 0), (1, 0))
    assert not judged_before_the_scenario(
        _od_oracle(), rows, CONTRACT_OD, at_edge=None)
    assert not judged_before_the_scenario(_od_oracle(), [], CONTRACT_OD, at_edge=0)


# ----------------------------------------------- the detector reaches the author

def test_the_idle_match_note_reaches_verify_one(monkeypatch):
    """`judged_before_the_scenario` was built, tested, and had NO CALLERS.

    That is the same shape as `stimulus_liveness`, which existed for months
    while nothing invoked it: an instrument that measures correctly and decides
    nothing. This pins the wiring rather than the arithmetic -- the arithmetic
    is pinned above.
    """
    from specflow import oracles_stage as S

    seen = {}

    def _fake(oracle, rows, contract, *, at_edge):
        seen["called"] = True
        return "judged at edge 0, before any of scl_oen had moved"

    monkeypatch.setattr(S._L, "judged_before_the_scenario", _fake)

    notes = {"witness": "fails it at edge 0 -- scl_oen never released",
             "idle_match": _fake(None, [], {}, at_edge=0)}
    issues = S._witness_note("REQ-0070", notes)

    assert issues[0].path.endswith("judged_at_idle"), "the precise note leads"
    assert [i.path.rsplit(".", 1)[-1] for i in issues] == [
        "judged_at_idle", "witness_disagrees_reported"], (
        "the witness failure travels with it -- dropping it froze five checks "
        "on h3-i2c that then convicted golden")


def test_the_specific_note_replaces_the_relaxation_request():
    """Both messages ask for an edit and they pull in opposite directions.

    `_advisory` asks the author to TRY to accept a second implementation, which
    measured as pressure toward relaxation -- over-strictness 27 -> 15 and
    convictions 2 -> 16 when declining meant the oracle was discarded. The idle
    note names an exact defect whose repair makes the check MORE precise.
    Sending the RELAXATION REQUEST alongside would invite weakening for a
    defect that has a specific fix -- so `_advisory` is still not sent.

    What changed: the witness FAILURE is no longer dropped along with it. On
    h3-i2c five checks carried both keys, went out with the idle note only,
    froze TRUSTED, and all five convicted golden. The idle note still leads;
    a non-relaxing record of the disagreement follows it.
    """
    from specflow import oracles_stage as S

    both = S._witness_note("REQ-0070", {
        "witness": "fails it at edge 0 -- scl_oen never released",
        "idle_match": "judged at edge 0, before any of scl_oen had moved"})
    assert [i.path.rsplit(".", 1)[-1] for i in both] == [
        "judged_at_idle", "witness_disagrees_reported"], (
        "the specific note leads; the witness verdict is recorded, not dropped")
    assert not any("witness_disagrees" == i.path.rsplit(".", 1)[-1]
                   for i in both), (
        "the RELAXATION REQUEST must still not be sent alongside")

    generic = S._witness_note("REQ-0070", {
        "witness": "fails it at edge 4 -- scl_oen released too early"})
    assert len(generic) == 1
    assert "witness_disagrees" in generic[0].path

    assert S._witness_note("REQ-0070", {}) == []


def test_the_idle_advisory_does_not_ask_for_a_weaker_check():
    """The safety property. A note that says 'accept this' where the defect is
    over-strictness is fine; one that says it where the defect is a level read
    would trade a wrong check for an emptier one."""
    from specflow import oracles_stage as S

    body = S._idle_advisory("REQ-0070", "judged at edge 0").message.lower()
    body = " ".join(body.split())          # line wraps have cost this repo before

    assert "transition" in body and "level" in body
    assert "compare consecutive rows" in body
    assert "keep your check as it is" in body, "declining must stay available"
    assert "relax" not in body


# --------------------------------------- 22: an oracle that disagrees with itself

_SPLIT_MODEL = """\
from specflow.refmodel.base import RefModel


class Model(RefModel):
    OUTPUT_PORTS = ['y']
    LATENCY_CYCLES = 0

    def step(self, i):
        return {'y': i['a']}
"""

#: Holds wherever `a` is 0 and breaks wherever `a` is 1, so which testpoints an
#: oracle names decides how often it fails.
_SPLIT_ORACLE = """\
def decide(trace):
    for row in trace:
        if row['inputs']['a'] == 1:
            return False, row['edge'], 'a went high'
    return True, 0, 'a stayed low'
"""

_QUIET = [{"a": 0}, {"a": 0}]
_LOUD = [{"a": 0}, {"a": 1}]
_SPLIT_CONTRACT = {"io": [
    {"name": "clk", "dir": "input", "width": 1},
    {"name": "a", "dir": "input", "width": 1},
    {"name": "y", "dir": "output", "width": 1},
]}


def _split_oracle(*tps: str):
    from specflow.refmodel.oracles import RequirementOracle
    return RequirementOracle(req_uid="REQ-0066", tp_uids=list(tps),
                             clause="a stays low", source=_SPLIT_ORACLE)


def test_a_check_that_holds_on_most_of_its_testpoints_is_reported():
    """REQ-0066 passes 4 of its testpoints and fails 1; REQ-0060 passes 3 and
    fails 1. `decide_all` reports the single failure as the whole verdict --
    the first failure is the answer -- so four agreements vanish behind one
    mismatch."""
    note = liveness.disagrees_with_itself(
        _split_oracle("TP-A", "TP-B", "TP-C", "TP-D"), _SPLIT_MODEL,
        _SPLIT_CONTRACT,
        {"TP-A": _QUIET, "TP-B": _QUIET, "TP-C": _QUIET, "TP-D": _LOUD},
        base="step")

    assert "holds on 3" in note
    assert "TP-D" in note


def test_a_bare_majority_is_not_a_split():
    """The dangerous twin: 'passes some, fails one' is also what a CORRECT
    oracle looks like catching a defect visible in one scenario. Two passes and
    strictly more passes than failures is where the two separate, so 1-of-2 and
    2-of-4 both stay silent."""
    two_two = liveness.disagrees_with_itself(
        _split_oracle("TP-A", "TP-B", "TP-C", "TP-D"), _SPLIT_MODEL,
        _SPLIT_CONTRACT,
        {"TP-A": _QUIET, "TP-B": _QUIET, "TP-C": _LOUD, "TP-D": _LOUD},
        base="step")
    assert two_two == "", "two failures is not one mismatched scenario"

    one_one = liveness.disagrees_with_itself(
        _split_oracle("TP-A", "TP-B"), _SPLIT_MODEL, _SPLIT_CONTRACT,
        {"TP-A": _QUIET, "TP-B": _LOUD}, base="step")
    assert one_one == "", "fewer than three testpoints has no majority to read"


def test_an_oracle_failing_everywhere_is_not_a_split():
    """Uniformly too strict is the case this detector must NOT claim."""
    note = liveness.disagrees_with_itself(
        _split_oracle("TP-A", "TP-B", "TP-C"), _SPLIT_MODEL, _SPLIT_CONTRACT,
        {"TP-A": _LOUD, "TP-B": _LOUD, "TP-C": _LOUD}, base="step")
    assert note == ""


def test_it_needs_no_control_and_convicts_nothing():
    """It asks about the ORACLE'S OWN testpoints against a SINGLE design, so no
    implementation has to be believed correct -- and it returns a reason, never
    a verdict."""
    from specflow import oracles_stage as S

    note = liveness.disagrees_with_itself(
        _split_oracle("TP-A", "TP-B", "TP-C", "TP-D"), _SPLIT_MODEL,
        _SPLIT_CONTRACT,
        {"TP-A": _QUIET, "TP-B": _QUIET, "TP-C": _QUIET, "TP-D": _LOUD},
        base="step")

    issues = S._witness_note("REQ-0066", {"witness": "fails it", "self_split": note})
    assert len(issues) == 1
    assert issues[0].path.endswith("disagrees_with_itself")
    assert issues[0].severity == "warning", "nothing rejects on this"

    body = " ".join(issues[0].message.split())
    assert "KEEP YOUR CHECK EXACTLY AS IT IS" in body, "declining must stay open"
    assert "real defect visible only there" in body.lower()


def test_the_sharper_DIAGNOSIS_wins_but_the_witness_fact_still_travels():
    """Two competing diagnoses is worse than the sharper one alone, and the
    idle read is the sharper -- it names an exact repair. `self_split` is still
    dropped for that reason.

    The witness FAILURE is not a competing diagnosis, though, it is evidence,
    and it is now reported alongside rather than discarded with the loser."""
    from specflow import oracles_stage as S

    issues = S._witness_note("REQ-0070", {
        "witness": "fails it at edge 0",
        "idle_match": "judged at edge 0, before any of scl_oen had moved",
        "self_split": "holds on 3 of the testpoints it names"})
    kinds = [i.path.rsplit(".", 1)[-1] for i in issues]
    assert kinds == ["judged_at_idle", "witness_disagrees_reported"]
    assert "disagrees_with_itself" not in kinds, "the weaker diagnosis loses"


def test_a_check_that_never_triggered_is_not_blamed_on_its_author():
    """The near/far probe edits OUTPUT ports, so a check whose guard is an input
    condition the stimulus never stages abstains on every row and NOTHING can
    move it -- landing in "nothing moved it", DEAD_ORACLE, whatever the cause.

    Measured on z-i2c: all 11 DEAD_ORACLE verdicts were oracles returning None
    on every testpoint they named. Nine were re-asked and told "your check
    cannot fail"; all nine came back unchanged, because an author can neither
    stage a scenario nor supply an observable the requirement does not name.
    """
    # Reads a declared output -- so it passes the "names no output port" guard
    # and reaches the perturbation probe -- but its GUARD is an input value the
    # stimulus never stages, so it abstains on every row.
    never = ("def decide(trace):\n"
             "    for row in trace:\n"
             "        if row['inputs'].get('a') == 99:\n"
             "            if row['outputs']['y'] != 0:\n"
             "                return False, row['edge'], 'bad'\n"
             "            return True, row['edge'], 'ok'\n"
             "    return None, 0, 'the scenario never occurred'\n")
    oracle = RequirementOracle(req_uid="REQ-0001", tp_uids=["TP-0000"],
                               clause="c", source=never)
    traces = liveness.replay_all([oracle], MODEL, CONTRACT, STIM, base="step")
    rec = liveness.liveness_of(oracle, traces, CONTRACT)
    assert rec["verdict"] == liveness.UNKNOWN, rec
    assert "never decided" in rec["detail"], rec["detail"]
    assert liveness.never_decides({"REQ-0001": rec}) , (
        "and the predicate has to name it, since `_dispositions` keys on it")


def test_never_decides_does_not_catch_a_working_check():
    """A predicate that also fires on live oracles would move most of a working
    set into UNOBSERVABLE. The one that decides anything must not be caught."""
    live = RequirementOracle(req_uid="REQ-0002", tp_uids=["TP-0000"],
                             clause="c", source=SHARP)
    traces = liveness.replay_all([live], MODEL, CONTRACT, STIM, base="step")
    rec = liveness.liveness_of(live, traces, CONTRACT)
    assert not liveness.never_decides({"REQ-0002": rec}), rec
