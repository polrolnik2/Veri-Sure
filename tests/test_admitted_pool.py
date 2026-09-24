"""The POOL the pipeline can ship, instead of one body per requirement.

The stage accepts one body per requirement and retains the rest, and until
`scorecard.score` stopped keying by `req_uid` the rest could not be scored at all
-- `POOL.md` records that limit. `admitted_pool` is what makes the plan's "fill the
pool, then select" expressible by the pipeline rather than reconstructed by a
driver.

Measured on `full2` against golden under the corpus's own stimulus: 122 bodies give
span 0.9737 / blindness 0.1416, and 333 give span 0.9737 / blindness 0.0526. Span
does not move because a second body for an already-covered requirement covers no
new requirement.
"""

from specflow.oracles_stage import CorpusBody, OracleSet, admitted_pool
from specflow.refmodel.oracles import RequirementOracle

CONTRACT = {"io": [{"name": "clk", "dir": "input", "width": 1},
                   {"name": "q", "dir": "output", "width": 1}]}
PLAN = [{"uid": "TP-0000", "req_uid": "REQ-0001"}]

GOOD = ("def decide(trace):\n"
        "    for row in trace:\n"
        "        if row['outputs']['q'] != 1:\n"
        "            return (False, row['edge'], 'q was not 1')\n"
        "    return (True, None, 'ok')\n")
ALSO_GOOD = ("def decide(trace):\n"
             "    bad = [r for r in trace if r['outputs']['q'] == 0]\n"
             "    if bad:\n"
             "        return (False, bad[0]['edge'], 'q low')\n"
             "    return (True, None, 'ok')\n")
#: Builds its own window by indexing the trace -- outside the reach of `extent`,
#: `governed`, `body` and every future correction to them.
HAND_ROLLED = ("def decide(trace):\n"
               "    for k in range(0, len(trace)):\n"
               "        if trace[k]['outputs']['q'] != 1:\n"
               "            return (False, k, 'q was not 1')\n"
               "    return (True, None, 'ok')\n")
MALFORMED = "def decide(trace):\n    return this_name_does_not_exist\n"


def _set(bodies):
    trusted = [RequirementOracle(req_uid="REQ-0001", tp_uids=["TP-0000"],
                                 clause="c", source=GOOD)]
    return OracleSet(trusted=trusted, corpus={"REQ-0001": [
        CorpusBody(req_uid="REQ-0001", source=src, arm="generate", round_=0)
        for src in bodies]})


def test_the_pool_CONTAINS_the_accepted_body_and_the_corpus_alternatives():
    pool = admitted_pool(_set([GOOD, ALSO_GOOD]), CONTRACT, PLAN)
    assert [o.source for o in pool] == [GOOD, ALSO_GOOD], (
        "the accepted body must come first and the alternative must be admitted")
    assert all(o.req_uid == "REQ-0001" for o in pool)
    assert all(list(o.tp_uids) == ["TP-0000"] for o in pool), (
        "an admitted body inherits the accepted body's testpoints -- it has none "
        "of its own, and inventing them would decide where a check applies")


def test_the_accepted_body_is_not_duplicated_by_its_own_corpus_entry():
    """`_retain` records the survivor too, with `frozen=True`. Admitting it again
    would double every requirement's contribution to blindness."""
    pool = admitted_pool(_set([GOOD]), CONTRACT, PLAN)
    assert len(pool) == 1 and pool[0].source == GOOD


def test_a_MALFORMED_corpus_body_is_refused():
    pool = admitted_pool(_set([MALFORMED, ALSO_GOOD]), CONTRACT, PLAN)
    assert [o.source for o in pool] == [GOOD, ALSO_GOOD]


def test_a_HAND_ROLLED_corpus_body_is_refused_by_default():
    """Refused on window semantics, not on what it convicts: such a body is
    outside the reach of every window guarantee the temporal module offers, and
    the census is 29 of 241 bodies with 26 convicting nothing."""
    pool = admitted_pool(_set([HAND_ROLLED, ALSO_GOOD]), CONTRACT, PLAN)
    assert [o.source for o in pool] == [GOOD, ALSO_GOOD]
    kept = admitted_pool(_set([HAND_ROLLED]), CONTRACT, PLAN,
                         refuse_hand_rolled=False)
    assert [o.source for o in kept] == [GOOD, HAND_ROLLED], (
        "the switch must actually gate it, or the default is untested")


