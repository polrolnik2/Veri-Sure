from __future__ import annotations

import asyncio
import json
import logging
import sys
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from agentscope.formatter import OpenAIChatFormatter
from agentscope.formatter._truncated_formatter_base import TruncatedFormatterBase
from agentscope.message import (
    Msg,
    TextBlock,
    ImageBlock,
    AudioBlock,
    ToolUseBlock,
    ToolResultBlock,
)
from agentscope.model import ChatModelBase, OpenAIChatModel

from eda_agent.config import OpenAIConfig

def usage_attr(obj: Any, name: str, default: Any = None) -> Any:
    """Read `name` off a token-usage object of ANY shape, without raising.

    `getattr(obj, name, default)` IS NOT SAFE HERE, and the three-argument form
    reads as though it were. agentscope's `ChatUsage` subclasses `dict` via
    `DictMixin`, so its `__getattr__` is `self[name]` and a missing key raises
    KeyError -- while `getattr`'s default only absorbs AttributeError. Measured
    live: a full run died on its first model response with
    `KeyError: 'input_tokens_details'` and still exited 0.

    IT LIVES IN THIS MODULE FOR A LAYERING REASON, and the reason cost a run.
    It was first put in `specflow.cache_stats`, which already knew both API
    shapes -- and that made `eda_agent/model.py` import specflow. Arm A is by
    construction the tree with specflow DELETED, and `make_arm_a.sh` copies
    this file into it whole, so arm A died immediately with
    `ModuleNotFoundError: No module named 'specflow'`. specflow imports
    eda_agent in a dozen places and never the reverse.

    `eda_agent/utils.py` was the next candidate and is worse: `make_arm_a.sh`
    carries config.py and model.py only, deliberately, so putting it there
    would force arm A to take HEAD's whole 862-line utils.py and contaminate
    the arm with code that IS the hardening under test. Here it rides along
    with a file the arm already takes.

    A Mapping is read as a mapping, everything else by attribute, and both
    swallow only lookup failure -- never a genuine error from a property.
    """
    if isinstance(obj, Mapping):
        return obj.get(name, default)
    try:
        return getattr(obj, name, default)
    except (AttributeError, KeyError, TypeError):
        return default


logger = logging.getLogger(__name__)


class Llama4ChatFormatter(TruncatedFormatterBase):
    """Formatter for Llama-4 models that converts tool results to user messages.
    
    Llama-4 (via OpenAI-compatible APIs) does not support the "tool" role.
    This formatter converts tool_result blocks into user messages with formatted
    content instead of using the "tool" role.
    """

    support_tools_api: bool = True
    support_multiagent: bool = True
    support_vision: bool = True

    supported_blocks: list[type] = [
        TextBlock,
        ImageBlock,
        AudioBlock,
        ToolUseBlock,
        ToolResultBlock,
    ]

    async def _format(
        self,
        msgs: list[Msg],
    ) -> list[dict[str, Any]]:
        """Format message objects into Llama-4 compatible format.
        
        Tool results are converted to user messages instead of using "tool" role.
        """
        self.assert_list_of_msgs(msgs)

        messages: list[dict] = []
        for msg in msgs:
            content_blocks = []
            tool_calls = []
            tool_results = []

            for block in msg.get_content_blocks():
                typ = block.get("type")
                if typ == "text":
                    content_blocks.append({**block})

                elif typ == "tool_use":
                    tool_calls.append(
                        {
                            "id": block.get("id"),
                            "type": "function",
                            "function": {
                                "name": block.get("name"),
                                "arguments": json.dumps(
                                    block.get("input", {}),
                                    ensure_ascii=False,
                                ),
                            },
                        },
                    )

                elif typ == "tool_result":
                    # Collect tool results to convert to user message format
                    tool_name = block.get("name", "tool")
                    tool_id = block.get("id", "")
                    tool_output = self.convert_tool_result_to_string(
                        block.get("output"),  # type: ignore[arg-type]
                    )
                    tool_results.append({
                        "name": tool_name,
                        "id": tool_id,
                        "output": tool_output,
                    })

                elif typ == "image":
                    source_type = block["source"]["type"]
                    if source_type == "url":
                        url = block["source"]["url"]
                    elif source_type == "base64":
                        data = block["source"]["data"]
                        media_type = block["source"]["media_type"]
                        url = f"data:{media_type};base64,{data}"
                    else:
                        raise ValueError(
                            f"Unsupported image source type: {source_type}",
                        )

                    content_blocks.append(
                        {
                            "type": "image_url",
                            "image_url": {"url": url},
                        },
                    )

                elif typ == "audio":
                    # Llama-4 may not support audio; skip or handle gracefully
                    pass

            # Build the message
            msg_dict = {
                "role": msg.role,
                "name": msg.name,
                "content": content_blocks or None,
            }

            if tool_calls:
                msg_dict["tool_calls"] = tool_calls

            # Add regular message if it has content or tool_calls
            if msg_dict["content"] or msg_dict.get("tool_calls"):
                messages.append(msg_dict)

            # Convert tool results to user messages (Llama-4 compatible format)
            for tr in tool_results:
                tool_result_text = (
                    f"[Tool Result: {tr['name']}]\n"
                    f"{tr['output']}"
                )
                messages.append({
                    "role": "user",
                    "content": [{"type": "text", "text": tool_result_text}],
                })

        return messages


