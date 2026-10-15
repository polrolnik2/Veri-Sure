from __future__ import annotations

import json
import re
from typing import Any, AsyncGenerator

from agentscope.agent import ReActAgent
from agentscope.message import ToolUseBlock
from agentscope.tool import Toolkit, ToolResponse

# Fullwidth vertical bar '｜' (U+FF5C) — the separator observed in leaked
# chat-template/tool-call special tokens from a DeepSeek-family model served
# via OpenRouter (e.g. "<｜DSML｜tool_calls>...<｜DSML｜invoke name=...>").
# When the upstream model/gateway fails to emit a structured tool call, this
# literal template text lands in the assistant message's plain `content`
# field instead — ReActAgent cannot distinguish it from a genuine answer, so
# it silently becomes the "final" response for that turn, wasting it. This is
# a serving-layer artifact (not something any local formatter choice
# controls: formatters only shape the OUTBOUND request; response/tool-call
# parsing happens entirely inside agentscope's model client, with zero
# model-family branching) affecting every agent in this package equally,
# since all of them (RTLEditor/Debugger, TBEditor, ArchitectAgent,
# BooleanProoferAgent, AsserterAgent, RTLGenerator, TBGenerator) construct
# their SafeReActAgent via the identical make_openai_model/make_formatter
# pair. Fixed once, here, benefits all of them.
_LEAK_PIPE = "｜"
_LEAK_KEYWORD_RE = re.compile(
    rf"{_LEAK_PIPE}[^\n]{{0,60}}(tool_calls|invoke|parameter)", re.IGNORECASE,
)


def _looks_like_leaked_tool_call(content: str) -> bool:
    """True iff `content` looks like leaked chat-template markup rather than
    a genuine natural-language (or SystemVerilog) answer.

    Deliberately conservative: the fullwidth pipe essentially never occurs in
    legitimate text or SV (which may contain the ordinary ASCII bitwise-or
    `|`, never `｜`), so requiring it to co-occur near a tool-call-shaped
    keyword keeps false positives near zero — a stray unicode character
    alone is not enough to trip this.
    """
    if not content or _LEAK_PIPE not in content:
        return False
    return bool(_LEAK_KEYWORD_RE.search(content))


def _leak_repair_response(response: str) -> ToolResponse | None:
    """If `response` looks like a leaked tool-call, return the corrective
    "not really finished" ToolResponse; otherwise None.

    The {"success": False, "response_msg": None} shape is agentscope's own
    existing "the conversation is NOT actually finished" signal (used today
    by ReActAgent's structured-output ValidationError branch) — it does not
    terminate the ReAct loop; it's added to memory as an ordinary tool
    result, so the model sees the corrective text on its very next turn. Same
    idiom GuidingToolkit.call_tool_function already uses for a different
    malformed-model-action class (hallucinated tool names).

    Re-prompting (not regex-extracting the leaked call) is deliberate: the
    exact leaked token spelling is a snapshot of one serving-layer bug, not a
    stable contract, and a single confirmed occurrence doesn't yet justify
    parsing complexity tied to today's exact shape. If recurrence with a
    stable, parseable shape is later confirmed, extraction could be layered
    in as a fallback tried before this re-prompt — not built now.
    """
    if not _looks_like_leaked_tool_call(response):
        return None
    return ToolResponse(
        content=[{
            "type": "text",
            "text": (
                "ToolError: your previous response contained garbled special-token/"
                "template text instead of a valid tool call or a plain answer (a "
                "serving-layer formatting glitch, not something the user sent). "
                "Re-issue your intended action using the actual tool-call mechanism "
                "(not by writing markup/tags in your reply text). If you intended to "
                "finish, call generate_response again with a plain-text response."
            ),
        }],
        metadata={"success": False, "response_msg": None},
    )


class GuidingToolkit(Toolkit):
    """Toolkit that turns an unknown-tool call into actionable guidance.

    When a model invents a tool (weaker models routinely hallucinate e.g.
    ``read_file``), the base toolkit returns a bare
    ``FunctionNotFoundError: Cannot find the function named X``. That gives the
    model nothing to correct toward, so it loops, inflating context until the
    request exceeds the model's window. Instead, list the actual available tools
    so the model re-issues a valid call and closes the loop fast. We do **not**
    add aliases for hallucinated names — that would entrench the bad behaviour.
    """

    async def call_tool_function(  # type: ignore[override]
        self, tool_call: ToolUseBlock
    ) -> AsyncGenerator[ToolResponse, None]:
        # The ReActAgent does ``await toolkit.call_tool_function(call)`` and then
        # iterates the returned async generator, so this coroutine must *return*
        # an async generator (not itself be one).
        if tool_call["name"] in self.tools:
            return await super().call_tool_function(tool_call)

        available = ", ".join(sorted(self.tools))
        text = (
            f"ToolError: '{tool_call['name']}' is not an available tool and "
            f"was not executed. Available tools: {available}. "
            "Re-issue your request using exactly one of these tool names; "
            "do not invent tool names."
        )

        async def _guidance() -> AsyncGenerator[ToolResponse, None]:
            yield ToolResponse(content=[{"type": "text", "text": text}])

        return _guidance()


