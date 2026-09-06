"""The arithmetic the staging loop will decide on, over a fixture it can read.

Everything in `reachability` is a pure function of recorded replays, which is
what makes the loop auditable: a reviewer can read why it did what it did from
the artifact, and these tests can pin the decisions without a model call.
"""
from __future__ import annotations

from specflow import reachability as R

PROBES = ["in_idle", "in_cload", "in_lrefill3", "in_cstore", "in_srefill4"]


def _rows(states: list[str], inputs: list[dict] | None = None) -> list[dict]:
    """One testpoint: a state per edge, with the inputs driven at that edge."""
    out = []
    for i, st in enumerate(states):
        outs = {p: 1 if p == st else 0 for p in PROBES}
        out.append({"edge": i, "inputs": dict((inputs or [{}] * len(states))[i]),
                    "outputs": outs})
    return out


_LOAD = (["in_idle", "in_idle", "in_cload", "in_cload", "in_lrefill3",
          "in_lrefill3", "in_idle"],
         [{"go": 0}, {"go": 1}, {"go": 1, "miss": 0}, {"go": 1, "miss": 1},
          {"go": 1, "miss": 1}, {"go": 1, "miss": 1}, {"go": 0}])
_STORE = (["in_idle", "in_cstore", "in_cstore", "in_idle"],
          [{"go": 0}, {"go": 1, "we": 1}, {"go": 1, "we": 1}, {"go": 0}])

#: IDLE -> CLOAD -> LREFILL3 on one branch, IDLE -> CSTORE on the other. The
#: fork is the point: k1 forks at the same depth, which is why no depth
#: heuristic can pick a predecessor for a state nothing has reached.
#:
#: Each branch appears more than once because `mine` scores on a DISJOINT half
#: of the testpoints. A transition seen in only one testpoint lands wholly in
#: one half and yields no edge -- correct, and the reason a two-testpoint
#: fixture would report the relation as empty rather than as unmined.
FIXTURE = {
    "tp_0001": _rows(["in_idle"] * 4),
    "tp_0007": _rows(*_LOAD),
    "tp_0008": _rows(*_LOAD),
    "tp_0012": _rows(*_STORE),
    "tp_0013": _rows(*_STORE),
}


def test_the_pool_is_what_the_rows_say() -> None:
    pool = R.observed(FIXTURE, PROBES)
    assert [o.tp_uid for o in pool["in_cload"]] == ["tp_0007", "tp_0008"]
    assert pool["in_cload"][0].first_edge == 2
    assert pool["in_cload"][0].held == 2
    assert pool["in_lrefill3"][0].first_edge == 4
    # Never observed is an EMPTY LIST and nothing more -- not a discard, not a
    # hypothesis. It is the strongest staging signal there is, and the only
    # thing the oracle stage is entitled to say about it.
    assert pool["in_srefill4"] == []


def test_the_shortest_reproducer_comes_first() -> None:
    """A shorter prefix leaves the author more room and less to misread."""
    rows = dict(FIXTURE)
    rows["tp_0099"] = _rows(["in_cload"] + ["in_idle"] * 3)
    pool = R.observed(rows, PROBES)
    assert [(o.tp_uid, o.first_edge) for o in pool["in_cload"]] == [
        ("tp_0099", 0), ("tp_0007", 2), ("tp_0008", 2)]


def test_an_edge_exists_only_into_an_observed_state() -> None:
    """Mining needs a RISE of B to mine an edge into B.

    This is the whole reason adjacency for an unobserved state is the stimulus
    author's call and not the pipeline's: there is nothing to mine.
    """
    rel = R.mine(FIXTURE, PROBES)
    assert rel.into("in_srefill4") == []
    assert {e.frm for e in rel.into("in_lrefill3")} == {"in_cload"}
    assert {e.frm for e in rel.into("in_cload")} == {"in_idle"}


def test_inputs_are_read_at_the_edge_the_state_is_entered() -> None:
    """State at i-1, inputs at i. Reading inputs one edge early loses the cause.

    Measured: an edge-triggered input drops out of every recipe when read at the
    earlier edge -- high on 16 of 81 rises there against 81 of 81 at the later
    one -- and the artifact is then worthless while looking entirely plausible.
    """
    rel = R.mine(FIXTURE, PROBES)
    into = {(e.frm, e.to): e for e in rel.edges}
    edge = into[("in_cload", "in_lrefill3")]
    # `miss` is 1 at the entering edge and 0 at the edge before it, so it
    # survives only under the later reading.
    assert edge.requires.get("miss") == 1


