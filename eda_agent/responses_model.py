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

import asyncio
import json
import logging
import time
from datetime import datetime
from typing import Any

from agentscope.message import TextBlock, ThinkingBlock, ToolUseBlock
from agentscope.model import ChatModelBase, ChatResponse
from agentscope.model._model_usage import ChatUsage

from . import stream_policy as policy


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


class _MergedUsage:
    """Usage summed across every continuation of one generation.

    The final chunk's own `usage` describes THAT REQUEST, not the generation.
    Reporting it would under-count a chunked call by however many rounds it
    took -- and each round is a separately billed request, so both input and
    output are additive here. A cost figure that silently drops four fifths of
    the calls is the class of number this project has already had to retract.
    """

    def __init__(self, usages: list) -> None:
        self._usages = usages

    def _sum(self, name: str) -> int:
        total = 0
        for u in self._usages:
            try:
                total += int(getattr(u, name, 0) or 0)
            except (TypeError, ValueError):
                pass
        return total

    @property
    def input_tokens(self) -> int:
        return self._sum("input_tokens")

    @property
    def output_tokens(self) -> int:
        return self._sum("output_tokens")

    @property
    def input_tokens_details(self):
        # The LAST round's, unsummed: it is a breakdown of that request's
        # prefix, and the rounds do not share one. Summing cached tokens across
        # continuations would report a cache hit rate for a prefix that never
        # existed.
        return (getattr(self._usages[-1], "input_tokens_details", None)
                if self._usages else None)


