"""A resend-able failure must be resent. A 30-minute generation depends on it.

The i2c reference model at `xhigh` is roughly half an hour of work, spread over
several continuation chunks. One run lost all of it on the second chunk to a
gateway 500 whose own message read "You can retry your request" -- because the
retry set was a list of transport-error class NAMES, and the SDK reports a
mid-stream server error as a bare `APIError` with no `status_code` to read.

So the classification is by "could a resend fix this", not by exception type,
and it is deliberately biased towards retrying: a wrong guess that way costs one
wasted resend, and a wrong guess the other way costs the whole generation.
"""

from __future__ import annotations

import httpx
import openai
import pytest

from specflow.model_io import ApiPort, PortSettings, _retryable


def _request() -> httpx.Request:
    return httpx.Request("POST", "http://gateway.invalid/v1/responses")


def _status(cls, code: int):
    return cls("boom", response=httpx.Response(code, request=_request()), body=None)


class TestRetryable:
    def test_a_bare_apierror_from_a_stream_error_event_is_retried(self):
        """The regression. The SDK raises a bare `APIError` -- NOT an
        `APIStatusError` -- when the SSE carries an error event, so there is no
        status code, and matching on the class name filed a transient 500 with
        the permanent failures."""
        exc = openai.APIError(
            "The server had an error processing your request. Sorry about that! "
            "You can retry your request",
            request=_request(), body={"code": "server_error"},
        )
        assert _retryable(exc) is True

    @pytest.mark.parametrize("cls,code", [
        (openai.RateLimitError, 429),
        (openai.ConflictError, 409),
    ])
    def test_transient_status_codes_are_retried(self, cls, code):
        assert _retryable(_status(cls, code)) is True

    @pytest.mark.parametrize("cls,code", [
        (openai.BadRequestError, 400),
        (openai.AuthenticationError, 401),
        (openai.PermissionDeniedError, 403),
        (openai.NotFoundError, 404),
        (openai.UnprocessableEntityError, 422),
    ])
    def test_permanent_status_codes_are_not_retried(self, cls, code):
        """Resending a malformed body produces the same malformed body."""
        assert _retryable(_status(cls, code)) is False

    def test_a_permanent_code_inside_a_500_shaped_reply_is_not_retried(self):
        """A content filter does not become satisfied on the second attempt."""
        exc = openai.APIError("filtered", request=_request(),
                              body={"code": "content_filter"})
        assert _retryable(exc) is False

    def test_an_unparseable_event_is_not_retried(self):
        """A shape the SDK cannot read will be equally unreadable next time."""
        assert _retryable(TypeError("list index out of range")) is False
        assert _retryable(KeyError("output")) is False

    def test_an_unknown_failure_is_retried(self):
        """The bias. An exception nobody classified costs one resend if it was
        hopeless, and saves the generation if it was not."""
        assert _retryable(RuntimeError("something new")) is True


class _Event:
    def __init__(self, type_, **kw):
        self.type = type_
        for k, v in kw.items():
            setattr(self, k, v)


class _Responses:
    """Fails `fail_times` times, then streams a complete response."""

    def __init__(self, exc, fail_times):
        self.exc, self.fail_times, self.calls = exc, fail_times, 0

    def create(self, **_kw):
        self.calls += 1
        if self.calls <= self.fail_times:
            raise self.exc
        final = type("R", (), {"status": "completed", "usage": None})()
        return iter([
            _Event("response.output_text.delta", delta="def step("),
            _Event("response.output_text.delta", delta="self): pass"),
            _Event("response.completed", response=final),
        ])


def _port(tmp_path, retries):
    return ApiPort(root=tmp_path,
                   settings=PortSettings(stream_retries=retries))


def test_a_retryable_chunk_recovers_rather_than_losing_the_work(tmp_path, monkeypatch):
    """The whole point: the second attempt returns the chunk, and the caller
    never sees the failure."""
    monkeypatch.setattr("time.sleep", lambda _s: None)
    exc = openai.APIError("server had an error", request=_request(),
                          body={"code": "server_error"})
    responses = _Responses(exc, fail_times=1)
    client = type("C", (), {"responses": responses})()

    got, final = _port(tmp_path, 2)._stream_chunk(client, {"input": []})

    assert "".join(got) == "def step(self): pass"
    assert final.status == "completed"
    assert responses.calls == 2


def test_a_permanent_failure_is_not_resent(tmp_path, monkeypatch):
    """Retrying a 400 burns the budget and changes nothing."""
    monkeypatch.setattr("time.sleep", lambda _s: None)
    responses = _Responses(_status(openai.BadRequestError, 400), fail_times=99)
    client = type("C", (), {"responses": responses})()

    with pytest.raises(openai.BadRequestError):
        _port(tmp_path, 3)._stream_chunk(client, {"input": []})
    assert responses.calls == 1


def test_retries_are_bounded_and_the_last_error_survives(tmp_path, monkeypatch):
    monkeypatch.setattr("time.sleep", lambda _s: None)
    exc = openai.APIError("still broken", request=_request(), body=None)
    responses = _Responses(exc, fail_times=99)
    client = type("C", (), {"responses": responses})()

    with pytest.raises(openai.APIError):
        _port(tmp_path, 2)._stream_chunk(client, {"input": []})
    assert responses.calls == 3  # 1 attempt + 2 retries


def test_backoff_grows_and_stays_bounded(tmp_path, monkeypatch):
    """Instant resends hit the same unhealthy backend; unbounded ones would
    themselves become the 300s idle gap this path exists to avoid."""
    slept: list[float] = []
    monkeypatch.setattr("time.sleep", slept.append)
    exc = openai.APIError("still broken", request=_request(), body=None)
    client = type("C", (), {"responses": _Responses(exc, fail_times=99)})()

    with pytest.raises(openai.APIError):
        _port(tmp_path, 4)._stream_chunk(client, {"input": []})

    assert slept == [4.0, 8.0, 16.0, 30.0]
    assert max(slept) <= 30.0
