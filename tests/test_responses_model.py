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
        return _response(
            [SimpleNamespace(type="message", content=[SimpleNamespace(text="ok")])]
        )

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

    assert seen["reasoning"] == {"effort": "xhigh"}
    assert seen["max_output_tokens"] == 8000
    assert "max_completion_tokens" not in seen
    # Reasoning models reject an explicit temperature, and this surface is only
    # ever selected for one.
    assert "temperature" not in seen
    assert seen["tools"][0]["name"] == "f"
    assert json.loads(json.dumps(seen["input"])) == [
        {"role": "user", "content": "hi"}
    ]