#: Where the API's own `function.arguments` string is stashed on a tool_use
#: block, so the formatter can replay it instead of re-deriving it.
RAW_ARGS = "_raw_arguments"


class ByteReplayFormatter(OpenAIChatFormatter):
    """Send back the argument bytes the API sent, not our re-derivation of them.

    A gateway returns `function.arguments` as a JSON STRING. The SDK parses it,
    agentscope holds a dict, and the base formatter re-serializes it on every
    later call -- so what goes out is ours: `{"a":1}` becomes `{"a": 1}`.

    That is harmless while the re-derivation is deterministic, and measured
    against the live gateway it is: same key order, identical output across
    three hash seeds. But it holds by a property of CPython -- `json.loads`
    fills a dict in document order and `json.dumps` walks insertion order --
    and nothing enforces it. A `set` anywhere on that path, a different encoder,
    or a port to a language with randomized map iteration breaks it silently,
    and the whole suffix after the first tool call reprices as fresh tokens.

    So the bytes are kept at parse time and replayed verbatim here. Strictly a
    narrowing: with nothing stashed this is the base formatter exactly, which is
    what happens for a block this process constructed rather than received.
    """

    async def _format(self, msgs: list[Msg]) -> list[dict[str, Any]]:
        formatted = await super()._format(msgs)
        raw: dict[str, str] = {}
        for msg in msgs:
            for block in msg.get_content_blocks():
                if block.get("type") == "tool_use" and block.get(RAW_ARGS):
                    raw[str(block.get("id"))] = str(block[RAW_ARGS])
        if not raw:
            return formatted
        for entry in formatted:
            for call in entry.get("tool_calls") or []:
                kept = raw.get(str(call.get("id")))
                if kept is not None and isinstance(call.get("function"), dict):
                    call["function"]["arguments"] = kept
        return formatted


