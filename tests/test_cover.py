"""`specflow.cover` -- the shipped set is the cover of the pool."""
import inspect

from specflow import cover
from specflow import integration


def _cover(sep, req, conv=None):
    return cover.greedy_cover(list(sep), {k: frozenset(v) for k, v in sep.items()},
                              req, conv or {})


def test_the_cover_keeps_every_separated_cell_and_drops_the_redundant():
    """C is a subset of A∪B, so it separates nothing new and is dropped."""
    sep = {"A": {1, 2, 3}, "B": {4, 5}, "C": {2, 4}}
    req = {"A": "R1", "B": "R2", "C": "R1"}
    kept, greedy = _cover(sep, req)
    assert kept == ["A", "B"] and greedy == 2
    assert set().union(*(sep[k] for k in kept)) == {1, 2, 3, 4, 5}


def test_greedy_takes_the_largest_gain_not_the_first_body():
    """A body earlier in pool order loses to one separating strictly more."""
    sep = {"A": {1}, "B": {1, 2, 3}, "C": {4}}
    req = {"A": "R1", "B": "R2", "C": "R3"}
    kept, greedy = _cover(sep, req)
    assert kept[:greedy] == ["B", "C"]


def test_ties_go_to_pool_order_so_a_run_always_ships_the_same_set():
    sep = {"A": {1, 2}, "B": {1, 2}}
    req = {"A": "R1", "B": "R1"}
    assert _cover(sep, req)[0] == ["A"]
    assert cover.greedy_cover(["B", "A"], {k: frozenset(v) for k, v in sep.items()},
                              req, {})[0] == ["B"]


def test_the_floor_gives_an_emptied_requirement_its_best_body_back():
    """R2's bodies are all redundant; span needs one of them. The floor takes the
    one separating the most, and among equals the one convicting fewest designs
    -- never a body separating less to save a conviction."""
    sep = {"A": {1, 2, 3}, "B": {1}, "C": {1}, "D": set()}
    req = {"A": "R1", "B": "R2", "C": "R2", "D": "R3"}
    kept, greedy = _cover(sep, req, conv={"B": 3, "C": 1, "D": 0})
    assert greedy == 1
    assert kept == ["A", "C", "D"]
    assert {req[k] for k in kept} == {"R1", "R2", "R3"}


def test_nothing_separated_ships_one_body_per_requirement():
    sep = {"A": set(), "B": set(), "C": set()}
    req = {"A": "R1", "B": "R1", "C": "R2"}
    kept, greedy = _cover(sep, req)
    assert greedy == 0 and kept == ["A", "C"]


def test_select_with_no_population_ships_nothing_rather_than_guessing():
    assert cover.select({}, {}, [], {"io": []}, {}, base="") is None


def test_build_artifacts_wires_the_cover_into_what_it_scores():
    """SOURCE-LEVEL PIN. A call site inside `build_artifacts` has been deleted on
    this branch without failing a behavioural test more than once; the scorecard
    must score what `_ship_cover` returned, and a stale `shipped.json` must be
    removed before a re-entry decides whether to write one."""
    src = inspect.getsource(integration.build_artifacts)
    unlink = src.index("_shipped_path.unlink(missing_ok=True)")
    ship = src.index("_scored = _ship_cover(")
    score = src.index("card = _scorecard.score(")
    assert unlink < ship < score
    assert "for o in _scored]" in src[score:score + 400]
    assert "ship_cover and admit_pool" in src[unlink:ship]


def test_a_transport_failure_in_normalize_stops_the_build():
    """A 429 that exhausted normalize's retries used to leave the run planning
    S2 with NO normalized forms, and its records were replayed by resume."""
    import openai

    from specflow.integration import _transport_failure
    from specflow.model_io import NoChoicesError

    assert _transport_failure(NoChoicesError("x", body={"code": 429}))
    wrapped = RuntimeError("fan-out item failed")
    wrapped.__cause__ = NoChoicesError("x")
    assert _transport_failure(wrapped)
    import httpx
    assert _transport_failure(openai.APIConnectionError(
        request=httpx.Request("POST", "https://x")))
    #: A content failure keeps the old behaviour: the run continues.
    assert not _transport_failure(ValueError("could not parse the form"))
    assert not _transport_failure(KeyError("observable"))
    src = inspect.getsource(integration.build_artifacts)
    at = src.index('logger.warning("normalize: not produced (%r)", exc)')
    assert "if _transport_failure(exc):" in src[at - 900:at]
    #: The same rule at every stage that swallowed a failure as a warning.
    for marker in ('"probes: interrupted by a transport failure',
                   '"stimulus: interrupted by a transport failure',
                   '"oracles: interrupted by a transport failure'):
        assert marker in src, marker
