""".env.local must actually reach the HTTP client.

`ApiPort.config()` applies `.env.local`'s overrides, builds the config, then puts
the environment back in a `finally`. `_client()` read `OPENAI_MAX_RETRIES` and
`OPENAI_TIMEOUT_S` from `os.environ` *after* that restore, so neither could ever
be set from `.env.local`: a file declaring `OPENAI_MAX_RETRIES=2` still built a
client with 8.

That is expensive rather than cosmetic. A request that cannot survive the
network path is retried by the SDK at every attempt, so eight attempts at the
observed ~300s ceiling is ~40 minutes of silence -- the failure
`docs/specflow-migration.md` records as fixed by exactly this setting. It was
fixed only for `benchmarks/run_chipverilog.py`, which happens to update
`os.environ` permanently before any port exists.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import specflow.model_io as mio
from specflow.model_io import ApiPort


@pytest.fixture
def _env(monkeypatch):
    """No ambient values, so the test cannot pass by accident."""
    for k in ("OPENAI_MAX_RETRIES", "OPENAI_TIMEOUT_S", "OPENAI_API_KEY",
              "OPENAI_BASE_URL", "OPENAI_MODEL"):
        monkeypatch.delenv(k, raising=False)


def _port(monkeypatch, overrides: dict) -> ApiPort:
    monkeypatch.setattr(mio, "load_env_file", lambda *a, **k: overrides)
    return ApiPort(root=Path("/tmp"))


def test_env_file_values_reach_the_client(_env, monkeypatch):
    port = _port(monkeypatch, {
        "OPENAI_API_KEY": "k", "OPENAI_MAX_RETRIES": "2", "OPENAI_TIMEOUT_S": "123",
    })
    port.config()
    assert port._client_kwargs == {"max_retries": 2, "timeout": 123.0}


def test_defaults_apply_when_the_env_file_is_silent(_env, monkeypatch):
    port = _port(monkeypatch, {"OPENAI_API_KEY": "k"})
    port.config()
    assert port._client_kwargs == {"max_retries": 8, "timeout": 600.0}


def test_the_override_window_is_still_closed_afterwards(_env, monkeypatch):
    """The restore must survive the fix -- the values are captured, not leaked."""
    import os
    port = _port(monkeypatch, {"OPENAI_API_KEY": "k", "OPENAI_MAX_RETRIES": "2"})
    port.config()
    assert os.environ.get("OPENAI_MAX_RETRIES") is None
    assert port._client_kwargs["max_retries"] == 2


def test_client_kwargs_are_read_from_the_port_not_the_environment(_env, monkeypatch):
    """Pins the actual regression: `_client` must not re-read `os.environ`.

    Setting a hostile value in the environment after `config()` must not change
    what the client is built with.
    """
    import inspect
    src = inspect.getsource(ApiPort._client)
    assert "os.environ" not in src, (
        "_client() must use the kwargs resolved inside config()'s override "
        "window; reading os.environ here is the bug this test exists for"
    )
