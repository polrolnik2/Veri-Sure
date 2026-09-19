"""Does this gateway cache a TOOL-CALLING conversation as it grows?

    python benchmarks/cache_probe.py gpt-5-mini gpt-5.6-luna

`cache_report.py` reads what a RUN spent. This asks the prior question -- whether
the gateway caches this model in this shape at all -- and it takes four small
calls rather than a run. It exists because that question was open while the debug
loop was spending 46.1M input tokens per run against 10.8M for every specflow
stage combined, and nothing on disk could answer it.

Measured 2026-08-27 against llm.sdc.siemens.cloud:

    gpt-5-mini    call 0  2151 in     0 cached   (cold)
                  call 1  2753      2048   74.4%
                  call 2  3355      2688   80.1%
                  call 3  3957      3328   84.1%   +640 = 5 x 128

    gpt-5.6-luna  call 0  2151         0    0.0%  (cold)
                  call 1  2753      2148   78.0%
                  call 2  3355      2750   82.0%
                  call 3  3957      3352   84.7%

Both cache, and the cached region GROWS with the conversation. mini moves in
128-token increments; Luna caches the whole prior prefix. The uncached remainder
is constant at ~605 tokens -- exactly the newly appended turn -- so the rate goes
to ~100% as the conversation lengthens, which is the debug loop's shape.


The debug loop's shape: a large stable head (system + tool schema), then an
append-only conversation of tool_use / tool_result pairs. Every request re-sends
everything before it, so from call 2 onward almost the whole prompt should be a
cache hit -- IF the gateway caches this model in this shape at all.
"""
import json
import pathlib
import sys

env = {}
for line in pathlib.Path("/home/user/Veri-Sure/.env.local").read_text().splitlines():
    if "=" in line and not line.strip().startswith("#"):
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip().strip('"').strip("'")

from openai import OpenAI  # noqa: E402 -- after the env file is read
client = OpenAI(api_key=env["OPENAI_API_KEY"], base_url=env["OPENAI_BASE_URL"],
                timeout=180)

SYS = ("You repair a Python reference model of a hardware design so that it "
       "satisfies a set of requirement checks. " + (
       "Work one edit at a time; name the method you are changing and why; "
       "never widen a check to make it pass; read before you write. ") * 40)

def tool(n):
    return {"type": "function", "function": {
        "name": f"_tool_{n}",
        "description": (f"{n}. " + "Answers narrowly and says what it cut. " * 12),
        "parameters": {"type": "object", "properties": {
            "req_uid": {"type": "string", "description": "e.g. REQ-0000"},
            "detail": {"type": "string", "description": "what to look at"}},
            "required": ["req_uid"]}}}

TOOLS = [tool(n) for n in ("list_assertions", "explain", "run_assertion",
                           "read_model", "replace_method", "add_stimulus")]

RESULT = "edge N: cmd_ack=0 scl_oen=1 sda_oen=1 busy=0; " * 25


def run(model, rounds=4):
    msgs = [{"role": "system", "content": SYS},
            {"role": "user", "content": "Begin. Say only OK."}]
    print(f"\n=== {model}")
    print(f"{'call':>4} {'input':>8} {'cached':>8} {'rate':>7}  {'msgs':>5}")
    for i in range(rounds):
        r = client.chat.completions.create(
            model=model, messages=msgs, tools=TOOLS,
            max_completion_tokens=2000)
        u = r.usage
        c = getattr(getattr(u, "prompt_tokens_details", None), "cached_tokens", 0) or 0
        rate = f"{100*c/u.prompt_tokens:5.1f}%" if u.prompt_tokens else "    -"
        print(f"{i:>4} {u.prompt_tokens:>8} {c:>8} {rate:>7}  {len(msgs):>5}")
        cid = f"call_{i}"
        msgs.append({"role": "assistant", "content": None, "tool_calls": [
            {"id": cid, "type": "function", "function": {
                "name": "_tool_run_assertion",
                "arguments": json.dumps({"req_uid": f"REQ-000{i}"})}}]})
        msgs.append({"role": "tool", "tool_call_id": cid,
                     "content": f"{i} " + RESULT})
        msgs.append({"role": "user", "content": f"Continue, step {i}. Say OK."})


for m in sys.argv[1:] or ["gpt-5-mini"]:
    try:
        run(m)
    except Exception as exc:
        print(f"\n=== {m}\n  FAILED: {type(exc).__name__}: {str(exc)[:200]}")
