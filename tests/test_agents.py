"""`clear_memory_safely` must clear before it returns, not eventually.

Every `chat`/`align`/`ablation_chat` entry point in `eda_agent` calls
`self.reset()` and then, still synchronously, goes straight on to the turn
that adds the next message -- see `ArchitectAgent.chat`, `RTLGenerator.chat`,
`AsserterAgent.chat`, `BooleanProoferAgent.chat`, `RTLEditor.chat`,
`TBEditor.chat`. If `reset()` only *schedules* the clear rather than doing it,
that schedule loses the race against every one of those call sites: nothing
yields to the event loop between `reset()` returning and the turn's opening
message landing in `agentscope`'s memory (`InMemoryMemory.add()` is a plain
list append with no genuine suspension point, and it is the first thing
`ReActAgent.reply()` does), so the deferred clear fires later than intended
-- at the first REAL await, which is the network call -- and wipes the
message the request in flight was just built from.
"""

from __future__ import annotations

import asyncio

from agentscope.memory import InMemoryMemory
from agentscope.message import Msg

from eda_agent.agents import clear_memory_safely


class _Agent:
    """Just enough of `ReActAgent` for `clear_memory_safely` to act on."""


def test_clear_memory_safely_clears_synchronously() -> None:
    """No event-loop turn should be needed for the clear to take effect.

    The old implementation scheduled `InMemoryMemory.clear()` with
    `loop.create_task()` when a loop was already running, and returned
    immediately -- so `.content` was still the OLD content right after this
    call returned, and only became empty once something else yielded to the
    loop. That is the bug: this assertion is the one property that rules it
    out regardless of what asyncio schedules next.
    """

    async def scenario() -> None:
        agent = _Agent()
        agent.memory = InMemoryMemory()
        await agent.memory.add(Msg("user", "old turn", role="user"))

        clear_memory_safely(agent)

        assert agent.memory.content == [], (
            "clear_memory_safely returned without clearing -- the clear "
            "was merely scheduled, which is the race this test exists to "
            "catch"
        )

    asyncio.run(scenario())


def test_reset_then_add_survives_whatever_asyncio_schedules_next() -> None:
    """The exact shape of every real call site, replayed end to end.

    `reset()` runs, and the very next thing that happens -- still inside the
    same coroutine, nothing has awaited anything real yet -- is the turn's
    opening message going into memory. A deferred clear task, if one were
    still pending from `reset()`, gets its first chance to run at the
    `asyncio.sleep(0)` below (standing in for the turn's first genuine
    network await). The opening message must still be there afterward.
    """

    async def scenario() -> None:
        agent = _Agent()
        agent.memory = InMemoryMemory()
        await agent.memory.add(Msg("user", "stale prior turn", role="user"))

        clear_memory_safely(agent)
        await agent.memory.add(Msg("user", "this turn's prompt", role="user"))

        # Give any leftover deferred task every chance to run.
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        texts = [m.get_text_content() for m in agent.memory.content]
        assert texts == ["this turn's prompt"], (
            f"memory after reset()+add was {texts!r} -- a deferred clear "
            "fired AFTER the new turn's message was added and wiped it"
        )

    asyncio.run(scenario())


def test_clear_memory_safely_tolerates_a_memory_with_no_content_attribute() -> None:
    """A `MemoryBase` without `.content` must not raise -- best effort only.

    Nothing in this package constructs such a memory today, but
    `clear_memory_safely` is not typed to rule it out, so it must degrade to
    the old best-effort async clear rather than crash the caller's `reset()`.
    """

    class _NoContentMemory:
        def __init__(self) -> None:
            self.cleared = False

        async def clear(self) -> None:
            self.cleared = True

    async def scenario() -> None:
        agent = _Agent()
        agent.memory = _NoContentMemory()
        clear_memory_safely(agent)  # must not raise
        await asyncio.sleep(0)
        assert agent.memory.cleared

    asyncio.run(scenario())


def test_clear_memory_safely_tolerates_no_memory_and_no_clear() -> None:
    """Defensive no-ops: neither absence should raise."""
    agent = _Agent()
    agent.memory = None
    clear_memory_safely(agent)  # must not raise

    class _NoClearMemory:
        pass

    agent.memory = _NoClearMemory()
    clear_memory_safely(agent)  # must not raise
