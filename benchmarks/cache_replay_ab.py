"""A/B: does re-deriving tool arguments instead of replaying them cost the cache?

Measured 2026-08-27, gpt-5.6-luna on /v1/responses:

    A -- replay      43.4%  ->  63.8%  ->  73.4%
    B -- re-derive   43.4%  ->  27.7%  ->  46.9%

B collapses to 1692 cached at call 2 -- the system+user head and nothing more --
the moment an earlier tool call's arguments come back in a different key order.
Roughly 26 points, widening with the conversation. A first attempt varying only
JSON SPACING showed no difference at all: four bytes is absorbed, and it took
reordering to make the break visible.

That is what `model.ByteReplayFormatter` prevents.


A -- REPLAY: every call sends the same argument bytes for a given tool call.
B -- RE-DERIVE: each call re-serializes the EARLIER calls' arguments a little
     differently (spacing flips), which is what a non-deterministic encoder or a
     randomized map iteration produces.

Each pass gets its own system prompt so it cannot hit the other's cache.
"""
import json
import pathlib
import sys

env = {}
for line in pathlib.Path("/home/user/Veri-Sure/.env.local").read_text().splitlines():
    if "=" in line and not line.strip().startswith("#"):
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip().strip('"').strip("'")

from openai import OpenAI  # noqa: E402

client = OpenAI(api_key=env["OPENAI_API_KEY"], base_url=env["OPENAI_BASE_URL"],
                timeout=300)

BASE = ("You repair a Python reference model of a hardware design. " + (
        "Work one edit at a time; name the method you change and why; never "
        "widen a check to make it pass; read before you write. ") * 40)

TOOLS = [{"type": "function", "name": f"_tool_{n}",
          "description": (f"{n}. " + "Answers narrowly and says what it cut. " * 12),
          "parameters": {"type": "object", "properties": {
              "req_uid": {"type": "string"}, "detail": {"type": "string"}},
              "required": ["req_uid"]}}
         for n in ("list_assertions", "explain", "run_assertion", "read_model")]

ROW = "edge N: cmd_ack=0 scl_oen=1 sda_oen=1 busy=0; " * 25


def args_for(i, call_index, rederive):
    """A BIG payload with many keys, so a re-derivation that reorders them
    differs unmistakably rather than by four spaces."""
    keys = [(f"k{n:02d}", f"value {n} for REQ-000{i} " * 4) for n in range(40)]
    keys.append(("req_uid", f"REQ-000{i}"))
    if rederive and call_index % 2:
        keys = list(reversed(keys))          # what randomized iteration gives
    return json.dumps(dict(keys))


def run(label, rederive, rounds=4):
    sysmsg = BASE + f"\n\nSession: {label}."
    calls = []          # (i, call_id)
    print(f"\n=== {label}")
    print(f"{'call':>4} {'input':>8} {'cached':>8} {'rate':>7}")
    for c in range(rounds):
        items = [{"role": "system", "content": sysmsg},
                 {"role": "user", "content": "Begin. Say only OK."}]
        for i, cid in calls:
            items.append({"type": "function_call", "call_id": cid,
                          "name": "_tool_run_assertion",
                          "arguments": args_for(i, c, rederive)})
            items.append({"type": "function_call_output", "call_id": cid,
                          "output": f"{i} " + ROW})
            items.append({"role": "user", "content": f"Step {i}. Say OK."})
        r = client.responses.create(
            model="gpt-5.6-luna", input=items, tools=TOOLS,
            reasoning={"effort": "medium", "summary": "auto"},
            max_output_tokens=2000, store=False)
        u = r.usage
        det = getattr(u, "input_tokens_details", None)
        k = (getattr(det, "cached_tokens", 0) or 0) if det else 0
        n = u.input_tokens
        print(f"{c:>4} {n:>8} {k:>8} "
              f"{f'{100*k/n:5.1f}%' if n else '    -':>7}")
        calls.append((c, f"call_{c}"))


stamp = sys.argv[1] if len(sys.argv) > 1 else "x1"
run(f"A-replay-{stamp}", rederive=False)
run(f"B-rederive-{stamp}", rederive=True)
