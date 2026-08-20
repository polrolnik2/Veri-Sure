"""`SPECFLOW_SMALL_MODEL` must not capture the reference model.

The docstring on `ApiPort.model_override` has always said the small model is for
"the fanned-out stages ... while the whole-artifact stages keep the configured
one". The code did not do that. `make_port` attaches the override to the single
port the entire run shares, and `config()` cached its result on first call — so
whichever stage ran first froze its model choice for every stage after it.
`classify` runs first, so the small model captured everything.

Measured on a live `alu` run: the operator had configured `gpt-5.6-luna` at
`xhigh`, and every artifact in the run — including the reference model — was
written by `gpt-5-mini` at `low`. Nothing reported it. The artifacts looked
plausible, the gates passed and the node accepted, so the only way to notice was
to read the per-call provenance records afterwards.

The reference model is the artifact the whole pipeline's correctness rests on:
every check compares the DUT against it, and this session spent its length
proving how much a wrong one costs. It is the last thing that should be silently
downgraded to save tokens.
"""

from __future__ import annotations


import pytest

from specflow.model_io import make_port


@pytest.fixture
def _env(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_MODEL", "big-model")
    monkeypatch.setenv("OPENAI_REASONING_EFFORT", "xhigh")
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    monkeypatch.setenv("SPECFLOW_SMALL_MODEL", "small-model")
    monkeypatch.setenv("SPECFLOW_SMALL_EFFORT", "low")
    monkeypatch.setenv("SPECFLOW_ENV_FILE", str(tmp_path / "absent.env"))
    return tmp_path


def test_the_reference_model_stage_keeps_the_configured_model(_env):
    port = make_port("api", _env)
    cfg = port.config("refmodel")
    assert (cfg.model, cfg.reasoning_effort) == ("big-model", "xhigh")


def test_the_narrow_fanned_out_stages_still_get_the_small_one(_env):
    port = make_port("api", _env)
    for stage in ("classify", "s2", "s3", "judge", "stimulus"):
        cfg = port.config(stage)
        assert (cfg.model, cfg.reasoning_effort) == ("small-model", "low"), stage


def test_call_order_does_not_decide_the_model(_env):
    """The actual defect: the first stage to resolve froze the choice for all.

    `classify` runs before `refmodel` in every real run, so this ordering is the
    one that happened — and asking for `refmodel` first must not change the
    answer either.
    """
    port = make_port("api", _env)
    port.config("classify")
    assert port.config("refmodel").model == "big-model"

    other = make_port("api", _env)
    other.config("refmodel")
    assert other.config("classify").model == "small-model"


def test_the_exclusion_set_is_configurable(monkeypatch, _env):
    monkeypatch.setenv("SPECFLOW_FULL_STRENGTH_STAGES", "refmodel,judge")
    port = make_port("api", _env)
    assert port.config("judge").model == "big-model"
    assert port.config("s3").model == "small-model"


def test_with_no_small_model_configured_every_stage_is_full_strength(monkeypatch, _env):
    monkeypatch.delenv("SPECFLOW_SMALL_MODEL")
    monkeypatch.delenv("SPECFLOW_SMALL_EFFORT")
    port = make_port("api", _env)
    for stage in ("classify", "refmodel", "s3"):
        assert port.config(stage).model == "big-model", stage
