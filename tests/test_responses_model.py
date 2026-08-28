"""The Responses-API adapter: conversion, parsing, and the truncation signal.

No network. What needs testing is the translation between two API shapes and
what the adapter refuses to lose -- not that `openai` can make a request.

The adapter exists because this gateway rejects function tools together with
`reasoning_effort` on /v1/chat/completions and directs callers to /v1/responses.
Every agent in `eda_agent` is tool-using, so without it the RTL loop runs at the
endpoint's default effort while only specflow's tool-free calls honour the
configured one.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from types import SimpleNamespace

from eda_agent.config import load_openai_config
from eda_agent.responses_model import (
    OpenAIResponsesModel,
    to_responses_input,
    to_responses_tools,
)

# ------------------------------------------------------------------- config


def test_api_flavor_is_chat_unless_asked(monkeypatch):
    """Nothing may change API surface by accident."""
    monkeypatch.delenv("OPENAI_API_FLAVOR", raising=False)
    assert load_openai_config().api_flavor == "chat"


def test_api_flavor_is_settable_from_the_environment(monkeypatch):
    monkeypatch.setenv("OPENAI_API_FLAVOR", "RESPONSES")
    assert load_openai_config().api_flavor == "responses"  # normalised


# -------------------------------------------------------------------- input


def test_a_tool_result_becomes_a_function_call_output():
    """The Responses API has no `tool` role at all, so a passthrough would be
    rejected -- and the `call_id` must match the call it answers."""
    items = to_responses_input(
        [
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "call_7",
                        "type": "function",
                        "function": {"name": "run_sim", "arguments": '{"top":"T"}'},
                    }
                ],
            },
            {"role": "tool", "tool_call_id": "call_7", "content": "3 mismatches"},
        ]
    )
    call, output = items
    assert call == {
        "type": "function_call",
        "call_id": "call_7",
        "name": "run_sim",
        "arguments": '{"top":"T"}',
    }
    assert output == {
        "type": "function_call_output",
        "call_id": "call_7",
        "output": "3 mismatches",
    }


def test_system_becomes_developer_and_content_lists_flatten():
    items = to_responses_input(
        [
            {"role": "system", "content": "be precise"},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "a"},
                    {"type": "text", "text": "b"},
                ],
            },
        ]
    )
    assert items[0] == {"role": "developer", "content": "be precise"}
    assert items[1] == {"role": "user", "content": "ab"}


def test_an_empty_assistant_turn_carrying_a_call_emits_no_message():
    """An assistant turn whose only content is a tool call must not also send an
    empty message, which the API rejects."""
    items = to_responses_input(
        [
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "c",
                        "type": "function",
                        "function": {"name": "f", "arguments": "{}"},
                    }
                ],
            }
        ]
    )
    assert [i.get("type") for i in items] == ["function_call"]


def test_tool_schemas_flatten_and_are_idempotent():
    nested = [
        {
            "type": "function",
            "function": {
                "name": "f",
                "description": "d",
                "parameters": {"type": "object"},
            },
        }
    ]
    flat = to_responses_tools(nested)
    assert flat == [
        {
            "type": "function",
            "name": "f",
            "description": "d",
            "parameters": {"type": "object"},
        }
    ]
    assert to_responses_tools(flat) == flat


# -------------------------------------------------------------------- parse


def _response(output, *, status="completed", reason=None):
    return SimpleNamespace(
        output=output,
        status=status,
        incomplete_details=SimpleNamespace(reason=reason),
        usage=SimpleNamespace(input_tokens=11, output_tokens=22),
    )


class _FakeStream:
    """What `responses.create(stream=True)` returns: an async iterator of events.

    The final response arrives INSIDE the terminal event, which is the shape
    `_create` reads and the reason it needs no accumulator.
    """

    def __init__(self, events):
        self._events = list(events)

    def __aiter__(self):
        async def gen():
            for e in self._events:
                yield e
        return gen()


def _stream_of(response, *, terminal="response.completed", extra=()):
    return _FakeStream(list(extra) + [
        SimpleNamespace(type=terminal, response=response)])


def test_a_function_call_becomes_a_tool_use_block():
    resp = _response(
        [
            SimpleNamespace(
                type="function_call",
                call_id="call_1",
                name="run_sim",
                arguments='{"top": "TopModule"}',
            )
        ]
    )
    parsed = OpenAIResponsesModel._parse(datetime.now(), resp)
    (block,) = parsed.content
    assert block["type"] == "tool_use"
    assert block["id"] == "call_1"
    assert block["input"] == {"top": "TopModule"}
    assert parsed.usage.input_tokens == 11


def test_malformed_tool_arguments_do_not_raise():
    """A JSONDecodeError unwinding through the model boundary kills the leaf;
    the agent layer reports a bad argument far more usefully."""
    resp = _response(
        [SimpleNamespace(type="function_call", call_id="c", name="f", arguments="{no")]
    )
    (block,) = OpenAIResponsesModel._parse(datetime.now(), resp).content
    assert block["input"] == {"__unparsed_arguments__": "{no"}


def test_truncation_survives_as_finish_reason():
    """`model.py` reports a truncated artifact off
    `metadata["finish_reason"] == "length"`. Losing it would make a response cut
    short by the token budget look complete -- the same "couldn't finish" vs
    "finished" confusion `FinishReasonPreservingModel` prevents on the chat
    path."""
    parsed = OpenAIResponsesModel._parse(
        datetime.now(), _response([], status="incomplete", reason="max_output_tokens")
    )
    assert parsed.metadata["finish_reason"] == "length"


def test_a_complete_response_carries_no_finish_reason():
    parsed = OpenAIResponsesModel._parse(
        datetime.now(),
        _response([SimpleNamespace(type="message", content=[SimpleNamespace(text="hi")])]),
    )
    assert not (parsed.metadata or {}).get("finish_reason")
    assert parsed.content[0]["text"] == "hi"


# ------------------------------------------------------------------ request


def test_the_effort_and_the_token_budget_reach_the_request():
    """`max_completion_tokens` is the chat spelling; Responses calls the same
    budget `max_output_tokens` and rejects the other one."""
    model = OpenAIResponsesModel(
        model_name="gpt-5.6-luna",
        api_key="k",
        reasoning_effort="xhigh",
        generate_kwargs={"max_completion_tokens": 8000, "temperature": 0.0},
    )
    seen: dict = {}

    async def _create(**kwargs):
        seen.update(kwargs)
        return _stream_of(_response(
            [SimpleNamespace(type="message", content=[SimpleNamespace(text="ok")])]
        ))

    model.client = SimpleNamespace(responses=SimpleNamespace(create=_create))
    asyncio.run(
        model(
            [{"role": "user", "content": "hi"}],
            tools=[
                {
                    "type": "function",
                    "function": {
                        "name": "f",
                        "description": "",
                        "parameters": {"type": "object"},
                    },
                }
            ],
        )
    )

    # `summary` rides with the effort and is NOT optional: without it the
    # gateway sends nothing for the whole reasoning phase, so a streamed
    # connection is still idle and its 300s reaper still closes it. Pinned as
    # part of the request rather than left to the transport, because dropping
    # it is silent -- a shallow merge over `reasoning` would do it.
    assert seen["reasoning"] == {"effort": "xhigh", "summary": "auto"}
    assert seen["max_output_tokens"] == 8000
    assert "max_completion_tokens" not in seen
    # Reasoning models reject an explicit temperature, and this surface is only
    # ever selected for one.
    assert "temperature" not in seen
    assert seen["tools"][0]["name"] == "f"
    assert json.loads(json.dumps(seen["input"])) == [
        {"role": "user", "content": "hi"}
    ]



# ------------------------------------------------- streaming, and why it exists
def test_the_request_is_streamed_and_the_response_comes_from_the_terminal_event():
    """STREAMING IS SURVIVAL HERE, NOT A FEATURE.

    A non-streaming request sends no bytes while the model reasons, and this
    gateway closes a connection after 300s of silence. Measured on arm A,
    or1200_dc_fsm, isolated: contract.json at 09:28:32, done at 09:43:35 --
    903s, which is exactly 3 x 301s, one per attempt under
    OPENAI_MAX_RETRIES=2, every one an APIConnectionError.

    The response is read from the TERMINAL EVENT rather than an accumulator:
    `specflow/model_io.py` measured the SDK's `stream()` helper raising
    `IndexError` on shapes this gateway sends, and raw iteration never hit it.
    """
    model = OpenAIResponsesModel(model_name="gpt-5.6-luna", api_key="k")
    seen: dict = {}

    async def _create(**kwargs):
        seen.update(kwargs)
        return _stream_of(
            _response([SimpleNamespace(type="message",
                                       content=[SimpleNamespace(text="ok")])]),
            # Deltas the model emits on the way; they keep the socket alive and
            # are otherwise discarded, since this class returns one response.
            extra=[SimpleNamespace(type="response.output_text.delta", delta="o"),
                   SimpleNamespace(type="response.output_text.delta", delta="k")])

    model.client = SimpleNamespace(responses=SimpleNamespace(create=_create))
    res = asyncio.run(model([{"role": "user", "content": "hi"}]))
    assert seen["stream"] is True, "the whole point is that bytes keep flowing"
    assert res.content[0]["text"] == "ok"


def test_a_stream_that_ends_without_a_terminal_event_RAISES():
    """Returning None here would report a closed connection as an empty
    generation -- a transport failure wearing a modelling failure's clothes,
    which is the confusion this repo has had to unpick repeatedly."""
    model = OpenAIResponsesModel(model_name="gpt-5.6-luna", api_key="k")

    async def _create(**kwargs):
        return _FakeStream([SimpleNamespace(type="response.output_text.delta",
                                            delta="partial")])

    model.client = SimpleNamespace(responses=SimpleNamespace(create=_create))
    try:
        asyncio.run(model([{"role": "user", "content": "hi"}]))
    except RuntimeError as exc:
        assert "without a terminal event" in str(exc)
    else:
        raise AssertionError("a truncated stream must not look like a result")


def test_a_gateway_that_refuses_to_stream_falls_back_and_says_so(caplog):
    """A silent fallback would restore the exact failure streaming replaced."""
    model = OpenAIResponsesModel(model_name="gpt-5.6-luna", api_key="k")
    calls: list[dict] = []

    async def _create(**kwargs):
        calls.append(kwargs)
        if kwargs.get("stream"):
            raise ValueError("streaming not supported here")
        return _response([SimpleNamespace(type="message",
                                          content=[SimpleNamespace(text="ok")])])

    model.client = SimpleNamespace(responses=SimpleNamespace(create=_create))
    with caplog.at_level("WARNING"):
        res = asyncio.run(model([{"role": "user", "content": "hi"}]))
    assert res.content[0]["text"] == "ok"
    assert len(calls) == 2 and calls[1].get("stream") is None
    # The warning must name what the fallback exposes the run to. Both hazards
    # are pinned: the idle reaper this path originally existed for, and the
    # single-response cap measured later (550.6s and 662.4s drops on healthy
    # streams), which chunking defends against and a non-streamed call cannot.
    assert "idle reaper" in caplog.text
    assert "single response" in caplog.text


# ---------------------------------------------------------------- chunking
def _chunk_response(items, *, status="completed", reason=None, out_tokens=100):
    return SimpleNamespace(
        output=items, status=status,
        incomplete_details=SimpleNamespace(reason=reason) if reason else None,
        usage=SimpleNamespace(input_tokens=10, output_tokens=out_tokens,
                              input_tokens_details=None),
    )


def _chunk_stream(response):
    """An async iterator ending in the terminal event carrying `response`."""
    async def _gen():
        for ev in (SimpleNamespace(type="response.output_text.delta", delta="x"),
                   SimpleNamespace(type=f"response.{response.status}",
                                   response=response)):
            yield ev
    return _gen()


def test_a_spent_slice_continues_and_every_round_reaches_the_caller():
    """THE POINT OF CHUNKING, and the failure it must not introduce.

    A generation split across slices emits text and tool calls in more than one
    response. Parsing only the last would silently drop everything before it.
    """
    model = OpenAIResponsesModel(model_name="gpt-5.6-luna", api_key="k")
    model.reasoning_effort = "xhigh"
    seen: list[dict] = []

    rounds = [
        _chunk_response([SimpleNamespace(type="message",
                                         content=[SimpleNamespace(text="first ")])],
                        status="incomplete", reason="max_output_tokens"),
        _chunk_response([SimpleNamespace(type="message",
                                         content=[SimpleNamespace(text="second")])]),
    ]

    async def _create(**kwargs):
        seen.append(kwargs)
        return _chunk_stream(rounds[len(seen) - 1])

    model.client = SimpleNamespace(responses=SimpleNamespace(create=_create))
    res = asyncio.run(model([{"role": "user", "content": "hi"}]))

    assert len(seen) == 2, "a spent slice must continue"
    # Both rounds' text survives.
    assert "first " in res.content[0]["text"] and "second" in res.content[0]["text"]
    # The continuation carried the first round's items plus a nudge.
    second_input = seen[1]["input"]
    assert any("Continue from exactly" in str(m.get("content", ""))
               for m in second_input if isinstance(m, dict))
    # Statelessness: the continuation depends on what we send, not on what the
    # gateway remembers -- this gateway cannot retrieve a stored response.
    assert seen[0]["store"] is False
    assert seen[0]["include"] == ["reasoning.encrypted_content"]


def test_the_slice_is_the_effort_s_not_the_whole_ceiling():
    """Each REQUEST is short; the ceiling is the budget across all of them."""
    model = OpenAIResponsesModel(model_name="gpt-5.6-luna", api_key="k")
    model.reasoning_effort = "xhigh"
    seen: list[dict] = []

    async def _create(**kwargs):
        seen.append(kwargs)
        return _chunk_stream(_chunk_response([]))

    model.client = SimpleNamespace(responses=SimpleNamespace(create=_create))
    asyncio.run(model([{"role": "user", "content": "hi"}],
                      max_tokens=192000))
    assert seen[0]["max_output_tokens"] == 64000, \
        "an xhigh request must be capped at the xhigh slice, not the ceiling"


def test_usage_is_summed_across_continuations():
    """The last chunk's usage describes that REQUEST, not the generation."""
    model = OpenAIResponsesModel(model_name="gpt-5.6-luna", api_key="k")
    model.reasoning_effort = "xhigh"
    rounds = [
        _chunk_response([], status="incomplete", reason="max_output_tokens",
                        out_tokens=100),
        _chunk_response([], out_tokens=250),
    ]
    n = {"i": 0}

    async def _create(**kwargs):
        r = rounds[n["i"]]
        n["i"] += 1
        return _chunk_stream(r)

    model.client = SimpleNamespace(responses=SimpleNamespace(create=_create))
    res = asyncio.run(model([{"role": "user", "content": "hi"}]))
    assert res.usage.output_tokens == 350
    assert res.usage.input_tokens == 20
