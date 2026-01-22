from __future__ import annotations

import json
from typing import Any

from agentscope.agent import ReActAgent
from agentscope.tool import ToolResponse


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
