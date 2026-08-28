"""Pins for the chunk-and-continue policy shared by both transports.

The load-bearing one is `test_both_transports_read_one_table`: the entire point
of this module is that `specflow` and `eda_agent` cannot drift on the numbers
that decide whether a request outlives the gateway's cap on a single response.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from eda_agent import stream_policy as policy


def test_both_transports_read_one_table() -> None:
    """specflow's slice table IS the shared one, not a copy of it."""
    from specflow.model_io import PortSettings
    assert PortSettings().effort_chunk == policy.EFFORT_CHUNK
    from specflow import model_io
    assert model_io._MIDSTREAM_DROP is policy.MIDSTREAM_DROP
    assert model_io._PERMANENT is policy.PERMANENT
    assert model_io._PERMANENT_CODES is policy.PERMANENT_CODES


@pytest.mark.parametrize("effort,want", [
    ("xhigh", 64000), ("high", 48000), ("medium", 9000), ("low", 9000),
    ("XHIGH", 64000), (None, policy.DEFAULT_CHUNK), ("nonsense", policy.DEFAULT_CHUNK),
])
def test_slice_scales_with_effort(effort, want) -> None:
    """A slice under the reasoning budget yields no content, and that is fatal."""
    assert policy.chunk_for(effort) == want


def test_a_slice_equal_to_the_ceiling_is_caught_and_narrowed() -> None:
    """At slice == total there is no continuation AND no widening.

    Both halves of the recovery go silently off, which cost a two-hour run.
    """
    chunk, rounds, warning = policy.plan(48000, 64000)
    assert chunk < 48000 and rounds > 1
    assert warning and "no continuation and no widening" in warning


def test_a_healthy_ceiling_is_left_alone() -> None:
    chunk, rounds, warning = policy.plan(192000, 64000)
    assert (chunk, rounds, warning) == (64000, 3, None)


def test_only_a_spent_slice_continues() -> None:
    """A response that stopped for any other reason is FINISHED.

    Continuing one would duplicate work or loop.
    """
    spent = SimpleNamespace(status="incomplete",
                            incomplete_details=SimpleNamespace(reason="max_output_tokens"))
    assert policy.wants_continuation(spent)
    for other in (
        SimpleNamespace(status="completed", incomplete_details=None),
        SimpleNamespace(status="incomplete",
                        incomplete_details=SimpleNamespace(reason="content_filter")),
        SimpleNamespace(status="failed", incomplete_details=None),
    ):
        assert not policy.wants_continuation(other)


def test_continuation_carries_the_models_own_reasoning() -> None:
    """Verbatim items, not a summary -- anything less restarts the reasoning."""
    item = {"type": "reasoning", "id": "r1", "status": "completed",
            "encrypted_content": "abc", "content": None}
    final = SimpleNamespace(output=[item])
    out = policy.continuation_input([{"role": "user", "content": "go"}], final)
    assert out[0] == {"role": "user", "content": "go"}
    # `status` is emitted on output and REJECTED on input; nulls likewise.
    assert out[1] == {"type": "reasoning", "id": "r1", "encrypted_content": "abc"}
    assert out[-1]["role"] == "user" and "Continue from exactly" in out[-1]["content"]


def test_retry_is_biased_towards_resending() -> None:
    """A wrong guess costs one resend; the other way costs a whole generation."""
    class Bad(Exception):
        pass
    Bad.__name__ = "BadRequestError"
    assert not policy.retryable(Bad())

    # The case that cost a 30-minute generation: a gateway 500 arriving as a
    # bare exception with no status_code at all.
    assert policy.retryable(RuntimeError("500 you can retry your request"))

    coded = RuntimeError("nope")
    coded.body = {"code": "context_length_exceeded"}
    assert not policy.retryable(coded)

    throttled = RuntimeError("429")
    throttled.status_code = 429
    assert policy.retryable(throttled)


def test_midstream_drop_is_named_not_guessed() -> None:
    class Drop(Exception):
        pass
    Drop.__name__ = "RemoteProtocolError"
    assert policy.is_midstream_drop(Drop())
    assert not policy.is_midstream_drop(ValueError("x"))