class _Merged:
    """The final response, carrying the output items of EVERY round.

    A chunked generation emits text and tool calls across several responses.
    `_parse` reads `response.output`, so handing it only the last one would
    silently drop everything produced before the last slice ran out -- a
    failure the chunking would otherwise INTRODUCE while fixing the one it
    exists for. Status and incomplete details come from the final response,
    because they describe how the generation actually ended.
    """

    def __init__(self, final, output: list, usages: list | None = None) -> None:
        self._final = final
        self.output = output
        self._usage = _MergedUsage(usages or [])

    @property
    def usage(self):
        return self._usage

    def __getattr__(self, name: str):
        return getattr(self._final, name)


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

    @staticmethod
    def _vitals(started: float, events: int, gap: float, summary_chars: int,
                first_content: float | None, request: dict) -> str:
        """What a stream did, in one line, identical on every exit.

        Written once and shared because the three ways out of `_create` --
        dropped, ended with no terminal event, completed -- are only
        comparable if they report the same fields. The first version had two
        of them formatting their own string and the third saying nothing.
        """
        return (
            f"after {time.monotonic() - started:.1f}s: {events} events, "
            f"largest gap {gap:.1f}s, {summary_chars} summary chars, "
            f"first content "
            f"{f'{first_content:.1f}s' if first_content else 'NEVER'}, "
            f"max_output_tokens={request.get('max_output_tokens')}. "
            "A gap near 300s with no content is the gateway's idle reaper; a "
            "large gap under it with content flowing is the client timeout; "
            "summary chars near a completed call's is a spent output budget."
        )

    async def _create(self, request: dict) -> Any:
        """One generation, CHUNKED so no single request outlives the gateway.

        This gateway terminates a single response somewhere in a ~475-665s band
        while the stream is still healthy -- measured, not inferred: two drops
        on or1200_dc_fsm at xhigh, at 550.6s and 662.4s, with largest
        inter-event gaps of 8.8s and 9.9s, one of them with a 1800s client
        timeout in force and 128000 output tokens unspent. Nothing was idle,
        nothing was truncated, nothing timed out locally.

        So a request that must carry a whole generation is a request that will
        eventually be killed, and no ceiling or timeout fixes that. What fixes
        it is keeping every request short: cap each at the effort's slice and
        continue from the model's own reasoning items. `specflow` has done this
        all along, which is the whole of why it completed 2,400 calls -- longest
        536s, exactly one over 475s -- while arm A produced RTL on 2 runs of 18.

        Every decision here comes from `stream_policy`, shared with that
        transport. Only the loop is separate, because one SDK iterator is async
        and the other is not.

        The output items of EVERY round are merged and handed to `_parse`.
        Taking only the final response's would silently drop text and tool calls
        emitted before the last slice ran out -- the failure this mechanism
        would otherwise introduce while fixing the one it exists for.
        """
        effort = self.reasoning_effort
        total = int(request.pop("max_output_tokens", None)
                    or policy.DEFAULT_TOTAL)
        chunk, rounds, warning = policy.plan(total, policy.chunk_for(effort))
        if warning:
            logger.warning("responses: %s", warning)

        # Continuation carries the model's OWN reasoning, not a summary of it.
        # The plaintext `content` comes back empty from this gateway and the
        # summary is lossy by construction, so the encrypted item is the only
        # faithful carrier. `store: false` keeps it stateless -- the
        # continuation depends on what we send, not on what the gateway
        # remembers, and this gateway cannot retrieve a stored response anyway.
        request["include"] = ["reasoning.encrypted_content"]
        request["store"] = False
        request["max_output_tokens"] = min(chunk, total)

        conversation = request.get("input") or []
        if isinstance(conversation, str):
            conversation = [{"role": "user", "content": conversation}]
        merged: list[Any] = []
        usages: list[Any] = []
        final = None
        spent = 0
        widenings = policy.DEFAULT_WIDENINGS
        attempt = 0

        while attempt < rounds:
            call = dict(request)
            call["input"] = conversation
            try:
                # A drop we can still widen out of must not be resent
                # identically first: the resend reproduces it, and at high
                # effort each reproduction costs minutes to learn nothing.
                final = await self._stream_chunk(
                    call,
                    retries=0 if widenings and call["max_output_tokens"] < total
                    else policy.DEFAULT_STREAM_RETRIES)
            except Exception as exc:  # noqa: BLE001
                if (widenings and call["max_output_tokens"] < total
                        and policy.is_midstream_drop(exc)):
                    widenings -= 1
                    request["max_output_tokens"] = min(
                        total, call["max_output_tokens"] * 2)
                    rounds = max(attempt + 1,
                                 -(-total // max(1, request["max_output_tokens"])))
                    logger.warning(
                        "responses: stream dropped with no terminal event at "
                        "slice=%s -- widening to %s and re-issuing "
                        "continuation %s",
                        call["max_output_tokens"], request["max_output_tokens"],
                        attempt + 1)
                    continue
                raise

            attempt += 1
            merged.extend(getattr(final, "output", None) or [])
            usage = getattr(final, "usage", None)
            if usage is not None:
                usages.append(usage)
            spent += int(getattr(usage, "output_tokens", 0) or 0)
            if not policy.wants_continuation(final):
                break
            conversation = policy.continuation_input(conversation, final)
            request["max_output_tokens"] = min(chunk, max(chunk, total - spent))

        if final is None:
            raise RuntimeError("no response was produced")
        if attempt > 1:
            logger.warning("responses: generation took %d continuations, "
                           "%d output tokens", attempt, spent)
        return _Merged(final, merged, usages)

    async def _stream_chunk(self, call: dict, *, retries: int) -> Any:
        """One streamed slice, resent on any failure a resend could fix.

        Retrying is cheap precisely BECAUSE the work is chunked -- one slice is
        lost, not a whole generation -- so the thing that made chunking
        necessary also makes it affordable.

        `create(stream=True)`, NOT the `stream()` helper: the helper runs an
        accumulator that rebuilds a snapshot from every event and raises on
        shapes this gateway actually sends. And the final response is taken
        from the terminal EVENT, because `incomplete` is the normal path here --
        hitting the slice cap is exactly how a continuation is signalled.
        """
        last: Exception | None = None
        for attempt in range(max(0, retries) + 1):
            if attempt:
                # Bounded so the backoff cannot itself become the idle gap this
                # path exists to avoid.
                await asyncio.sleep(min(30.0, 4.0 * (2 ** (attempt - 1))))
            try:
                return await self._stream_once(call)
            except Exception as exc:  # noqa: BLE001
                if not policy.retryable(exc):
                    raise
                last = exc
        raise last  # type: ignore[misc]

    async def _stream_once(self, request: dict) -> Any:
        """One streamed request, instrumented on every exit.

        The three ways out -- dropped, ended with no terminal event, completed
        -- share one `_vitals` line, because they are only comparable if they
        report the same fields.
        """
        try:
            stream = await self.client.responses.create(**request, stream=True)
        except TypeError:
            return await self.client.responses.create(**request)  # SDK too old
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "responses streaming refused (%s: %s); falling back to a "
                "non-streaming call, which this gateway kills two ways: the "
                "300s idle reaper while the model reasons, and the ~475-665s "
                "cap on a single response. Chunking cannot help a call that "
                "is not streamed.", type(exc).__name__, str(exc)[:200])
            return await self.client.responses.create(**request)

        started = time.monotonic()
        last = started
        events = 0
        gap = 0.0
        summary_chars = 0
        first_content: float | None = None
        final = None
        try:
            async for event in stream:
                now = time.monotonic()
                gap = max(gap, now - last)
                last = now
                events += 1
                etype = getattr(event, "type", "") or ""
                if etype.endswith("output_text.delta"):
                    if first_content is None:
                        first_content = now - started
                elif etype.endswith("summary_text.delta"):
                    summary_chars += len(getattr(event, "delta", "") or "")
                if etype in self._TERMINAL:
                    final = getattr(event, "response", None) or final
        except Exception:
            logger.warning("responses stream DROPPED %s", self._vitals(
                started, events, gap, summary_chars, first_content, request))
            raise
        if final is None:
            logger.warning("responses stream ENDED WITH NO TERMINAL EVENT %s",
                           self._vitals(started, events, gap, summary_chars,
                                        first_content, request))
            raise RuntimeError(
                "the response stream ended without a terminal event; the "
                "connection was closed before the model finished")
        logger.warning("responses stream OK (status=%s) %s",
                       getattr(final, "status", None),
                       self._vitals(started, events, gap, summary_chars,
                                    first_content, request))
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

        # ADJACENT TEXT IS ONE MESSAGE THAT A SLICE BOUNDARY CUT IN HALF.
        #
        # A chunked generation emits each round's text as its own `message`
        # item, so the answer arrives as several TextBlocks that were one
        # sentence before the split. Callers read `content[0]["text"]` -- this
        # module's own tests do -- so leaving them apart hands back the first
        # half and silently drops the rest, which is precisely the truncation
        # the chunking exists to prevent, moved one layer up.
        #
        # Only ADJACENT runs are merged, so a tool call between two texts still
        # separates them and the order the model produced is preserved.
        coalesced: list[Any] = []
        for block in content:
            if (coalesced and isinstance(block, dict)
                    and block.get("type") == "text"
                    and isinstance(coalesced[-1], dict)
                    and coalesced[-1].get("type") == "text"):
                coalesced[-1] = TextBlock(
                    type="text", text=coalesced[-1]["text"] + block["text"])
            else:
                coalesced.append(block)
        content = coalesced

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
