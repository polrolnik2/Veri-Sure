"""Which stage gets which model is a RUNTIME SWITCH, not an ambient variable.

Two failures produced this file, and both were invisible while the answer came
from the environment.

The first: `SPECFLOW_SMALL_MODEL` was attached to the single port a whole run
shares, and `config()` cached its resolved result, so whichever stage ran first
froze the model for every stage after it. `classify` runs first, so the small
model captured everything -- including the reference model. Measured on a live
run: the operator had configured `gpt-5.6-luna` at `xhigh` and every artifact,
reference model included, was written by `gpt-5-mini` at `low`, with nothing
reporting it.

The second: `load_env_file` values OVERRIDE `os.environ` by design, so a rotated
key can reach a running session. That makes any knob ALSO read from the
environment decided by whichever file the callee happens to load rather than by
what the caller asked for -- a run launched with `--env-file env.high` did its
reference-model generation at `xhigh`.

So the switches are passed in. A caller states them once and no callee can
quietly disagree.
"""

from __future__ import annotations

import pytest

from specflow.model_io import PortSettings, make_port

SMALL = PortSettings(small_model="small-model", small_effort="low")


@pytest.fixture
def _env(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_MODEL", "big-model")
    monkeypatch.setenv("OPENAI_REASONING_EFFORT", "xhigh")
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    monkeypatch.setenv("SPECFLOW_ENV_FILE", str(tmp_path / "absent.env"))
    # Present on purpose: the ambient variables must no longer decide anything.
    monkeypatch.setenv("SPECFLOW_SMALL_MODEL", "ambient-model")
    monkeypatch.setenv("SPECFLOW_SMALL_EFFORT", "ambient-effort")
    return tmp_path


def test_the_reference_model_stage_keeps_the_configured_model(_env):
    cfg = make_port("api", _env, settings=SMALL).config("refmodel")
    assert (cfg.model, cfg.reasoning_effort) == ("big-model", "xhigh")


def test_the_narrow_fanned_out_stages_get_the_small_one(_env):
    port = make_port("api", _env, settings=SMALL)
    for stage in ("classify", "s2", "s3", "judge", "stimulus"):
        cfg = port.config(stage)
        assert (cfg.model, cfg.reasoning_effort) == ("small-model", "low"), stage


def test_ambient_environment_no_longer_decides(_env):
    """`SPECFLOW_SMALL_MODEL` is set in the environment and must be ignored."""
    port = make_port("api", _env, settings=PortSettings())
    assert port.config("classify").model == "big-model"


def test_call_order_does_not_decide_the_model(_env):
    """The original defect: the first stage to resolve froze the choice for all."""
    port = make_port("api", _env, settings=SMALL)
    port.config("classify")
    assert port.config("refmodel").model == "big-model"

    other = make_port("api", _env, settings=SMALL)
    other.config("refmodel")
    assert other.config("classify").model == "small-model"


def test_the_protected_set_is_a_switch(_env):
    settings = PortSettings(small_model="small-model", small_effort="low",
                            full_strength_stages=frozenset({"refmodel", "judge"}))
    port = make_port("api", _env, settings=settings)
    assert port.config("judge").model == "big-model"
    assert port.config("s3").model == "small-model"


def test_an_explicit_model_and_effort_override_everything(_env):
    """What `--model` / `--effort` must do: win over the file and the environment."""
    settings = PortSettings(model="chosen", effort="medium")
    cfg = make_port("api", _env, settings=settings).config("refmodel")
    assert (cfg.model, cfg.reasoning_effort) == ("chosen", "medium")


def test_with_no_small_model_every_stage_is_full_strength(_env):
    port = make_port("api", _env, settings=PortSettings())
    for stage in ("classify", "refmodel", "s3"):
        assert port.config(stage).model == "big-model", stage


# ------------------------------------------------- the switches reach the port


def test_every_switch_is_reachable_from_the_command_line():
    """A knob that only exists in Python is not a runtime switch.

    Each of these was an environment variable, and each was therefore settled by
    whichever file a callee happened to re-read rather than by the caller.
    """
    import argparse

    from benchmarks.run_chipverilog import build_parser  # noqa: PLC0415

    flags = {a.option_strings[0] for a in build_parser()._actions
             if isinstance(a, argparse.Action) and a.option_strings}
    for flag in ("--model", "--effort", "--api-flavor", "--stream",
                 "--small-model", "--small-effort", "--full-strength-stages",
                 "--max-output-tokens", "--responses-chunk", "--stream-retries",
                 "--api-max-retries", "--api-timeout"):
        assert flag in flags, flag


def test_the_model_call_path_reads_no_ambient_knobs():
    """`SPECFLOW_*` behaviour variables are gone from the request path.

    The env file still carries credentials -- a key is not a runtime choice, and
    the file is the one channel a live process can re-read when one rotates.
    """
    from pathlib import Path

    src = Path(__file__).resolve().parents[1] / "specflow" / "model_io.py"
    text = src.read_text(encoding="utf-8")
    banned = ("SPECFLOW_SMALL_MODEL", "SPECFLOW_SMALL_EFFORT",
              "SPECFLOW_FULL_STRENGTH_STAGES", "SPECFLOW_MAX_OUTPUT_TOKENS",
              "SPECFLOW_RESPONSES_CHUNK", "SPECFLOW_STREAM_RETRIES",
              "OPENAI_MAX_RETRIES", "OPENAI_TIMEOUT_S")
    for name in banned:
        assert f'os.environ.get("{name}"' not in text, name


def test_a_fanned_out_stage_can_be_named_full_strength():
    """Its stage name is per item, so exact membership could never match it.

    `judge_REQ-0000`, `stimulus_TP-0000`, `classify_224` -- only the monolithic
    stages (`s1`, `s2`, `s3`, `refmodel`) have a name a caller can write down.
    So `--full-strength-stages judge` matched nothing and the judge stayed on
    the small model at low effort, with no way to raise it. It returned "met"
    on 77 of 77 requirements for a model whose outputs never moved.
    """
    from specflow.model_io import PortSettings

    s = PortSettings(small_model="mini", small_effort="low",
                     full_strength_stages=frozenset({"refmodel", "judge"}))
    assert s.for_stage("judge_REQ-0000") == (None, None)
    assert s.for_stage("judge") == (None, None)
    assert s.for_stage("refmodel") == (None, None)


def test_naming_one_fanned_out_stage_does_not_promote_the_others():
    """Prefix matching must not become "anything that starts similarly"."""
    from specflow.model_io import PortSettings

    s = PortSettings(small_model="mini", small_effort="low",
                     full_strength_stages=frozenset({"judge"}))
    assert s.for_stage("stimulus_TP-0000") == ("mini", "low")
    assert s.for_stage("classify_224") == ("mini", "low")
    assert s.for_stage("s2") == ("mini", "low")
    # A stage merely sharing a prefix substring is not the named stage.
    assert s.for_stage("judgement") == ("mini", "low")


def test_no_fanned_out_stage_is_full_strength_by_default():
    """The expensive model runs whole-artifact calls, never per-item ones.

    A fan-out is 77 calls on i2c; the two stages that must not be downgraded --
    the reference model and the witness -- are ONE call each. Putting a fan-out
    prefix in `full_strength_stages` multiplies the strong model's cost by the
    requirement count silently, and `for_stage` matches by PREFIX, so a single
    careless entry captures every item of that stage. That has happened here
    before, in the other direction: `--full-strength-stages judge` silently
    matched and the whole judging pass stopped being downgraded.

    Oracle authoring quality IS a measured lever -- eleven oracles `[O]` could
    not make non-vacuous were re-authored at full strength and one of the first
    five produced a check the small model could not write. It is pulled with
    `deep_effort_stages` instead, which raises reasoning on the SAME model, so
    a 77-call fan-out never changes which model serves it.
    """
    from specflow.model_io import ApiPort, PortSettings

    FANNED_OUT = {"s2", "s3", "stimulus", "normalize", "oracle", "variant"}
    for default in (PortSettings.full_strength_stages,
                    ApiPort.__dataclass_fields__["full_strength_stages"].default):
        assert not (FANNED_OUT & set(default)), default

    settings = PortSettings(small_model="small", small_effort="low")
    for stage in ("normalize_REQ-0001", "oracle_REQ-0001",
                  "variant_REQ-0001_action", "s2_REQ-0001", "s3_TP-0001",
                  "stimulus_TP-0001"):
        assert settings.for_stage(stage)[0] == "small", stage
    for stage in ("refmodel", "witness"):
        assert settings.for_stage(stage) == (None, None), stage


def test_the_benchmark_runner_default_keeps_the_fanouts_small():
    """The switch the runs actually use, not just the library default."""
    from benchmarks.run_chipverilog import build_parser

    action = next(a for a in build_parser()._actions
                  if "--full-strength-stages" in (a.option_strings or []))
    named = {s.strip() for s in str(action.default).split(",") if s.strip()}
    assert named == {"refmodel", "witness"}
