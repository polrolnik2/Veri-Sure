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
tools, and reasoning effort. Audio is deliberately absent.

STREAMING IS NOW THE DEFAULT, AND IT IS NOT A FEATURE -- IT IS SURVIVAL. It
used to be "accepted and ignored". Measured, arm A on or1200_dc_fsm, isolated
with nothing else running:

    contract.json 09:28:32 -> done 09:43:35 == 903s == 3 x 301s
    openai.APIConnectionError, at tb_generator's call, three attempts
    (OPENAI_MAX_RETRIES=2), each dying after ~300s

That is this gateway's idle reaper, which `specflow/model_io.py` measured and
documented: "the stream simply stops, and 300s later the idle reaper closes
it". A non-streaming request sends NO bytes while the model reasons, so any
call whose reasoning outlives 300s is killed -- and arm A runs gpt-5.6-luna at
xhigh for every agent, including the testbench generator, its largest call
(13,195 in / 29,868 out on the one run that survived). Ten of eleven batch runs
died this way, all at the same call site, and the isolated retry died the same
way, which is what ruled out contention.

Reading the events also keeps the socket busy, which is the entire point: the
final response is still assembled once, from `get_final_response()`, so
`_parse` is untouched and the non-streaming shape stays the fallback.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

from agentscope.message import TextBlock, ThinkingBlock, ToolUseBlock
from agentscope.model import ChatModelBase, ChatResponse
from agentscope.model._model_usage import ChatUsage


logger = logging.getLogger(__name__)


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
        # `stream` here is agentscope's INCREMENTAL-YIELD contract, which this
        # class does not implement -- it returns one ChatResponse. That stays
        # False. Transport streaming is a separate thing and is always on: see
        # the module docstring. Conflating the two is what left `stream`
        # accepted-and-ignored while the transport died on the idle reaper.
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
            # `summary: "auto"` IS PART OF THE TRANSPORT, not a nicety. Without
            # it a reasoning model emits NOTHING until the answer starts, so
            # streaming keeps an empty socket open and the 300s idle reaper
            # closes it anyway -- measured: arm A with streaming but no summary
            # still died, in 3m22s, with the stream ending before any terminal
            # event. The summary deltas are what actually flow during the gap.
            # `specflow/model_io.py` reaches the same conclusion from the other
            # side: "streaming with reasoning.summary is necessary and not
            # sufficient" -- necessary is this line; sufficient needs the
            # chunk-and-continue that module also implements.
            request["reasoning"] = {"effort": self.reasoning_effort,
                                    "summary": "auto"}

        converted = to_responses_tools(tools)
        if converted:
            request["tools"] = converted
            if tool_choice:
                request["tool_choice"] = (
                    tool_choice
                    if tool_choice in ("auto", "none", "required")
                    else {"type": "function", "name": tool_choice}
                )

        response = await self._create(request)
        return self._parse(start, response)

    #: Terminal stream events. The final response arrives INSIDE one of these,
    #: which is why no accumulator is needed.
    _TERMINAL = ("response.completed", "response.incomplete", "response.failed")

    async def _create(self, request: dict) -> Any:
        """One response, streamed so the connection never goes idle.

        `create(stream=True)`, NOT the `stream()` helper, and the distinction is
        load-bearing -- `specflow/model_io.py` measured it: the helper runs an
        accumulator that rebuilds a snapshot from every event and raises on
        shapes this gateway actually sends (`IndexError: list index out of
        range` from `snapshot.output[event.output_index]`), which killed a live
        run in a small, cheap stage. Raw event iteration never hit it across
        thousands of events. The accumulation is not needed: the final response
        arrives in the terminal event.

        The events are otherwise discarded -- this class returns one
        `ChatResponse`, so there is nothing to yield them to. Reading them is
        what keeps the socket alive past the 300s idle reaper, which is the
        entire reason this path exists.

        Falls back to a plain create if the gateway refuses to stream, and SAYS
        SO: a silent fallback would restore the exact failure this replaced
        without a line in any log.
        """
        try:
            stream = await self.client.responses.create(**request, stream=True)
        except TypeError:
            return await self.client.responses.create(**request)  # SDK too old
        except Exception as exc:  # noqa: BLE001 -- see the docstring
            logger.warning(
                "responses streaming refused (%s: %s); falling back to a "
                "non-streaming call, which this gateway's 300s idle reaper can "
                "kill on a long reason", type(exc).__name__, str(exc)[:200])
            return await self.client.responses.create(**request)

        final = None
        async for event in stream:
            if getattr(event, "type", "") in self._TERMINAL:
                final = getattr(event, "response", None) or final
        if final is None:
            # A stream that ended with no terminal event. Named rather than
            # returned as an empty response, because a caller that got `None`
            # here would report an empty generation as a modelling failure.
            raise RuntimeError(
                "the response stream ended without a terminal event; the "
                "connection was closed before the model finished")
        return final

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
                wire = getattr(item, "arguments", "") or ""
                block = ToolUseBlock(
                    type="tool_use",
                    id=getattr(item, "call_id", "") or getattr(item, "id", ""),
                    name=getattr(item, "name", "") or "",
                    input=_json_loads_or_raw(wire),
                )
                # KEEP THE BYTES so the formatter can replay them rather than
                # re-deriving them from the parsed dict. Re-derivation is
                # deterministic in CPython and is not guaranteed to be, and a
                # single differing byte reprices every request after this tool
                # call as fresh tokens. See `model.ByteReplayFormatter`.
                if isinstance(wire, str) and wire:
                    from .model import RAW_ARGS

                    block[RAW_ARGS] = wire
                content.append(block)

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
