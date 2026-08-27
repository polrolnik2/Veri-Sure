"""The prefix must GROW, byte for byte, or prompt caching pays nothing.

Prompt caching here is automatic and prefix-based: the provider matches the
longest prefix it already holds. So the whole benefit rests on one property --
request N's serialized form is a byte-exact prefix of request N+1's -- and that
property is easy to break invisibly. Re-serializing a tool_use through a struct
that emits keys in a different order, clipping a result on turn 8 that went out
in full on turn 3, or building the tools array from a set all reprice everything
after the divergence as fresh tokens, silently.

Measured rather than sorted: every comparison below is on raw `json.dumps`
output with NO `sort_keys`, because sorting keys before comparing hides exactly
the defect this file exists to catch.
"""

from __future__ import annotations

import asyncio
import json

from agentscope.message import Msg, TextBlock, ToolResultBlock, ToolUseBlock

from eda_agent.model import make_formatter


def _ser(formatted):
    return [json.dumps(m, ensure_ascii=False) for m in formatted]


def _prefix_len(a, b):
    n = 0
    for x, y in zip(a, b):
        if x != y:
            break
        n += 1
    return n


def _turn():
    """A turn as the loop builds one: brief, tool call, tool result, brief."""
    msgs = [Msg("system", "SYS", "system"),
            Msg("user", "OPENING", "user")]
    yield list(msgs)
    for i in range(3):
        cid = f"c{i}"
        msgs.append(Msg("assistant",
                        [ToolUseBlock(type="tool_use", id=cid,
                                      name="_tool_run_oracle",
                                      input={"req_uid": f"REQ-000{i}",
                                             "rows": 12})],
                        "assistant"))
        yield list(msgs)
        msgs.append(Msg("system",
                        [ToolResultBlock(type="tool_result", id=cid,
                                         name="_tool_run_oracle",
                                         output=[TextBlock(type="text",
                                                           text="row " * 50)])],
                        "system"))
        yield list(msgs)
        msgs.append(Msg("user", f"CONTINUE {i}", "user"))
        yield list(msgs)


def test_every_request_is_a_byte_exact_prefix_of_the_next():
    fmt = make_formatter("gpt-5.6-luna")

    async def go():
        return [_ser(await fmt.format(m)) for m in _turn()]

    shots = asyncio.run(go())
    assert len(shots) > 5
    for i in range(1, len(shots)):
        kept = _prefix_len(shots[i - 1], shots[i])
        assert kept == len(shots[i - 1]), (
            f"request {i} diverges from request {i - 1} at message {kept}:\n"
            f"  was: {shots[i - 1][kept][:300]}\n"
            f"  now: {shots[i][kept][:300]}")
        assert len(shots[i]) > len(shots[i - 1]), "the prefix must GROW"


def test_a_tool_result_clips_the_same_way_every_time_it_is_sent():
    """The turn-8-vs-turn-3 hazard. A clip that depended on anything but the
    payload -- remaining budget, context size, how many results are already in
    the conversation -- would send a result in full early and clipped later, and
    every token after that point is a miss."""
    from eda_agent.refmodel_editor import TOOL_MAX_CHARS, _text

    payload = {"rows": [{"edge": i, "y": i % 2} for i in range(4000)]}
    first = _text(payload).content[0]["text"]
    for _ in range(5):
        assert _text(payload).content[0]["text"] == first
    assert len(first) <= TOOL_MAX_CHARS + 200, "the cap must actually engage"
    assert "characters cut" in first, "and it must say that it cut"


def test_a_payload_serializes_identically_twice():
    """Set iteration order is not stable across processes, and a set rendered
    into a payload would look fine in one run and reprice the whole suffix in
    the next. Everything the tools return has to come out of a list or a sorted
    view."""
    from specflow.refmodel.oracles import OracleResult

    from tests.test_refmodel_editor import _session

    s = _session()
    s._results = [OracleResult("REQ-0000", ok=False, edge=3, detail="d")]
    a = json.dumps(s.board(), ensure_ascii=False)
    b = json.dumps(s.board(), ensure_ascii=False)
    assert a == b


def test_tool_arguments_survive_parse_and_re_emit_in_ORDER():
    """We do NOT replay the API's bytes -- we re-emit them. This pins the
    property that actually matters.

    A gateway returns `function.arguments` as a compact JSON STRING. The SDK
    parses it, AgentScope holds it as a dict, and the formatter re-serializes it
    with `json.dumps` on every later call. So the bytes we send are ours, not
    the API's: `{"a":1}` goes out as `{"a": 1}`.

    That is harmless, because the provider caches on what WE send -- but only
    while the re-emission is DETERMINISTIC and order-preserving. In CPython it
    is: `json.loads` fills a dict in document order and `json.dumps` walks
    insertion order. In a language with randomized map iteration it is not, and
    the whole suffix would silently miss. Nothing enforces this; the test is
    what notices if it changes.
    """
    import json as _json

    wire = '{"req_uid":"REQ-0000","rows":12,"from_edge":3}'
    fmt = make_formatter("gpt-5.6-luna")
    msg = Msg("assistant",
              [ToolUseBlock(type="tool_use", id="c1", name="_tool_run_oracle",
                            input=_json.loads(wire))],
              "assistant")

    async def go():
        return await fmt.format([msg])

    blob = asyncio.run(go())[0]
    args = blob["tool_calls"][0]["function"]["arguments"]
    assert list(_json.loads(args)) == list(_json.loads(wire)), (
        "key ORDER changed across the round trip -- every request after the "
        "first tool call would be a cache miss")
    assert _json.loads(args) == _json.loads(wire), "the values must survive too"


def test_the_re_emission_is_stable_across_PROCESSES():
    """Hash randomisation is per-process, so a set anywhere on this path shows
    up only when the seed changes -- which never happens inside one test run."""
    import subprocess
    import sys

    prog = (
        "import asyncio,json;"
        "from agentscope.message import Msg,ToolUseBlock;"
        "from eda_agent.model import make_formatter;"
        "m=Msg('assistant',[ToolUseBlock(type='tool_use',id='c1',"
        "name='_tool_run_oracle',input=json.loads("
        "'{\"req_uid\":\"REQ-0000\",\"rows\":12,\"from_edge\":3}'))],'assistant');"
        "print(json.dumps(asyncio.run(make_formatter('x').format([m])),"
        "ensure_ascii=False))"
    )
    seen = set()
    for seed in ("0", "12345", "99999"):
        out = subprocess.run([sys.executable, "-c", prog], capture_output=True,
                             text=True, env={"PYTHONHASHSEED": seed,
                                             "PATH": "/usr/bin:/bin"},
                             check=True)
        seen.add(out.stdout)
    assert len(seen) == 1, "the formatted request differs between hash seeds"
