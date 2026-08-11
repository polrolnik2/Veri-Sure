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
        return await self._complete_if_truncated(res, *args, **kwargs)

    # A response that stopped at the token cap is PARTIAL, not wrong. Throwing
    # it away and asking again pays twice and gets the same length back; the
    # artifact is long because the task is, so a fresh draw truncates too.
    _CONTINUE_ROUNDS = 3
    _CONTINUE_INSTRUCTION = (
        "Your previous message stopped because it hit the output token limit. "
        "It is incomplete, not wrong. Continue it EXACTLY where it stopped — "
        "your next character is the one that would have followed. Do not repeat "
        "any part of it, do not restate the preamble, do not re-open a code "
        "fence you already opened, and do not apologise or explain. Emit only "
        "the remaining text."
    )
    # The reasoning-only case. A reasoning model can spend the ENTIRE output
    # budget thinking and emit no answer at all: measured on gpt-5.6-luna,
    # finish_reason=length with content='' and reasoning_tokens == completion
    # _tokens. There is no text to continue from, but the thinking is real work
    # that was paid for, so it goes back and the model is asked to spend its
    # next budget writing rather than re-deriving.
    _WRITE_UP_INSTRUCTION = (
        "Your previous message spent its whole output budget on reasoning and "
        "emitted no answer. The reasoning is above and is CORRECT WORK — do not "
        "redo it and do not think it through again. Write the final answer now, "
        "directly, using that reasoning. Start with the first character of the "
        "answer itself."
    )

    @staticmethod
    def _text_of(res: Any) -> str:
        out = []
        for block in getattr(res, "content", None) or []:
            if isinstance(block, dict) and block.get("type") == "text":
                out.append(block.get("text") or "")
            elif getattr(block, "type", None) == "text":
                out.append(getattr(block, "text", "") or "")
        return "".join(out)

    @staticmethod
    def _thinking_of(res: Any) -> str:
        """The ThinkingBlock text, which `_text_of` deliberately excludes.

        agentscope maps `message.reasoning_content` to a ThinkingBlock and only
        appends a TextBlock `if choice.message.content`. So a response that hit
        the cap mid-reasoning carries a ThinkingBlock and NOTHING else, and any
        extractor looking only for text sees an empty response -- which is what
        "keeping 0 chars" meant on the first live truncation.
        """
        out = []
        for block in getattr(res, "content", None) or []:
            if isinstance(block, dict) and block.get("type") == "thinking":
                out.append(block.get("thinking") or "")
            elif getattr(block, "type", None) == "thinking":
                out.append(getattr(block, "thinking", "") or "")
        return "".join(out)

    @staticmethod
    def _truncated(res: Any) -> bool:
        try:
            return (getattr(res, "metadata", None) or {}).get("finish_reason") == "length"
        except Exception:  # noqa: BLE001
            return False

    def _resume_turns(self, text: str, thinking: str) -> list[dict]:
        """The assistant turn to resume from, and the instruction that fits it.

        Reasoning tokens are BILLED OUTPUT. Sending back only the answer text
        throws them away and the model re-derives everything from scratch on the
        next round -- paying twice for identical work, on the same budget that
        was too small the first time. So the thinking goes back explicitly.

        Two shapes, and they need different instructions:

          text present    -> a genuine mid-artifact cut; continue from the cut.
          text empty      -> the whole budget went to reasoning (measured on
                             gpt-5.6-luna: content='' with reasoning_tokens ==
                             completion_tokens). Nothing to continue FROM, so
                             ask for the write-up instead of a continuation --
                             "continue exactly where you stopped" is incoherent
                             when nothing was written.
        """
        parts = []
        if thinking:
            parts.append(
                "[Reasoning you have already completed. It is correct and "
                "already paid for — do not repeat or re-derive it.]\n" + thinking
            )
        if text:
            parts.append(text)
        assistant = "\n\n".join(parts) or "(no output was produced)"
        return [
            {"role": "assistant", "content": assistant},
            {"role": "user", "content": (
                self._CONTINUE_INSTRUCTION if text else self._WRITE_UP_INSTRUCTION
            )},
        ]

    async def _complete_if_truncated(self, res: Any, *args: Any, **kwargs: Any):
        """Resume a length-capped response instead of discarding it.

        The partial text goes back as an assistant turn and the model is asked
        to carry on from the cut, so the tokens already paid for are kept and
        the caller sees ONE complete artifact. Without this the partial is
        handed downstream, fails to parse or lint, and is scored as a failed
        generation -- the exact confusion `_warn_if_truncated` names and then
        does nothing about. It also costs an attempt, and attempts are the
        budget that deadlocked three runs at 32/32.

        Bounded at `_CONTINUE_ROUNDS`: a model that truncates four times running
        is not going to finish, and an unbounded loop on a paid endpoint is how
        a budget disappears.

        Best-effort by construction. If the messages cannot be located or a
        continuation call fails, the ORIGINAL partial is returned unchanged --
        the caller is no worse off than before this existed.
        """
        if not self._truncated(res):
            return res

        messages = next((a for a in args if isinstance(a, list)), None)
        if messages is None:
            messages = kwargs.get("messages")
        if not isinstance(messages, list) or not messages:
            logger.warning(
                "Truncated response but the request messages were not found in "
                "the call signature; returning the partial unchanged."
            )
            return res

        combined = self._text_of(res)
        thinking = self._thinking_of(res)
        for rnd in range(1, self._CONTINUE_ROUNDS + 1):
            convo = list(messages) + self._resume_turns(combined, thinking)
            try:
                nxt = await self._base_model(convo, **{
                    k: v for k, v in kwargs.items() if k != "messages"
                })
            except Exception as e:  # noqa: BLE001
                logger.warning(
                    "Continuation round %d failed (%s); returning the %d chars "
                    "already generated rather than losing them.",
                    rnd, type(e).__name__, len(combined),
                )
                break
            self._accumulate_usage(getattr(nxt, "usage", None))
            piece = self._text_of(nxt)
            if not piece:
                # Still nothing but thinking. Carry the NEW reasoning forward
                # too -- it is another budget's worth of work, and dropping it
                # makes the next round start from nothing again.
                more = self._thinking_of(nxt)
                if more and self._truncated(nxt) and rnd < self._CONTINUE_ROUNDS:
                    thinking = f"{thinking}\n{more}" if thinking else more
                    logger.info(
                        "Continuation round %d was reasoning-only (+%d chars of "
                        "thinking, %d total); carrying it forward.",
                        rnd, len(more), len(thinking),
                    )
                    continue
                logger.warning(
                    "Continuation round %d came back with no answer text "
                    "(thinking=%d chars); keeping %d chars.",
                    rnd, len(more), len(combined),
                )
                break
            combined += piece
            logger.info(
                "Continued a truncated response (round %d): +%d chars, %d total.",
                rnd, len(piece), len(combined),
            )
            if not self._truncated(nxt):
                res.content = [TextBlock(type="text", text=combined)]
                meta = dict(getattr(res, "metadata", None) or {})
                meta["finish_reason"] = "stop"
                meta["continued_rounds"] = rnd
                res.metadata = meta
                return res
        else:
            logger.warning(
                "Still truncated after %d continuation rounds; returning %d "
                "chars and letting the caller judge it.",
                self._CONTINUE_ROUNDS, len(combined),
            )

        # Ran out of rounds, or a round failed: hand back everything gathered so
        # far, still flagged truncated so downstream keeps treating it as partial.
        if combined:
            res.content = [TextBlock(type="text", text=combined)]
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
