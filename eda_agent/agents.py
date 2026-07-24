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
    """Clear AgentScope memory without 'coroutine was never awaited' warnings."""
    mem = getattr(agent, "memory", None)
    if mem is None:
        return
    clear = getattr(mem, "clear", None)
    if clear is None:
        return
    try:
        ret = clear()
    except TypeError:
        # Some memory implementations may require args; ignore.
        return

    # In AgentScope 1.0.7, InMemoryMemory.clear() is async; schedule it if needed.
    if hasattr(ret, "__await__"):
        try:
            loop = __import__("asyncio").get_running_loop()
            loop.create_task(ret)  # type: ignore[arg-type]
        except RuntimeError:
            # No running loop; run it to completion.
            __import__("asyncio").run(ret)  # type: ignore[arg-type]
