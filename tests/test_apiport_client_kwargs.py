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


def test_the_retry_switch_reaches_the_client(_env, monkeypatch):
    """Retries and timeout are SWITCHES now, not env-file entries.

    They were env-file entries because that was the only channel that worked at
    the time. The channel was the bug: a value read from the environment is
    settled by whichever file a callee re-reads, not by the caller.
    """
    from specflow.model_io import PortSettings

    port = _port(monkeypatch, {"OPENAI_API_KEY": "k"})
    port = ApiPort(root=port.root,
                   settings=PortSettings(max_retries=2, timeout_s=123.0))
    monkeypatch.setattr(mio, "load_env_file", lambda *a, **k: {"OPENAI_API_KEY": "k"})
    port.config()
    assert port._client_kwargs == {"max_retries": 2, "timeout": 123.0}


def test_the_default_retry_count_is_two_not_eight(_env, monkeypatch):
    """The incident that made this configurable, preserved in the default.

    A request the gateway structurally cannot complete costs `max_retries` x
    ~300s of silence. Eight of those is ~40 minutes with nothing written. That
    used to be recoverable only by putting `OPENAI_MAX_RETRIES` in the env file
    -- the exact ambient-knob pattern now removed -- so the lesson has to live
    in the default instead of in a file somebody remembers to write.
    """
    port = _port(monkeypatch, {"OPENAI_API_KEY": "k"})
    port.config()
    assert port._client_kwargs == {"max_retries": 2, "timeout": 600.0}


def test_the_environment_cannot_set_the_retry_count(_env, monkeypatch):
    """A hostile ambient value must be inert."""
    import os
    monkeypatch.setenv("OPENAI_MAX_RETRIES", "8")
    port = _port(monkeypatch, {"OPENAI_API_KEY": "k", "OPENAI_MAX_RETRIES": "8"})
    port.config()
    assert port._client_kwargs["max_retries"] == 2
    assert os.environ.get("OPENAI_MAX_RETRIES") == "8", (
        "the override window still restores what it borrowed"
    )


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


def test_the_runner_does_not_reinstate_the_retry_storm():
    """`PortSettings.max_retries = 2` fixed a measured incident: a request this
    gateway cannot complete costs `max_retries` x ~300s of silence, and the SDK's
    8 is ~40 minutes with nothing written.

    `run_chipverilog` passes `--api-max-retries` unconditionally, so its CLI
    default is what actually runs -- and it said 8, restoring precisely the
    behaviour the dataclass had removed. Found by auditing every PortSettings
    field the runner overrides, after `max_output_tokens` turned out to be dead
    the same way and cost a two-hour run.

    Pins the RUNNER's number against the dataclass's, which is the comparison
    that matters.
    """
    import re
    from pathlib import Path

    from specflow.model_io import PortSettings

    src = Path("benchmarks/run_chipverilog.py").read_text()
    m = re.search(r'"--api-max-retries", type=int, default=(\d+)', src)
    assert m, "could not find the --api-max-retries default"
    assert int(m.group(1)) == PortSettings().max_retries, (
        "the runner's retry default must not disagree with PortSettings -- a "
        "disagreement means the dataclass value is dead in every real run")
