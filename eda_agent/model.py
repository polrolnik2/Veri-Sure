from __future__ import annotations

import json
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

    async def __call__(self, *args: Any, **kwargs: Any):  # type: ignore[override]
        res = await self._base_model(*args, **kwargs)
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
        return res

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

    base_model = OpenAIChatModel(
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
