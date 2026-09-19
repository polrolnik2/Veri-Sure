"""The chunk-and-continue policy, in ONE place, for both transports.

Two callers stream `/v1/responses` against the same gateway: `specflow`'s
`ApiPort` (synchronous, one prompt per stage) and `eda_agent`'s
`OpenAIResponsesChatModel` (asynchronous, a ReAct turn with tools). They faced
the same gateway behaviour and only one of them had an answer to it, which is
why arm A produced RTL on 2 runs of 18 while specflow completed 2,400 calls.

**What the gateway does, measured rather than assumed.** It terminates a single
response somewhere in a ~475-665s band, and it does so while the stream is
HEALTHY. Two instrumented drops on or1200_dc_fsm at xhigh:

    DROPPED after 550.6s: 3922 events, largest gap 8.8s, first content NEVER
    DROPPED after 662.4s: 10082 events, largest gap 9.9s, first content 312.4s

Neither is the 300s idle reaper -- the largest gap between events is under ten
seconds in both, so nothing went quiet. Neither is a client timeout: the 550.6s
drop happened with a 1800s bound in force. Neither exhausted its output budget:
128000 was set and unspent. It is an elapsed-time cap on ONE RESPONSE.

**So the only durable defence is to keep any single request short**, and that is
what this module's policy does: cap each request at a per-effort slice, and
continue from the model's own reasoning items. Measured on the specflow side
across 2,400 calls of a live i2c run: median 10-30s, longest 536s, exactly one
over 475s. Its witness call -- same model, same xhigh effort, 38,118 output
tokens of which 33,069 reasoning -- took 383s, comfortably under the band.

**Why a policy module and not a shared loop.** One caller iterates a synchronous
generator and the other an async one, which the SDK forces; a single function
cannot serve both without duplicating the loop anyway. So the LOOP stays with
each transport and every DECISION it makes comes from here -- the slice, whether
to continue, what the next request's input is, whether a failure is worth
resending, when to widen. Those are the parts that were allowed to diverge, and
the divergence is what this module exists to stop.

It lives in `eda_agent` because that is the LOWER layer: `eda_agent` may not
import `specflow` -- arm A is reconstructed with `specflow/` deleted -- while
`specflow` imports `eda_agent` widely. Same reasoning as `usage_attr`.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

#: Output slice per request, by reasoning effort. THE SLICE IS A BUDGET FOR
#: REASONING AND CONTENT TOGETHER, so it has to scale with effort: a slice
#: smaller than the reasoning budget yields no content at all, and on this
#: gateway that is not merely unproductive but fatal -- a response truncated
#: inside the reasoning phase gets no `response.incomplete` and no terminal
#: event, just silence until the reaper.
#:
#: Measured on one 21.7 KB prompt, one stream each: `high` at 9000 emitted 7545
#: events without a single content delta, went quiet at t=206.0s and dropped at
#: t=506.3s; `high` at 48000 completed in 96.5s with a 10.2s worst-case gap.
#: The numbers here are that measurement doubled, so a generation longer than
#: the probe's still lands inside its slice.
EFFORT_CHUNK: dict[str, int] = {
    "low": 9000, "medium": 9000, "high": 48000, "xhigh": 64000,
}

#: The slice when the effort is unknown or unset.
DEFAULT_CHUNK = 9000

#: Total output budget across all continuations of one generation. Must stay
#: well above the widest slice: `rounds` is `ceil(total / slice)`, so at
#: total == slice it is 1 and continuation silently disappears at exactly the
#: effort whose generations are longest.
DEFAULT_TOTAL = 192000

#: How many times a mid-stream drop may DOUBLE the slice instead of being
#: reported. Two, because doubling twice covers a 4x under-estimate of the
#: reasoning budget and anything past that is not a slice problem.
DEFAULT_WIDENINGS = 2

#: Resends of a dropped stream. Distinct from the SDK's own `max_retries`,
#: which applies before a response starts.
DEFAULT_STREAM_RETRIES = 2

#: Names of exceptions that mean the connection died mid-stream. A drop with no
#: terminal event is the signature of a response truncated inside the reasoning
#: phase, which this gateway does not signal -- so it is the one failure the
#: continuation machinery cannot handle, and a wider slice is the only repair.
MIDSTREAM_DROP = ("RemoteProtocolError", "ReadTimeout", "ConnectError",
                  "ReadError", "APIConnectionError", "APITimeoutError")

#: Exceptions that will fail identically however many times we resend.
#:
#: Everything else is retried, and that asymmetry is deliberate: a wrong guess
#: in this direction costs one wasted resend, a wrong guess the other way
#: throws away a whole generation. One i2c reference model at `xhigh` -- about
#: 30 minutes of work -- was lost to a gateway 500 whose own message said "You
#: can retry your request".
PERMANENT = frozenset({
    "BadRequestError",           # 400 -- the body is malformed; it still will be
    "AuthenticationError",       # 401
    "PermissionDeniedError",     # 403
    "NotFoundError",             # 404 -- wrong route, or an unresolvable model
    "UnprocessableEntityError",  # 422
    "TypeError", "KeyError", "IndexError",  # an event shape the SDK cannot parse
})

#: Error `code`/`type` values that stay permanent inside a 500-shaped reply.
PERMANENT_CODES = frozenset({
    "content_filter", "invalid_request_error", "context_length_exceeded",
    "model_not_found", "insufficient_quota",
})

#: What the model is told when a slice runs out. Anything less than feeding its
#: own reasoning items back -- a summary, or a bare "carry on" -- restarts the
#: reasoning from nothing.
CONTINUE_NUDGE = ("Continue from exactly where you stopped. Do not repeat "
                  "anything you have already produced.")


def chunk_for(effort: str | None, table: dict[str, int] | None = None) -> int:
    """The per-request output slice for this effort."""
    return (table or EFFORT_CHUNK).get((effort or "").lower(), DEFAULT_CHUNK)


def retryable(exc: BaseException) -> bool:
    """Should this failure be resent?

    The exception's type alone is not enough. When an SSE stream carries an
    error event the SDK raises a **bare `APIError`** -- not an `APIStatusError`,
    so there is no `status_code` to read -- and that is exactly how this gateway
    reports a transient server-side 500 in the middle of a long generation.
    Classifying by name filed it with the permanent failures, so a 500 that
    explicitly invited a retry killed a 30-minute generation on its second
    continuation chunk instead.

    Permanent by name, permanent by error code in the body, retryable
    otherwise -- biased towards retrying, because the two mistakes do not cost
    the same.
    """
    if type(exc).__name__ in PERMANENT:
        return False
    body = getattr(exc, "body", None)
    if isinstance(body, dict):
        for key in ("code", "type"):
            value = body.get(key)
            if isinstance(value, str) and value in PERMANENT_CODES:
                return False
    status = getattr(exc, "status_code", None)
    if isinstance(status, int) and 400 <= status < 500 and status not in (408, 409, 429):
        return False
    return True


def is_midstream_drop(exc: BaseException) -> bool:
    """A drop the continuation machinery cannot see, so widening is the repair."""
    return type(exc).__name__ in MIDSTREAM_DROP


def as_input_item(item: Any) -> dict:
    """An output item, reshaped into something the API accepts as INPUT.

    The two are not the same schema, and the difference is not written down
    anywhere you would look for it. Feeding a reasoning item straight back
    yields `Unknown parameter: 'input[1].status'` -- `status` is emitted on
    output and rejected on input. Nulls go for the same reason: to a strict
    validator an explicit `"content": null` is not an absent key.
    """
    if hasattr(item, "model_dump"):
        data = item.model_dump(exclude_none=True)
    elif isinstance(item, Mapping):
        data = {k: v for k, v in item.items() if v is not None}
    else:
        # Neither a pydantic model nor a mapping. The SDK returns the first and
        # the replay fixtures the second, but a bare object used to raise
        # `TypeError: not iterable` here -- and `TypeError` is classified
        # PERMANENT, so an item shape nobody anticipated would have failed the
        # whole generation with no retry rather than degrading.
        data = {k: v for k, v in vars(item).items()
                if v is not None and not k.startswith("_")}
    data.pop("status", None)
    return data


def wants_continuation(final: Any) -> bool:
    """Did this response stop because it ran out of SLICE, not out of things to say?

    Only `incomplete` with `max_output_tokens` continues. A response that
    stopped for any other reason is finished, and resending it would duplicate
    work or loop.
    """
    if getattr(final, "status", None) != "incomplete":
        return False
    reason = getattr(getattr(final, "incomplete_details", None), "reason", None)
    return reason == "max_output_tokens"


def continuation_input(conversation: list, final: Any) -> list:
    """The next request's input: the conversation, the model's own reasoning, a nudge.

    The reasoning items go back VERBATIM. That is what `include:
    ["reasoning.encrypted_content"]` on the request is for -- the plaintext
    `content` field comes back empty from this gateway and the summary is lossy
    by construction, so the encrypted item is the only faithful carrier of where
    the model actually was.
    """
    return list(conversation) + [
        as_input_item(item) for item in (getattr(final, "output", None) or [])
    ] + [{"role": "user", "content": CONTINUE_NUDGE}]


def plan(total: int, chunk: int, *, responses_chunk: int = DEFAULT_CHUNK
         ) -> tuple[int, int, str | None]:
    """(slice, rounds, warning) for one generation.

    A SLICE EQUAL TO THE CEILING HAS NO RECOVERY PATH AT ALL, and that is a
    configuration rather than a failure -- so it is caught here rather than
    discovered when a call dies. `rounds` is `ceil(total / chunk)`: at
    slice == total it is 1, so there is no continuation, and widening requires
    room under `total`, so there is no widening either. Both halves of the
    mid-stream-drop recovery are silently off.

    It cost a two-hour run once: a ceiling of 48000 against `xhigh`'s 64000
    slice made the effective cap `min(64000, 48000)` = 48000 = total, the
    largest call in the run took a mid-stream drop with neither mechanism
    available, and the stage that depended on it never ran.

    The operator's ceiling is a COST control and is respected: the slice comes
    down to fit rather than the ceiling going up.
    """
    warning = None
    if total <= chunk:
        chunk = max(int(responses_chunk), total // 3) or total
        warning = (
            f"max_output_tokens={total} is not above the slice for this "
            f"effort, which would leave no continuation and no widening; "
            f"narrowing the slice to {chunk}. Raise the ceiling to at least "
            f"3x the slice instead.")
    rounds = max(1, -(-total // max(1, chunk)))
    return chunk, rounds, warning