class FinishReasonPreservingModel(OpenAIChatModel):
    """Keep `finish_reason` instead of discarding it at the parse boundary.

    A response that stopped because it hit the token cap is a SUCCESSFUL HTTP
    200 carrying a PARTIAL artifact. The OpenAI SDK does not retry it -- rightly,
    since what to do about it is the caller's policy -- and agentscope's parser
    reads `choices[0].message.content` and drops every other field, so
    `finish_reason` never reaches any wrapper above it. `UsageTrackingModel`
    wraps agentscope, not the client, which is why no amount of wrapping there
    could ever have seen it.

    The result is a truncated testbench or RTL that is indistinguishable from a
    complete one: it simply fails to lint, or worse, lints and is subtly wrong.
    That is the same "couldn't check" vs "checked and failed" confusion as B49
    and B65, one layer lower -- at the model boundary, where it is invisible to
    every guard downstream.

    Verified against the live provider (2026-08-04): a call capped at 16 tokens
    returns `finish_reason='length'` and `native_finish_reason='length'`, so the
    signal is present and was simply being thrown away.

    `ChatResponse.metadata` already exists for exactly this kind of out-of-band
    fact, so nothing is forked -- `super()` still does all the parsing and this
    only annotates what it returns.
    """

    def _parse_openai_completion_response(self, *args: Any, **kwargs: Any):  # type: ignore[override]
        resp = super()._parse_openai_completion_response(*args, **kwargs)
        _keep_raw_arguments(resp, kwargs.get("response") or next(
            (a for a in args if hasattr(a, "choices")), None))
        # `response` is positional in agentscope's signature but be tolerant:
        # a future signature change must not take the model layer down.
        raw = kwargs.get("response") or next(
            (a for a in args if hasattr(a, "choices")), None
        )
        try:
            choice = (getattr(raw, "choices", None) or [None])[0]
            reason = getattr(choice, "finish_reason", None)
            if reason:
                meta = dict(resp.metadata or {})
                meta["finish_reason"] = reason
                native = getattr(choice, "native_finish_reason", None)
                if native:
                    meta["native_finish_reason"] = native
                resp.metadata = meta
        except Exception:  # noqa: BLE001
            # Annotation is a diagnostic. Never let it cost a usable response.
            pass
        return resp


def _keep_raw_arguments(resp: Any, raw: Any) -> None:
    """Stash each tool call's `arguments` string exactly as it arrived.

    Matched by call id rather than by position, because a response may carry
    several calls and nothing guarantees the parsed blocks keep their order.
    Never raises: replaying bytes is an optimisation, and losing it must not
    cost a usable response.
    """
    try:
        wire = {}
        for choice in getattr(raw, "choices", None) or []:
            message = getattr(choice, "message", None)
            for call in getattr(message, "tool_calls", None) or []:
                args = getattr(getattr(call, "function", None), "arguments", None)
                if isinstance(args, str):
                    wire[str(getattr(call, "id", ""))] = args
        if not wire:
            return
        for block in getattr(resp, "content", None) or []:
            if not isinstance(block, dict) or block.get("type") != "tool_use":
                continue
            kept = wire.get(str(block.get("id", "")))
            if kept is not None:
                block[RAW_ARGS] = kept
    except Exception:  # noqa: BLE001 -- see the docstring
        pass


