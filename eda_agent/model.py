from __future__ import annotations

import asyncio
import json
import logging
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


class UsageTrackingModel(ChatModelBase):
    def __init__(self, base_model: ChatModelBase) -> None:
        self._base_model = base_model
        super().__init__(
            model_name=base_model.model_name,
            stream=base_model.stream,
        )
        self._input_tokens = 0
        self._output_tokens = 0

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

    def _accumulate_usage(self, usage: Any) -> None:
        if usage is None:
            return
        self._input_tokens += int(getattr(usage, "input_tokens", 0) or 0)
        self._output_tokens += int(getattr(usage, "output_tokens", 0) or 0)

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

    async def __call__(self, *args: Any, **kwargs: Any):  # type: ignore[override]
        for attempt in range(self._DECODE_RETRIES):
            try:
                res = await self._base_model(*args, **kwargs)
                break
            except json.JSONDecodeError as e:
                if attempt == self._DECODE_RETRIES - 1:
                    logger.error(
                        "Model response was not decodable JSON after %d attempts "
                        "(%s); giving up and letting the caller see it",
                        self._DECODE_RETRIES, e,
                    )
                    raise
                logger.warning(
                    "Model response was not decodable JSON (%s) — provider sent a "
                    "truncated or non-JSON body over a 200; retrying (%d/%d)",
                    e, attempt + 1, self._DECODE_RETRIES - 1,
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
                f", output_tokens={getattr(usage, 'output_tokens', '?')}" if usage else "",
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


def _is_llama_model(model_name: str) -> bool:
    """Check if the model name indicates a Llama model."""
    name_lower = model_name.lower()
    return any(k in name_lower for k in ["llama", "meta-llama"])


def make_openai_model(cfg: OpenAIConfig) -> ChatModelBase:
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
    # legitimately take minutes. Overridable via OPENAI_TIMEOUT_S.
    try:
        _timeout_s = float(_os.environ.get("OPENAI_TIMEOUT_S", "600"))
    except ValueError:
        _timeout_s = 600.0
    client_args: dict[str, Any] = {
        "max_retries": _max_retries,
        "timeout": _timeout_s,
    }
    if cfg.base_url:
        client_args["base_url"] = cfg.base_url

    base_model = FinishReasonPreservingModel(
        model_name=cfg.model,
        api_key=cfg.api_key,
        stream=cfg.stream,
        reasoning_effort=cfg.reasoning_effort,  # type: ignore[arg-type]
        organization=cfg.organization,
        client_args=client_args or None,
        generate_kwargs=cfg.generate_kwargs or None,
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
    return OpenAIChatFormatter()
