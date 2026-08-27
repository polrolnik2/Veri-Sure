"""Does /v1/responses cache the same growing tool conversation?

The debug loop is on this surface -- `reasoning` is rejected on chat -- and the
chat probe that showed 78-85% says nothing about it.
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

SYS = ("You repair a Python reference model of a hardware design. " + (
       "Work one edit at a time; name the method you change and why; never "
       "widen a check to make it pass; read before you write. ") * 40)

TOOLS = [{"type": "function", "name": f"_tool_{n}",
          "description": (f"{n}. " + "Answers narrowly and says what it cut. " * 12),
          "parameters": {"type": "object", "properties": {
              "req_uid": {"type": "string"}, "detail": {"type": "string"}},
              "required": ["req_uid"]}}
         for n in ("list_assertions", "explain", "run_assertion",
                   "read_model", "replace_method", "add_stimulus")]

ROW = "edge N: cmd_ack=0 scl_oen=1 sda_oen=1 busy=0; " * 25


def run(model, effort, store, rounds=4):
    items = [{"role": "system", "content": SYS},
             {"role": "user", "content": "Begin. Say only OK."}]
    print(f"\n=== {model}  effort={effort}  store={store}")
    print(f"{'call':>4} {'input':>8} {'cached':>8} {'rate':>7}  {'items':>6}")
    for i in range(rounds):
        kw = {"model": model, "input": items, "tools": TOOLS,
              "max_output_tokens": 2000, "store": store}
        if effort:
            kw["reasoning"] = {"effort": effort, "summary": "auto"}
        r = client.responses.create(**kw)
        u = r.usage
        det = getattr(u, "input_tokens_details", None)
        c = (getattr(det, "cached_tokens", 0) or 0) if det else 0
        n = u.input_tokens
        print(f"{i:>4} {n:>8} {c:>8} "
              f"{f'{100*c/n:5.1f}%' if n else '    -':>7}  {len(items):>6}")
        cid = f"call_{i}"
        items.append({"type": "function_call", "call_id": cid,
                      "name": "_tool_run_assertion",
                      "arguments": json.dumps({"req_uid": f"REQ-000{i}"})})
        items.append({"type": "function_call_output", "call_id": cid,
                      "output": f"{i} " + ROW})
        items.append({"role": "user", "content": f"Step {i}. Say OK."})


model = sys.argv[1] if len(sys.argv) > 1 else "gpt-5.6-luna"
for effort, store in ((None, False), ("medium", False), ("medium", True)):
    try:
        run(model, effort, store)
    except Exception as exc:
        print(f"\n=== effort={effort} store={store}\n  FAILED: "
              f"{type(exc).__name__}: {str(exc)[:160]}")