class UsageTrackingModel(ChatModelBase):
    def __init__(self, base_model: ChatModelBase) -> None:
        self._base_model = base_model
        super().__init__(
            model_name=base_model.model_name,
            stream=base_model.stream,
        )
        self._input_tokens = 0
        self._output_tokens = 0
        self._cached_tokens = 0

    @property
    def model_name(self) -> str:  # type: ignore[override]
        return self._base_model.model_name if hasattr(self, "_base_model") else self.__dict__.get("model_name", "")

    @model_name.setter
    def model_name(self, value: str) -> None:  # type: ignore[override]
        self.__dict__["model_name"] = value
        if hasattr(self, "_base_model"):
            self._base_model.model_name = value

    @property
    def stream(self) -> bool:  # type: ignore[override]
        return self._base_model.stream if hasattr(self, "_base_model") else bool(self.__dict__.get("stream", False))

    @stream.setter
    def stream(self, value: bool) -> None:
        self.__dict__["stream"] = value
        if hasattr(self, "_base_model"):
            self._base_model.stream = value

    @property
    def total_input_tokens(self) -> int:
        return self._input_tokens

    @property
    def total_output_tokens(self) -> int:
        return self._output_tokens

    def reset_usage(self) -> None:
        self._input_tokens = 0
        self._output_tokens = 0
        self._cached_tokens = 0

    @property
    def total_cached_tokens(self) -> int:
        """How much of `total_input_tokens` was served from the prompt cache.

        Cached tokens are a SUBSET of input tokens, not an extra column, and
        they price at a fraction of a fresh read -- so an input total without
        this beside it cannot be turned into a cost. The refmodel debug loop is
        where that bites: it re-sends a monotonically growing conversation up to
        `max_attempts * 10` times per turn, 46.1M input tokens on a2-i2c against
        10.8M for every specflow stage combined, and it was the one stage whose
        cache rate nothing recorded.
        """
        return self._cached_tokens

    def _accumulate_usage(self, usage: Any) -> None:
        if usage is None:
            return
        # `usage_attr`, not `getattr`: agentscope's `ChatUsage` is a dict subclass
        # whose `__getattr__` raises KeyError, which `getattr`'s default does
        # not absorb. See `_attr`'s docstring -- this killed a run at its first
        # call, and the run then exited 0.
        self._input_tokens += int(usage_attr(usage, "input_tokens", 0) or 0)
        self._output_tokens += int(usage_attr(usage, "output_tokens", 0) or 0)
        # THE KEY IS NESTED, and reading the top level returns nothing and
        # reports 0% on a run that was in fact heavily cached -- a mistake this
        # project has already made once. `cache_stats` is the one place that
        # knows both API shapes (`input_tokens_details` on Responses,
        # `prompt_tokens_details` on Chat), so this borrows its reader rather
        # than becoming a second one that can drift from it.
        details = (usage_attr(usage, "input_tokens_details")
                   or usage_attr(usage, "prompt_tokens_details"))
        if details is not None:
            try:
                self._cached_tokens += int(usage_attr(details, "cached_tokens", 0) or 0)
            except (TypeError, ValueError):
                pass

    # A provider can answer HTTP 200 with a body that is not valid JSON — a
    # truncated stream, or an error page — and the OpenAI client raises
    # `json.JSONDecodeError` out of `response.json()` with no retry of its own
    # (its retry logic covers status codes and connection errors, not a body it
    # could not parse). That exception unwinds through the whole agent stack and
    # kills the leaf.
    #
    # Measured on fp_align_add (run fp_adder_e2e, 2026-08-03 12:39):
    #
    #     json.decoder.JSONDecodeError: Expecting value: line 1547 column 1 (char 8503)
    #
    # The attempt had already written rtl.sv, run six debug iterations and
    # regenerated after a mismatch — roughly an hour — and was recorded as
    # "produced no RTL". Every one of the run's 92 HTTP responses was 200 OK,
    # which is exactly why this was invisible until the exception was surfaced
    # (B45/F28).
    #
    # Deliberately narrow. Only a response the client could not decode is
    # retried: that is unambiguously a transport-layer defect and the request is
    # idempotent, so re-asking is safe. Anything else — a refusal, a tool error,
    # a malformed-but-parseable answer — is a real answer and must reach the
    # caller unchanged, because swallowing those is how a defect becomes a
    # silent retry loop.
    _DECODE_RETRIES = 3

    @staticmethod
    def _describe_undecodable_body(e: json.JSONDecodeError) -> str:
        """Name WHICH undecodable-body failure this is, from the body itself.

        The old message said "truncated or non-JSON body" for every case. For
        the one that actually happens that is wrong, and wrong in this project's
        recurring direction: it describes a partial answer when in fact NO
        answer arrived.

        `JSONDecodeError.doc` carries the raw body, so the distinction is free.

        Measured against a live OpenRouter call: the response is prefixed with
        keep-alive padding that holds the connection open while the request
        queues and generates --

            0000000  \\n                     \\n  \\n
            0000020                         \\n   {   "   i   d   " ...

        The repeating unit is '\\n' + 9 spaces + '\\n' = 11 chars over 2 lines,
        i.e. EXACTLY 5.500 chars per line. All nine failures recorded across
        2026-08-03/05 sit at 5.486-5.498 -- just under 5.5, which is what a body
        of padding and nothing else gives (the deficit is the final partial unit
        plus the 0-based char offset). Any real JSON would add one very long
        line and pull the ratio far above 5.5; none of the nine does.

        So the provider accepted the request, committed a 200, flushed headers,
        streamed padding while waiting on the upstream, then lost the generation
        and could only close the connection. Retrying is right -- there is
        nothing to continue, only to re-ask -- but the operator should read
        "provider capacity", not "our payload was malformed".
        """
        doc = getattr(e, "doc", None) or ""
        if doc and not doc.strip():
            lines = doc.count("\n") or 1
            return (
                f"the provider ACCEPTED the request and then dropped it: the body "
                f"is {len(doc)} chars of keep-alive padding "
                f"({len(doc) / lines:.2f} chars/line) and contains no JSON at "
                f"all. Nothing was generated, so there is nothing to resume — "
                f"only to re-ask. Padding volume tracks how long the request "
                f"hung before being lost"
            )
        head = doc[:80].replace("\n", "\\n")
        return (
            f"the body is {len(doc)} chars and is not JSON ({e}); "
            f"starts {head!r} — an error page or a genuinely truncated document, "
            f"which is NOT the keep-alive-padding case"
        )

    async def __call__(self, *args: Any, **kwargs: Any):  # type: ignore[override]
        for attempt in range(self._DECODE_RETRIES):
            try:
                res = await self._base_model(*args, **kwargs)
                break
            except json.JSONDecodeError as e:
                if attempt == self._DECODE_RETRIES - 1:
                    logger.error(
                        "Undecodable body after %d attempts — %s; giving up and "
                        "letting the caller see it",
                        self._DECODE_RETRIES, self._describe_undecodable_body(e),
                    )
                    raise
                logger.warning(
                    "Undecodable body over a 200 — %s; retrying (%d/%d)",
                    self._describe_undecodable_body(e),
                    attempt + 1, self._DECODE_RETRIES - 1,
                )
                await asyncio.sleep(min(2.0 ** attempt, 8.0))
        if self._base_model.stream:
            async def _gen():
                seen_usage = False
                async for chunk in res:
                    if (not seen_usage) and getattr(chunk, "usage", None):
                        self._accumulate_usage(chunk.usage)
                        seen_usage = True
                    yield chunk
            return _gen()
        self._accumulate_usage(getattr(res, "usage", None))
        self._warn_if_truncated(res)
        return res

    @staticmethod
    def _warn_if_truncated(res: Any) -> None:
        """Say so when the model stopped because it ran out of tokens.

        Without this the caller receives a partial artifact with no indication
        that it is partial, and every downstream guard then reasons about a
        testbench or module that the model never finished writing. Naming it is
        the whole point: "the model did not finish" is a different fact from
        "the model produced something wrong", and only the first is fixed by
        asking again.
        """
        try:
            reason = (getattr(res, "metadata", None) or {}).get("finish_reason")
        except Exception:  # noqa: BLE001
            return
        if reason == "length":
            usage = getattr(res, "usage", None)
            logger.warning(
                "MODEL RESPONSE TRUNCATED (finish_reason=length%s): the artifact "
                "is incomplete, not wrong — it stopped at the token cap. Raise "
                "max_completion_tokens or continue the response; do not score "
                "what came back as a failed generation.",
                f", output_tokens={usage_attr(usage, 'output_tokens', '?')}" if usage else "",
            )

    def __getattr__(self, name: str) -> Any:
        return getattr(self._base_model, name)


