"""ApiPort: credential resolution, recording, and the empty-completion guard.

No network anywhere. The transport is stubbed, because what needs testing is the
port's own behaviour -- which key it picks, what it writes down, and what it
refuses to pass on -- not that `openai` can make an HTTP request.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from specflow.model_io import ApiPort, load_env_file, make_port


class _Message:
    def __init__(self, content):
        self.content = content


class _Choice:
    def __init__(self, content, finish_reason="stop"):
        self.message = _Message(content)
        self.finish_reason = finish_reason


class _Usage:
    def model_dump(self):
        return {"total_tokens": 42}


class _Response:
    def __init__(self, content, finish_reason="stop"):
        self.choices = [_Choice(content, finish_reason)]
        self.model = "served/model-id"
        self.usage = _Usage()


class _Completions:
    def __init__(self, response):
        self._response = response
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self._response


class _Client:
    def __init__(self, response):
        self.chat = type("_Chat", (), {"completions": _Completions(response)})()


def _port(tmp_path: Path, response: _Response) -> tuple[ApiPort, _Client]:
    port = ApiPort(root=tmp_path / "agent_io")
    client = _Client(response)
    port._client = lambda: client  # type: ignore[method-assign]
    return port, client


# ------------------------------------------------------------------ env file


def test_env_file_overrides_the_process_environment(tmp_path, monkeypatch):
    """The direction matters: a rotated key lands in the file while the stale one
    is still in `os.environ`, which a running process cannot re-read."""
    monkeypatch.setenv("OPENAI_API_KEY", "stale-key")
    env = tmp_path / ".env.local"
    env.write_text('OPENAI_API_KEY="fresh-key"\nOPENAI_MODEL=some/model\n', encoding="utf-8")
    monkeypatch.setenv("SPECFLOW_ENV_FILE", str(env))

    values = load_env_file()
    assert values["OPENAI_API_KEY"] == "fresh-key"  # quotes stripped
    assert values["OPENAI_MODEL"] == "some/model"

    cfg = ApiPort(root=tmp_path).config()
    assert cfg.api_key == "fresh-key"
    assert cfg.model == "some/model"
    # And the override is scoped to resolution -- it must not leak into the
    # process environment, where it would silently reconfigure everything else.
    import os

    assert os.environ["OPENAI_API_KEY"] == "stale-key"


def test_comments_and_blank_lines_are_ignored(tmp_path, monkeypatch):
    env = tmp_path / "creds"
    env.write_text("# a comment\n\nOPENAI_API_KEY=k\nnot-a-pair\n", encoding="utf-8")
    monkeypatch.setenv("SPECFLOW_ENV_FILE", str(env))
    assert load_env_file() == {"OPENAI_API_KEY": "k"}


def test_a_missing_key_is_a_clear_error_not_an_auth_failure(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("SPECFLOW_ENV_FILE", str(tmp_path / "absent"))
    with pytest.raises(RuntimeError, match="no API key"):
        ApiPort(root=tmp_path).config()


# --------------------------------------------------------------- the call


def test_the_configured_effort_reaches_the_request(tmp_path, monkeypatch):
    """The operator sets reasoning effort in OPENAI_EXTRA_BODY; it has to arrive
    at the wire, not be dropped between config and client."""
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    monkeypatch.setenv("OPENAI_MODEL", "openai/gpt-5.6-luna")
    monkeypatch.setenv(
        "OPENAI_EXTRA_BODY", '{"reasoning": {"effort": "xhigh"}, "max_tokens": 32000}'
    )
    monkeypatch.setenv("SPECFLOW_ENV_FILE", str(tmp_path / "absent"))

    port, client = _port(tmp_path, _Response('{"ok": true}'))
    assert port.complete(stage="s1", round_=0, prompt="a prompt") == '{"ok": true}'

    (call,) = client.chat.completions.calls
    assert call["model"] == "openai/gpt-5.6-luna"
    assert call["extra_body"]["reasoning"]["effort"] == "xhigh"
    assert call["messages"] == [{"role": "user", "content": "a prompt"}]


def test_reasoning_effort_is_settable_from_the_environment(tmp_path, monkeypatch):
    """`reasoning_effort` is a named chat-completions parameter, and it was the
    one config field with no environment path -- so an operator who set an effort
    in the environment had it silently dropped.

    The distinction from the test above is not cosmetic. `{"reasoning":
    {"effort": ...}}` is the Responses-API shape; a chat-completions endpoint
    rejects it outright with `unknown_parameter`, which is how this was found.
    """
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-5.6-luna")
    monkeypatch.setenv("OPENAI_REASONING_EFFORT", "xhigh")
    monkeypatch.delenv("OPENAI_EXTRA_BODY", raising=False)
    monkeypatch.setenv("SPECFLOW_ENV_FILE", str(tmp_path / "absent"))

    port, client = _port(tmp_path, _Response("ok"))
    port.complete(stage="s1", round_=0, prompt="a prompt")

    (call,) = client.chat.completions.calls
    assert call["reasoning_effort"] == "xhigh"
    # Top-level, not smuggled through extra_body.
    assert "extra_body" not in call


def test_an_explicit_argument_still_beats_the_environment(tmp_path, monkeypatch):
    """Env resolution must fill in behind an explicit caller, not over it --
    otherwise a per-node effort override becomes unexpressible."""
    from eda_agent.config import load_openai_config

    monkeypatch.setenv("OPENAI_REASONING_EFFORT", "xhigh")
    assert load_openai_config().reasoning_effort == "xhigh"
    assert load_openai_config(reasoning_effort="low").reasoning_effort == "low"


def test_an_api_run_records_a_replayable_fixture(tmp_path, monkeypatch):
    """One paid run has to become a free deterministic one. ApiPort writes into
    the layout ReplayPort reads, so the same round replays without a model."""
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    monkeypatch.setenv("SPECFLOW_ENV_FILE", str(tmp_path / "absent"))
    monkeypatch.delenv("OPENAI_EXTRA_BODY", raising=False)

    port, _ = _port(tmp_path, _Response("the reply"))
    port.complete(stage="s2", round_=1, prompt="the prompt")

    root = tmp_path / "agent_io"
    assert (root / "s2_r1_prompt.txt").read_text(encoding="utf-8") == "the prompt"
    replay = make_port("replay", root)
    assert replay.complete(stage="s2", round_=1, prompt="ignored") == "the reply"

    meta = json.loads((root / "s2_r1_meta.json").read_text(encoding="utf-8"))
    assert meta["port"] == "api"
    assert meta["served_model"] == "served/model-id"
    assert meta["usage"] == {"total_tokens": 42}


def test_an_empty_completion_is_refused_rather_than_parsed(tmp_path, monkeypatch):
    """A reasoning model that spends its whole budget before emitting content
    returns exactly this. Passing it on would produce a gate report blaming the
    decomposition for what is a token-budget problem."""
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    monkeypatch.setenv("SPECFLOW_ENV_FILE", str(tmp_path / "absent"))

    port, _ = _port(tmp_path, _Response("", finish_reason="length"))
    with pytest.raises(RuntimeError, match="no content"):
        port.complete(stage="s1", round_=0, prompt="p")
    # And nothing was recorded, so a later replay cannot serve the empty string.
    assert not (tmp_path / "agent_io" / "s1_r0_response.txt").exists()


def test_make_port_returns_a_usable_api_port(tmp_path):
    assert isinstance(make_port("api", tmp_path), ApiPort)