def test_an_ACCEPTED_hand_rolled_body_is_passed_through():
    """**ADMISSION ONLY.** The accepted set was frozen before the detector
    existed, and dropping a body with no replacement costs its requirement's span
    outright -- so the refusal applies to corpus bodies and never to `trusted`.
    """
    trusted = [RequirementOracle(req_uid="REQ-0001", tp_uids=["TP-0000"],
                                 clause="c", source=HAND_ROLLED)]
    pool = admitted_pool(OracleSet(trusted=trusted, corpus={}), CONTRACT, PLAN)
    assert [o.source for o in pool] == [HAND_ROLLED]


def test_a_requirement_with_no_ACCEPTED_body_contributes_nothing():
    """It has no `tp_uids` to give a corpus body, and inventing them would be this
    function deciding where a check applies."""
    pool = admitted_pool(
        OracleSet(trusted=[], corpus={"REQ-0002": [
            CorpusBody(req_uid="REQ-0002", source=ALSO_GOOD, arm="generate",
                       round_=0)]}),
        CONTRACT, PLAN)
    assert pool == []


def test_the_pool_of_an_EMPTY_corpus_is_exactly_trusted():
    """A run that did not retain reads as "not retained", never as "one body"."""
    trusted = [RequirementOracle(req_uid="REQ-0001", tp_uids=["TP-0000"],
                                 clause="c", source=GOOD)]
    pool = admitted_pool(OracleSet(trusted=trusted, corpus={}), CONTRACT, PLAN)
    assert [o.source for o in pool] == [GOOD]


# ------------------------------------------- the pipeline's own call site


def test_build_artifacts_takes_admit_pool_and_defaults_it_OFF():
    """**A SOURCE-LEVEL PIN, AND THAT IS DELIBERATE.**

    A call site inside `build_artifacts` "has twice been deleted on this branch
    without failing a single behavioural test" -- `integration.py` says so about
    another one. So this asserts the parameter reaches
    `oracles_stage.admitted_pool` in the source, not merely that the keyword
    exists.

    OFF by default: every recorded figure on this branch was computed over one
    body per requirement, and switching this on silently would change what
    `blindness` NAMES in all of them rather than extending it.
    """
    import inspect
    import re

    from specflow import integration

    sig = inspect.signature(integration.build_artifacts)
    assert "admit_pool" in sig.parameters
    assert sig.parameters["admit_pool"].default is False, (
        "on by default would retroactively change what every recorded blindness "
        "figure on this branch means")

    src = inspect.getsource(integration.build_artifacts)
    call = re.search(r"card = _scorecard\.score\((.*?)\n        \)", src, re.S)
    assert call, "cannot find the scorecard.score call"
    assert "admitted_pool" in src, (
        "admit_pool is accepted and never reaches oracles_stage.admitted_pool, "
        "so the pool cannot be scored however the caller sets it")
    #: The conditional spans three lines AND contains parenthesised calls, so a
    #: non-greedy match to the first `)` or the first newline stops inside it.
    #: Two earlier versions of this did exactly that and failed on correct code,
    #: which was the test being wrong rather than the source. Bounded on the
    #: statement that follows instead.
    chooser = re.search(r"_scored = \((.*?)\n        if ", src, re.S)
    assert chooser, "cannot find the statement choosing the scored set"
    assert "admit_pool" in chooser.group(1), (
        "the set handed to the scorecard must be chosen BY admit_pool; found: "
        + " ".join(chooser.group(1).split())[:160])
    assert "trusted" in chooser.group(1), (
        "and it must fall back to oracle_set.trusted when admit_pool is off")
    assert "oracles=[" in call.group(1) and "_scored" in call.group(1), (
        "the scorecard must score the chosen set, not oracle_set.trusted "
        "directly -- otherwise the parameter is inert")