@dataclass
class UsageBreakdown:
    """Per-agent token breakdown for observability."""

    architect: tuple[int, int] = (0, 0)
    tb_gen: tuple[int, int] = (0, 0)
    rtl_gen: tuple[int, int] = (0, 0)
    rtl_edit: tuple[int, int] = (0, 0)
    consensus_rtl_player: tuple[int, int] = (0, 0)
    consensus_tb_player: tuple[int, int] = (0, 0)

    @property
    def total(self) -> tuple[int, int]:
        pairs = [
            self.architect, self.tb_gen, self.rtl_gen, self.rtl_edit,
            self.consensus_rtl_player, self.consensus_tb_player,
        ]
        return (sum(p[0] for p in pairs), sum(p[1] for p in pairs))

    def to_dict(self) -> dict[str, dict[str, int]]:
        total_in, total_out = self.total
        return {
            "architect": {"input": self.architect[0], "output": self.architect[1]},
            "tb_gen": {"input": self.tb_gen[0], "output": self.tb_gen[1]},
            "rtl_gen": {"input": self.rtl_gen[0], "output": self.rtl_gen[1]},
            "rtl_edit": {"input": self.rtl_edit[0], "output": self.rtl_edit[1]},
            "consensus_rtl_player": {"input": self.consensus_rtl_player[0], "output": self.consensus_rtl_player[1]},
            "consensus_tb_player": {"input": self.consensus_tb_player[0], "output": self.consensus_tb_player[1]},
            "total": {"input": total_in, "output": total_out},
        }