class SafeReActAgent(ReActAgent):
    """ReActAgent with a more forgiving generate_response tool.

    Some models occasionally call `generate_response` with a non-string payload
    (e.g. a dict). The base implementation passes it through to `ToolResponse`,
    which then raises a validation error. This subclass coerces to a string so
    the agent can always terminate cleanly.
    """

    def generate_response(self, response: str, **kwargs: Any) -> ToolResponse:  # type: ignore[override]
        """Finish the conversation with a plain string response."""
        if response is None:
            # A model call with response=null (JSON null; runtime doesn't
            # enforce the `str` type hint, so this reaches here rather than
            # raising) is NOT a valid final answer. The `isinstance` coercion
            # below would silently stringify it via json.dumps(None) ==
            # "null" and let the conversation terminate as if that were real
            # content. Confirmed live: a downstream Coder call whose prompt
            # was built from exactly this 4-character string produced a
            # placeholder module instead of real RTL ("No contract JSON...
            # previous response was 'null' which failed parsing") -- the
            # vestigial-glue structural check caught the placeholder, but
            # only after an entire glue-generation attempt was burned on it.
            # Treat it the same way `_leak_repair_response` treats garbled
            # tool-call leakage: a corrective re-prompt, not a silently
            # accepted answer.
            return ToolResponse(
                content=[{
                    "type": "text",
                    "text": (
                        "ToolError: generate_response was called with response=null. "
                        "This is not a valid final answer. Call generate_response "
                        "again with your actual answer as the response argument."
                    ),
                }],
                metadata={"success": False, "response_msg": None},
            )
        if not isinstance(response, str):
            try:
                response = json.dumps(response, ensure_ascii=False)
            except Exception:  # noqa: BLE001
                response = str(response)
        repair = _leak_repair_response(response)
        if repair is not None:
            return repair
        return super().generate_response(response=response, **kwargs)


def clear_memory_safely(agent: ReActAgent) -> None:
    """Clear AgentScope memory NOW, not on the next network await.

    The previous implementation scheduled `InMemoryMemory.clear()` with
    `loop.create_task(ret)` when a loop was already running -- to dodge a
    "coroutine was never awaited" warning -- and returned immediately
    without the clear having happened yet. That is a real race, not a
    cosmetic one, and it is live on every call site in this package: every
    `chat`/`align`/`ablation_chat` entry point calls `self.reset()` and then,
    still synchronously, proceeds to the turn that adds the next message.

    Trace it through agentscope 1.0.7 itself
    (`agentscope/memory/_in_memory_memory.py`,
    `agentscope/agent/_react_agent.py::reply`): `InMemoryMemory.add()` and
    `.clear()` are both `async def` for interface conformance only -- each is
    a plain list operation with no genuine suspension point -- and
    `ReActAgent.reply()` does `await self.memory.add(msg)` as its very first
    line. So nothing yields control to the event loop between `reset()`
    returning and the turn's opening message landing in memory; the FIRST
    real suspension in the whole call is `_reasoning()`'s
    `await self.model(...)`. That is exactly when a deferred clear task
    finally gets to run -- after the opening message was added, not before --
    so it wipes the very message the request in flight was just built from.
    Every iteration after the first (anything that calls a tool, which is
    the normal case for `RTLEditor`/`TBEditor`) then reasons with that
    message already gone from its own history, and sends a message list
    that no longer extends the previous request's -- the exact prefix break
    `tests/test_prompt_prefix.py` exists to catch, one layer below where
    that suite looks, and invisible to it because that suite builds its
    message lists by hand rather than through a live agent turn.

    The fix is to never create the coroutine at all. Every memory this
    package constructs is `InMemoryMemory`, which exposes a plain `.content`
    list -- the same attribute `RefModelEditor.restore_memory` already
    assigns directly and synchronously elsewhere in this codebase -- so set
    it directly. No task, no race, and no warning, because nothing async is
    ever invoked.
    """
    mem = getattr(agent, "memory", None)
    if mem is None:
        return
    if hasattr(mem, "content"):
        mem.content = []
        return

    # A MemoryBase implementation with no `.content` (not used anywhere in
    # this package today, but `clear_memory_safely` is not typed to rule it
    # out): fall back to the best-effort async clear rather than doing
    # nothing. Still races the same way for THAT implementation, but no
    # worse than before this fix.
    clear = getattr(mem, "clear", None)
    if clear is None:
        return
    try:
        ret = clear()
    except TypeError:
        # Some memory implementations may require args; ignore.
        return
    if hasattr(ret, "__await__"):
        try:
            loop = __import__("asyncio").get_running_loop()
            loop.create_task(ret)  # type: ignore[arg-type]
        except RuntimeError:
            # No running loop; run it to completion.
            __import__("asyncio").run(ret)  # type: ignore[arg-type]
