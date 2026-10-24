"""A body a strict majority of the spec-derived population convicts does not
ship, and the cell leg reads blindness by that same rule."""

import inspect

from specflow import variety


def test_a_strict_majority_of_the_POPULATION_not_of_the_deciders():
    seven = [str(i) for i in range(7)]

    def per(fails, decides=7):
        return {d: (False if i < fails else (True if i < decides else None))
                for i, d in enumerate(seven)}

    got = variety.convicted_by_a_majority({
        "four": per(4), "three": per(3), "all": per(7),
        #: Decides on two designs and convicts both: unanimous among the
        #: deciders, but two of seven is not a majority of the population.
        "two_of_two": per(2, decides=2),
    })
    assert got == ("all", "four")


def test_majority_contains_unanimous_where_every_design_decides():
    v = {"u": {"a": False, "b": False, "c": False},
         "m": {"a": False, "b": False, "c": True},
         "ok": {"a": True, "b": False, "c": True}}
    assert set(variety.refuted_by_the_population(v)) == {"u"}
    assert set(variety.convicted_by_a_majority(v)) == {"u", "m"}


def test_the_cell_leg_reads_blindness_by_the_shipping_rule(monkeypatch):
    """R1 alone separates `a` from `b` at TP-1 and convicts two of three
    designs overall: not refuted by all of them, refuted by a majority. A run
    that ships by the majority rule will not ship R1, so the cell is blind to
    it and must be a target; under the unanimous rule it is closed."""
    from specflow import oracles_stage as O

    rows = {d: {"TP-1": [{"inputs": {}, "outputs": {"p": v}}]}
            for d, v in (("a", 0), ("b", 1), ("c", 1))}
    monkeypatch.setattr(O, "_population_rows", lambda *a, **k: rows)
    monkeypatch.setattr(O, "_population_verdicts_by_tp", lambda *a, **k: {
        "R1": {"TP-1": {"a": True, "b": False, "c": None}}})
    monkeypatch.setattr(O, "_population_verdicts", lambda *a, **k: {
        "R1": {"a": True, "b": False, "c": False}})
    kw = dict(population=("a", "b", "c"), held={"R1": object()},
              contract={"io": [{"name": "p", "dir": "output"}]},
              stimulus_by_tp={"TP-1": [{}]},
              testplan=[{"uid": "TP-1", "covers": ["R2@1"]}],
              by_uid={"R2": {"uid": "R2", "text": "t"}},
              normalized={"R2": {"observable": ["p"]}},
              budget=4, base="", transactional=True, ignore_refuted=True)
    unanimous, _ = O._cell_targets(**kw)
    majority, _ = O._cell_targets(**kw, majority=True)
    assert {t["cell"].pair for t in unanimous} == {("a", "c")}
    assert {t["cell"].pair for t in majority} >= {("a", "b")}


def test_the_majority_rule_is_wired_end_to_end():
    """Source pins: a call site inside `run_oracle_stage` has been deleted on
    this branch without failing a behavioural test."""
    from specflow import cover, integration, oracles_stage

    sig = inspect.signature(integration.build_artifacts).parameters
    assert sig["refute_majority"].default is True
    build = inspect.getsource(integration.build_artifacts)
    assert "refuted_majority=refute_majority," in build
    assert "majority=refute_majority) or _scored" in build
    assert "exclude_refuted=exclude_refuted, majority=majority)" in inspect.getsource(
        integration._ship_cover)
    assert ("V.convicted_by_a_majority if majority else V.refuted_by_the_population"
            in inspect.getsource(cover.select))
    stage = inspect.getsource(oracles_stage.run_oracle_stage)
    assert "majority=refuted_majority)" in stage
    assert "majority=bool(refuted_excluded and refuted_majority))" in stage