def get_model_usage(model: Any) -> tuple[int, int]:
    input_tokens = getattr(model, "total_input_tokens", None)
    output_tokens = getattr(model, "total_output_tokens", None)
    if input_tokens is None or output_tokens is None:
        return 0, 0
    return int(input_tokens), int(output_tokens)


def get_model_cached(model: Any) -> int:
    """Cached input tokens, cumulative. A SUBSET of `get_model_usage`'s first.

    Separate from `get_model_usage` rather than a third element of it, on
    purpose. `UsageBreakdown` stores that function's result as a pair and its
    `total` sums `p[0]` and `p[1]`; widening the tuple would have made it sum
    input and CACHED and call the answer output -- a silently wrong number in a
    cost ledger, which is worse than the hole this exists to fill.

    An input total on its own cannot be turned into a cost: a cache read prices
    at a fraction of a fresh one, so 46M input tokens is two figures an order of
    magnitude apart depending on this.
    """
    return int(getattr(model, "total_cached_tokens", 0) or 0)


def _is_llama_model(model_name: str) -> bool:
    """Check if the model name indicates a Llama model."""
    name_lower = model_name.lower()
    return any(k in name_lower for k in ["llama", "meta-llama"])


def make_openai_model(cfg: OpenAIConfig,
                      cache_key: str | None = None) -> ChatModelBase:
    """`cache_key` is the prompt-cache ROUTING HINT, one per shared prefix.

    A prompt cache lives on the backend that served the request, so calls that
    share a prefix only benefit if they reach the same backend. Every agent here
    has its own system prompt and its own tool schema, so every agent is its own
    prefix and gets its own key -- pooling two would send traffic to a backend
    holding a head it cannot use.

    It matters most for the refmodel debug loop, which is the largest line in
    the ledger by a wide margin: 46.1M input tokens on a2-i2c against 10.8M for
    every specflow stage combined, from a conversation that is re-sent, growing,
    up to `max_attempts * 10` times per turn. That shape is the best case for
    caching and the worst case for cost, and routing is the difference.

    OPT-IN WAS THE BUG. This used to be "optional, so an agent that has not
    been given one behaves exactly as before" -- and behaving as before means
    NO routing hint at all, silently. Measured: arm A, reconstructed by
    `benchmarks/make_arm_a.sh`, takes this module whole from HEAD but its seven
    agents from the merge base, where `git grep cache_key` matches nothing. So
    every arm A request went out unkeyed while the mechanism sat right here,
    unused, and nothing said so. Byte replay reached that arm because it lives
    INSIDE the single door (`make_formatter`); the key did not, because it was
    handed in from outside.

    So a caller that passes nothing now gets a key derived from ITS OWN MODULE
    rather than none. That keeps the one property that matters -- one key per
    prefix, never pooled, since every agent has its own system prompt and tool
    schema -- while making it impossible to miss by omission. Each of the seven
    agent modules holds exactly one construction site, so module identity and
    prefix identity coincide; a module that ever grows a second, differently
    prefixed agent must pass an explicit key, and the explicit keys below are
    kept for exactly that reason and because they survive a file rename.
    """
    if not cache_key:
        # The CALLER's module, not this one: `sys._getframe(1)` is the frame
        # that called `make_openai_model`. Cheap (no stack walk) and evaluated
        # once per agent construction, not once per request.
        try:
            mod = sys._getframe(1).f_globals.get("__name__") or ""
        except Exception:  # noqa: BLE001 -- a missing frame must not stop a run
            mod = ""
        cache_key = mod.rsplit(".", 1)[-1] or None
    # Raise the OpenAI SDK's retry count (default 2) so rate-limit (429) and
    # transient 5xx/connection errors are ridden out via the SDK's built-in
    # exponential backoff + jitter (which also honors Retry-After /
    # x-ratelimit-reset headers). The default 2 only absorbs brief bursts; on a
    # shared free-tier key running many parallel problems, sustained throttling
    # outlasts 2 retries and surfaces as a spurious leaf failure — or crashes the
    # run at the unwrapped Architect/Proposer calls. 8 retries ~= up to a minute
    # of cumulative backoff, enough to cross a per-minute free-tier window.
    # Overridable via OPENAI_MAX_RETRIES.
    import os as _os
    try:
        _max_retries = int(_os.environ.get("OPENAI_MAX_RETRIES", "8"))
    except ValueError:
        _max_retries = 8
    # A per-request TIMEOUT. Without one the SDK waits indefinitely, so a single
    # stalled request silently consumes a run's entire wall clock with no log
    # output at all. Observed live (booth 7803027, 2026-07-26): 8+ minutes with
    # one in-flight request and zero output, which read as a hang -- the job was
    # cancelled on that assumption while it was in fact still progressing.
    #
    # This is a per-ATTEMPT bound, and max_retries above still applies, so a
    # genuinely slow-but-alive call is retried rather than lost. Generous by
    # default because reasoning models on ~20K-token composition prompts
    # legitimately take minutes.
    #
    # IT COMES FROM THE CONFIG, so a caller sets it with a switch and the run
    # can report what it used. The environment is read only as a fallback for
    # a config built before the field existed; a value passed in always wins.
    # This bound is not theoretical -- see `OpenAIConfig.timeout_s` for the
    # measurement where it, and not the gateway, ended the request.
    _timeout_s = getattr(cfg, "timeout_s", None)
    if _timeout_s is None:
        try:
            _timeout_s = float(_os.environ.get("OPENAI_TIMEOUT_S", "600"))
        except ValueError:
            _timeout_s = 600.0
    _timeout_s = float(_timeout_s)
    client_args: dict[str, Any] = {
        "max_retries": _max_retries,
        "timeout": _timeout_s,
    }
    if cfg.base_url:
        client_args["base_url"] = cfg.base_url

    gen_kwargs = dict(cfg.generate_kwargs or {})
    if cache_key:
        gen_kwargs.setdefault("prompt_cache_key", f"veri-sure:{cache_key}:{cfg.model}")

    if cfg.api_flavor == "responses":
        # Selected when tools and reasoning effort have to coexist: a gateway
        # can refuse that combination on chat-completions and point at
        # /v1/responses instead, and every agent here is tool-using. The
        # adapter reports truncation through the same
        # `metadata["finish_reason"]` channel, so the usage and truncation
        # guards below are unaffected by the switch.
        from .responses_model import OpenAIResponsesModel

        return UsageTrackingModel(
            OpenAIResponsesModel(
                model_name=cfg.model,
                api_key=cfg.api_key,
                stream=cfg.stream,
                reasoning_effort=cfg.reasoning_effort,
                organization=cfg.organization,
                client_args=client_args or None,
                generate_kwargs=gen_kwargs or None,
            )
        )

    base_model = FinishReasonPreservingModel(
        model_name=cfg.model,
        api_key=cfg.api_key,
        stream=cfg.stream,
        reasoning_effort=cfg.reasoning_effort,  # type: ignore[arg-type]
        organization=cfg.organization,
        client_args=client_args or None,
        generate_kwargs=gen_kwargs or None,
    )
    return UsageTrackingModel(base_model)


def make_formatter(model_name: str | None = None) -> OpenAIChatFormatter | Llama4ChatFormatter:
    """Create a message formatter appropriate for the model.
    
    Args:
        model_name: The model name to determine formatter type. If None or not
                   a Llama model, returns the standard OpenAI formatter.
    
    Returns:
        A formatter compatible with the specified model.
    """
    if model_name and _is_llama_model(model_name):
        return Llama4ChatFormatter()
    return ByteReplayFormatter()
