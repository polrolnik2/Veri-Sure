"""An agentscope chat model backed by OpenAI's Responses API.

Written because a tool-using agent cannot use reasoning effort on the
chat-completions endpoint of the SDC gateway. The endpoint answers, verbatim:

    Function tools with reasoning_effort are not supported for gpt-5.6-luna in
    /v1/chat/completions. Please use /v1/responses instead.

Every agent in `eda_agent` is tool-using, so on chat-completions the choice was
between tools and reasoning -- which in practice meant the whole RTL loop ran at
the endpoint's default effort while only specflow's five tool-free calls honoured
the configured one. agentscope 1.0.7 ships no Responses model class
(`agentscope/model/` has Anthropic, DashScope, Gemini, Ollama, OpenAI-chat and
Trinity), so this adapter is that class.

Measured on the gateway before writing it, on one prompt with tools attached:
`effort=low` spends 171 reasoning tokens and `effort=xhigh` spends 671. The
parameter is honoured here, not merely accepted.

Scope: the request shapes `eda_agent` actually uses -- a message list, function
tools, and reasoning effort. Streaming and audio are deliberately absent rather
than half-implemented; `stream` is accepted and ignored, and
`make_openai_model` keeps the chat-completions path as the default so nothing
opts into this by accident.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from agentscope.message import TextBlock, ThinkingBlock, ToolUseBlock
from agentscope.model import ChatModelBase, ChatResponse
from agentscope.model._model_usage import ChatUsage


def _json_loads_or_raw(text: str) -> dict:
    """Tool arguments, or an envelope carrying what could not be parsed.

    A model that emits malformed JSON for a tool call must not take the run
    down: the agent layer above reports a bad argument far more usefully than a
    `JSONDecodeError` unwinding through the model boundary does.
    """
    try:
        value = json.loads(text or "{}")
    except (TypeError, ValueError):
        return {"__unparsed_arguments__": text}
    return value if isinstance(value, dict) else {"value": value}


def _content_to_text(content: Any) -> str:
    """Flatten a chat-format `content` field to plain text.

    The Responses API distinguishes `input_text` from `output_text` by whose
    turn it is, while the chat format this receives uses a single `text` type.
    Rather than reconstruct that distinction per role, collapse to a string --
    which both APIs accept everywhere a content list is legal.
    """
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                # `text` covers the chat format; `input_text`/`output_text`
                # cover a list that has already been converted once.
                parts.append(str(block.get("text") or ""))
        return "".join(parts)
    return str(content)


def to_responses_input(messages: list[dict]) -> list[dict]:
    """Convert chat-format messages into Responses API input items.

    Three shapes need real translation rather than passthrough, and each is a
    place the two APIs disagree:

    * an assistant turn carrying `tool_calls` becomes one `function_call` item
      per call, hoisted out of the message;
    * a `tool` role message becomes a `function_call_output` item keyed by
      `call_id` -- the Responses API has no `tool` role at all;
    * `system` becomes `developer`, which is the Responses spelling.

    The `call_id` linkage is why the whole history is converted every call: a
    `function_call_output` whose `call_id` never appeared in the same input is
    rejected. agentscope re-sends the full message list each turn, so this
    holds naturally.
    """
    items: list[dict] = []
    for msg in messages:
        role = msg.get("role")

        if role == "tool":
            items.append(
                {
                    "type": "function_call_output",
                    "call_id": msg.get("tool_call_id") or msg.get("id") or "",
                    "output": _content_to_text(msg.get("content")),
                }
            )
            continue

        tool_calls = msg.get("tool_calls") or []
        text = _content_to_text(msg.get("content"))
        if text:
            items.append(
                {
                    "role": "developer" if role == "system" else (role or "user"),
                    "content": text,
                }
            )
        for call in tool_calls:
            fn = call.get("function") or {}
            items.append(
                {
                    "type": "function_call",
                    "call_id": call.get("id") or "",
                    "name": fn.get("name") or call.get("name") or "",
                    "arguments": fn.get("arguments")
                    if isinstance(fn.get("arguments"), str)
                    else json.dumps(fn.get("arguments") or {}),
                }
            )
    return items


def to_responses_tools(tools: list[dict] | None) -> list[dict] | None:
    """Flatten chat-format tool schemas into Responses format.

    Chat nests the schema under a `function` key; Responses puts `name`,
    `description` and `parameters` at the top level. Schemas that are already
    flat pass through, so this is safe to apply twice.
    """
    if not tools:
        return None
    out: list[dict] = []
    for tool in tools:
        fn = tool.get("function")
        if isinstance(fn, dict):
            out.append(
                {
                    "type": "function",
                    "name": fn.get("name"),
                    "description": fn.get("description") or "",
                    "parameters": fn.get("parameters")
                    or {"type": "object", "properties": {}},
                }
            )
        else:
            out.append(tool)
    return out


class OpenAIResponsesModel(ChatModelBase):
    """Chat model over `client.responses.create`.

    Same constructor surface as the `OpenAIChatModel` it replaces, so
    `make_openai_model` can swap one for the other without any caller noticing.
    """

    def __init__(
        self,
        model_name: str,
        api_key: str | None = None,
        stream: bool = False,
        reasoning_effort: str | None = None,
        organization: str | None = None,
        client_args: dict | None = None,
        generate_kwargs: dict | None = None,
    ) -> None:
        # Streaming is accepted and ignored rather than rejected: callers set it
        # from a shared config, and refusing here would make a flag that is
        # merely unimplemented look like a misconfiguration.
        super().__init__(model_name=model_name, stream=False)
        self._requested_stream = bool(stream)
        self.reasoning_effort = reasoning_effort
        self.generate_kwargs = dict(generate_kwargs or {})

        from openai import AsyncOpenAI

        kwargs: dict[str, Any] = dict(client_args or {})
        if api_key:
            kwargs["api_key"] = api_key
        if organization:
            kwargs["organization"] = organization
        self.client = AsyncOpenAI(**kwargs)

    async def __call__(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        tool_choice: str | None = None,
        structured_model: Any = None,
        **kwargs: Any,
    ) -> ChatResponse:
        if not isinstance(messages, list):
            raise ValueError(
                f"`messages` expected type `list`, got `{type(messages)}`."
            )

        start = datetime.now()
        request: dict[str, Any] = {
            "model": self.model_name,
            "input": to_responses_input(messages),
        }

        payload = {**self.generate_kwargs, **kwargs}
        # `max_completion_tokens` is the chat spelling; Responses calls the same
        # budget `max_output_tokens`. Passing the chat name through is a 400.
        for chat_name, responses_name in (
            ("max_completion_tokens", "max_output_tokens"),
            ("max_tokens", "max_output_tokens"),
        ):
            if chat_name in payload:
                payload[responses_name] = payload.pop(chat_name)
        # Reasoning models reject an explicit temperature, and this endpoint is
        # only ever selected for one.
        payload.pop("temperature", None)
        payload.pop("stream", None)
        request.update(payload)

        if self.reasoning_effort:
            request["reasoning"] = {"effort": self.reasoning_effort}

        converted = to_responses_tools(tools)
        if converted:
            request["tools"] = converted
            if tool_choice:
                request["tool_choice"] = (
                    tool_choice
                    if tool_choice in ("auto", "none", "required")
                    else {"type": "function", "name": tool_choice}
                )

        response = await self.client.responses.create(**request)
        return self._parse(start, response)

    # ------------------------------------------------------------------ parse
    @staticmethod
    def _parse(start: datetime, response: Any) -> ChatResponse:
        content: list[Any] = []
        for item in getattr(response, "output", None) or []:
            kind = getattr(item, "type", None)

            if kind == "reasoning":
                # Summaries only; the raw chain is not returned by the API.
                summary = "".join(
                    getattr(part, "text", "") or ""
                    for part in (getattr(item, "summary", None) or [])
                )
                if summary:
                    content.append(ThinkingBlock(type="thinking", thinking=summary))

            elif kind == "message":
                text = "".join(
                    getattr(part, "text", "") or ""
                    for part in (getattr(item, "content", None) or [])
                )
                if text:
                    content.append(TextBlock(type="text", text=text))

            elif kind == "function_call":
                content.append(
                    ToolUseBlock(
                        type="tool_use",
                        id=getattr(item, "call_id", "") or getattr(item, "id", ""),
                        name=getattr(item, "name", "") or "",
                        input=_json_loads_or_raw(getattr(item, "arguments", "") or ""),
                    )
                )

        usage = None
        raw_usage = getattr(response, "usage", None)
        if raw_usage is not None:
            usage = ChatUsage(
                input_tokens=int(getattr(raw_usage, "input_tokens", 0) or 0),
                output_tokens=int(getattr(raw_usage, "output_tokens", 0) or 0),
                time=(datetime.now() - start).total_seconds(),
            )

        # Preserve the truncation signal. `model.py` reports a truncated
        # artifact off `metadata["finish_reason"] == "length"`, and without this
        # a response cut short by the token budget would be indistinguishable
        # from a complete one -- the same "couldn't finish" vs "finished" confusion
        # `FinishReasonPreservingModel` exists to prevent on the chat path.
        metadata: dict = {}
        status = getattr(response, "status", None)
        if status == "incomplete":
            reason = getattr(
                getattr(response, "incomplete_details", None), "reason", None
            )
            metadata["finish_reason"] = (
                "length" if reason == "max_output_tokens" else (reason or "incomplete")
            )
            metadata["native_finish_reason"] = reason or "incomplete"

        return ChatResponse(
            content=content, usage=usage, metadata=metadata or None
        )
