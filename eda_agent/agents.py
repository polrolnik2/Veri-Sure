from __future__ import annotations

import json
from typing import Any, AsyncGenerator

from agentscope.agent import ReActAgent
from agentscope.message import ToolUseBlock
from agentscope.tool import Toolkit, ToolResponse


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