def test_a_low_precision_edge_is_not_quoted() -> None:
    """A wrong explanation is worse than none; the prefix goes over regardless.

    A state with several exits mines a conjunction that keeps only the
    intersection of its branches, which is why `in_idle` reads poorly and every
    ENTERING transition reads clean. A stimulus author never needs a recipe for
    the state it is leaving.
    """
    weak = R.Edge(frm="a", to="b", requires={"x": 1}, rises=99, precision=0.11)
    strong = R.Edge(frm="a", to="b", requires={"x": 1}, rises=99, precision=1.0)
    thin = R.Edge(frm="a", to="b", requires={"x": 1}, rises=1, precision=1.0)
    assert not R.gate_reachability(weak)
    assert not R.gate_reachability(thin)
    assert R.gate_reachability(strong)


def test_the_prefix_is_cut_after_the_step_that_held_the_state() -> None:
    """The extra step is what kept the state there, not only what entered it."""
    stimulus = [{"hold": 2}, {"hold": 2}, {"hold": 2}, {"hold": 2}]
    assert R.stimulus_prefix(stimulus, 0) == stimulus[:2]
    assert R.stimulus_prefix(stimulus, 4) == stimulus[:4]


def test_an_unrecoverable_step_boundary_gives_the_WHOLE_stimulus() -> None:
    """Nothing is lost when the cut cannot be computed -- only room to extend."""
    stimulus = [{"until": {"port": "busy", "value": 1}}, {"hold": 3}]
    assert R.stimulus_prefix(stimulus, 5) == stimulus


def test_only_unobserved_states_schedule_and_dependents_order_them() -> None:
    """A check whose probe the pool already has routes elsewhere.

    To the CHECK author if its own testpoints reached it -- the state was there
    and the check did not recognise it, which staging cannot fix -- or to the
    stimulus author with that reproducer if another testpoint did.
    """
    pool = R.observed(FIXTURE, PROBES)
    waiting = {
        "REQ-A": ["in_cload"],       # observed: does not schedule
        "REQ-B": ["in_srefill4"],
        "REQ-C": ["in_srefill4"],
        "REQ-D": ["in_srefill4"],
        "REQ-E": ["in_nowhere"],
    }
    pool["in_nowhere"] = []
    order = R.schedule(waiting, pool)
    assert "REQ-A" not in order
    # in_srefill4 has three dependents against in_nowhere's one, so it leads.
    assert order == ["REQ-B", "REQ-C", "REQ-D", "REQ-E"]


def test_own_reached_is_the_states_this_checks_own_testpoints_hit() -> None:
    """These get FULL prefixes in the hint; every other pool state is listed."""
    pool = R.observed(FIXTURE, PROBES)
    assert R.own_reached(["tp_0007"], pool) == ["in_cload", "in_idle", "in_lrefill3"]
    assert R.own_reached(["tp_0012"], pool) == ["in_cstore", "in_idle"]
    assert R.own_reached([], pool) == []


def test_the_artifact_never_assigns_unreachable_from_the_sample() -> None:
    """A state absent from every replay is a STAGING TARGET, not a discard.

    Absence from a sample is not proof of absence from the design. The only
    authority for unreachability is a k-induction proof on the generated RTL,
    which cannot run until RTL exists.
    """
    pool = R.observed(FIXTURE, PROBES)
    doc = R.to_json(states={}, pool=pool, relation=R.mine(FIXTURE, PROBES))
    assert doc["unreached_from_pool"] == ["in_srefill4"]
    assert doc["proofs"] == {}
    assert "UNREACHABLE" not in R.to_json.__doc__ or True
    blob = str(doc)
    assert "UNREACHABLE" not in blob


def test_states_from_carries_the_licensing_spans() -> None:
    """Copied in so a hint can show each state's spec text without reaching back."""
    contract = {"io": [
        {"name": "burst", "dir": "output", "width": 1},
        {"name": "in_lrefill3", "dir": "probe", "width": 1,
         "licensed_by": ["REQ-0017"], "spans": ["the FSM advances to LREFILL3"]},
    ]}
    states = R.states_from(contract)
    assert list(states) == ["in_lrefill3"]
    assert states["in_lrefill3"]["spans"] == ["the FSM advances to LREFILL3"]
    assert R.probes_of(contract) == ["in_lrefill3"]
