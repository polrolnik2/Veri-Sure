"""A 404 from the gateway must say which of the two things went wrong.

Both causes read identically in the SDK's exception, and both kill a run the
same way. Measured in this repo: `OPENAI_BASE_URL` was set to the gateway root
with no path, so every request landed on `/chat/completions` and 404'd where the
gateway serves at `/v1`; and separately the configured model had been withdrawn
from that gateway while the URL was fine. Distinguishing them is one `curl`
nobody thinks to make until they have lost an afternoon.
"""

from __future__ import annotations

import pytest

from specflow.model_io import ApiPort


class _NotFound(Exception):
    pass


_NotFound.__name__ = "NotFoundError"


class _Boom:
    """A client whose every completion 404s."""

    class chat:  # noqa: N801
        class completions:  # noqa: N801
            @staticmethod
            def create(**_):
                raise _NotFound("Error code: 404")


class _Cfg:
    def __init__(self, base_url):
        self.base_url = base_url
        self.model = "openai/gone-5"
        self.reasoning_effort = "high"
        self.max_tokens = 1000
        self.stream = False
        self.generate_kwargs = {}


def _port(tmp_path, base_url):
    port = ApiPort(root=tmp_path, _config=_Cfg(base_url))
    port._client = lambda: _Boom()  # noqa: SLF001
    return port


def test_a_pathless_base_url_is_named_as_the_likely_cause(tmp_path):
    port = _port(tmp_path, "https://llm.example.cloud")
    with pytest.raises(RuntimeError) as exc:
        port.complete(stage="s1", round_=0, prompt="hello")
    message = str(exc.value)
    assert "has no path" in message and "<base>/v1" in message
    assert "openai/gone-5" in message
    assert "/v1/models" in message, "the message must say how to check"


def test_a_base_url_that_already_has_a_path_does_not_get_that_hint(tmp_path):
    """Then the model is the likely cause, and guessing the URL would mislead."""
    port = _port(tmp_path, "https://llm.example.cloud/v1")
    with pytest.raises(RuntimeError) as exc:
        port.complete(stage="s1", round_=0, prompt="hello")
    message = str(exc.value)
    assert "has no path" not in message
    assert "is not available on it" in message
