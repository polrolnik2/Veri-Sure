"""`EDA_STREAM_RETRIES` overrides the number of resends of a dropped stream."""

import importlib


def test_the_default_is_two(monkeypatch):
    monkeypatch.delenv("EDA_STREAM_RETRIES", raising=False)
    import eda_agent.stream_policy as policy

    assert importlib.reload(policy).DEFAULT_STREAM_RETRIES == 2


def test_the_environment_overrides_it(monkeypatch):
    monkeypatch.setenv("EDA_STREAM_RETRIES", "6")
    import eda_agent.stream_policy as policy

    try:
        assert importlib.reload(policy).DEFAULT_STREAM_RETRIES == 6
    finally:
        monkeypatch.delenv("EDA_STREAM_RETRIES")
        importlib.reload(policy)
