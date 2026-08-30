"""Drive the REAL `_EditSession` with a local agent as the model.

`RTLEditor.chat` runs an agentscope ReAct loop against the OpenAI gateway. What
is under test here is not that loop: it is the EDITOR -- its tools, its evidence,
its staging discipline and its budget. So the session is driven directly and the
ReAct loop is hand-rolled over `AgentPort`, one tool call per rendezvous round.

Nothing about the session is stubbed. `commit()` writes, lints, checks drivers,
runs the whole suite through `SpecflowReviewer` and re-decides the frozen 90 --
the same code path `RTLEditor` would take.

WHAT IS DELIBERATELY WITHHELD: the golden RTL. The agent sees the requirement
text, the check's own complaint, the recorded boundary trace, the VCD internals
of the suspect blocks, and the candidate's source. It never sees the reference
design, and no verdict it is shown was computed against one.
"""
import argparse
import json
import shutil
import sys
import time
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, "/home/user/Veri-Sure")
sys.path.insert(0, "/home/user/Veri-Sure/docs/evidence")

S = Path("/tmp/claude-0/-home-user-Veri-Sure/12bb865e-7a51-5506-b55a-e5ac7cf72a4a/scratchpad")

ap = argparse.ArgumentParser()
ap.add_argument("--run", required=True, help="a directory loop_run.py built")
ap.add_argument("--name", default="edit1")
ap.add_argument("--trials", type=int, default=6)
ap.add_argument("--rounds", type=int, default=40, help="tool calls, not trials")
ap.add_argument("--timeout", type=float, default=3600.0)
ap.add_argument("--include", default="")
ap.add_argument("--script", default="",
                help="JSON file of tool calls to replay INSTEAD of asking an "
                     "agent -- a plumbing smoke test, not an experiment")
a = ap.parse_args()

RUN = Path(a.run)
IO = S / "asrt" / a.name / "io"
IO.mkdir(parents=True, exist_ok=True)

from eda_agent.explain import load_requirement_views       # noqa: E402
from eda_agent.rtl_editor import _EditSession              # noqa: E402
from eda_agent.specflow_node import (SpecflowReviewer,     # noqa: E402
                                     _frozen_oracles)
from specflow.model_io import AgentPort                    # noqa: E402

contract = json.loads((RUN / "contract.json").read_text())
cov = json.loads((RUN / "specflow/coverage_model.json").read_text())
incs = [p for p in a.include.split(",") if p]

reviewer = SpecflowReviewer(
    built=SimpleNamespace(suite_dir=RUN / "suite",
                          refmodel_path=RUN / "ref_model.py",
                          bins=cov.get("bins") or []),
    hdl_toplevel="i2c_master_bit_ctrl", output_dir=RUN,
    include_dirs=incs,
    oracles=_frozen_oracles(RUN), contract=contract)

print("baseline run ...", flush=True)
t0 = time.time()
is_pass, failing, sim_output = reviewer.review()
print(f"  {time.time()-t0:.0f}s  pass={is_pass}  failing testpoints={failing}",
      flush=True)

session = _EditSession(
    tb_path=None, rtl_path=str(RUN / "rtl.sv"), output_dir=str(RUN),
    last_mismatch_cnt=failing, sim_reviewer=reviewer, max_trials=a.trials,
    requirements=load_requirement_views(RUN, contract), contract=contract)
session._pull_req_results()

TOOLS = {
    "list_failing_requirements": lambda: session.list_failing_requirements(),
    "explain": lambda req_uid: session.explain(req_uid),
    "focus": lambda req_uid: session.focus(req_uid),
    "list_suspect_blocks": lambda: session.list_suspect_blocks(),
    "read_block": lambda block_id: session.read_block(block_id),
    "replace_block": lambda block_id, new_code: session.stage_replace(block_id, new_code),
    "add_block": lambda anchor_id, code: session.stage_add(anchor_id, code),
    "remove_block": lambda block_id: session.stage_remove(block_id),
    "check_staged": lambda: session.check_staged(),
    "discard_staged": lambda: session.discard_staged(),
    "commit": lambda: session.commit(),
}

RULES = """You are debugging a Verilog design against a frozen set of checks written
from its specification. You do NOT have the specification and you do NOT have a
reference design. What you have is the requirement each check came from, in the
requirement's own words, and the evidence below.

Reply with EXACTLY ONE JSON object and nothing else. No prose, no fences.

  {"tool": "<name>", "args": {...}}      call one tool
  {"done": "<one sentence>"}             stop

TOOLS

  list_failing_requirements()      what the last run decided. FAILING and
                                   UNCOVERED in full; passing as a count.
                                   START HERE.
  explain(req_uid)                 the span this requirement governs, the
                                   boundary ports across it, the suspect
                                   blocks' INTERNAL signals from the waveform,
                                   the transitions, and what single-value
                                   perturbation would have satisfied the check.
                                   When none would, the defect is TEMPORAL.
  focus(req_uid)                   slice the design from THAT requirement's
                                   ports. Do this before reading blocks.
  list_suspect_blocks()            the current slice.
  read_block(block_id)             its source, from the STAGED buffer.

  replace_block(block_id, new_code)   FREE. Stages an edit. No compile, no run.
  add_block(anchor_id, code)          FREE. anchor_id is a block id, or
                                      "endmodule" for the module end.
  remove_block(block_id)              FREE.
  check_staged()                      FREE and unlimited: syntax and driver
                                      checks on the batch. No simulation.
  discard_staged()                    FREE. Back to the last accepted RTL.

  commit()                            THE TRIAL. Compiles and runs the WHOLE
                                      suite. Improved -> latched. Not improved
                                      -> the accepted RTL is untouched AND YOUR
                                      STAGED EDITS SURVIVE, so adjust them
                                      rather than starting over.

Staging is free; only commit costs a trial. Settle syntax and drivers with
check_staged() before spending one. An UNCOVERED requirement is not an
accusation against the design and no edit discharges it -- do not chase one.
"""


def render(obs: str) -> str:
    return (RULES
            + f"\n\nTRIALS USED {session.action_calls} of {session.max_trials}."
            + f"  check_staged calls {session.check_calls}."
            + f"  staged: {'yes' if session.staged_rtl is not None else 'no'}\n\n"
            + "LAST OBSERVATION\n" + obs
            + "\n\nReply with ONE JSON object.\n")


port = AgentPort(root=IO, timeout=a.timeout)
scripted = json.loads(Path(a.script).read_text()) if a.script else None
obs = json.dumps(session.list_failing_requirements(), indent=1)[:12000]
log = []
for rnd in range(a.rounds):
    if scripted is not None:
        if rnd >= len(scripted):
            break
        reply = json.dumps(scripted[rnd])
        render(obs)   # built anyway, so a prompt-shape error still surfaces
    else:
        reply = port.complete(stage="edit", round_=rnd, prompt=render(obs))
    try:
        call = json.loads(reply.strip().removeprefix("```json").removeprefix("```")
                          .removesuffix("```").strip())
    except ValueError as exc:
        obs = f"Your reply was not one JSON object ({exc}). Send exactly one."
        log.append({"round": rnd, "error": "unparseable"})
        continue
    if "done" in call:
        print(f"round {rnd}: DONE -- {call['done']}", flush=True)
        log.append({"round": rnd, "done": call["done"]})
        break
    name, args = call.get("tool"), call.get("args") or {}
    fn = TOOLS.get(name)
    if fn is None:
        obs = f"No tool named {name!r}. Available: {sorted(TOOLS)}"
        log.append({"round": rnd, "error": f"unknown tool {name}"})
        continue
    t = time.time()
    try:
        out = fn(**args)
    except TypeError as exc:
        out = {"error": f"wrong arguments for {name}: {exc}"}
    except Exception as exc:  # noqa: BLE001
        out = {"error": f"{name} raised {exc!r}"}
    dt = time.time() - t
    print(f"round {rnd}: {name}({', '.join(args)})  {dt:.0f}s", flush=True)
    log.append({"round": rnd, "tool": name, "args": {k: str(v)[:200] for k, v in args.items()},
                "seconds": round(dt, 1),
                "result": json.loads(json.dumps(out, default=str))
                if not isinstance(out, str) else out[:4000]})
    if name == "commit":
        session._pull_req_results()
    obs = (out if isinstance(out, str) else json.dumps(out, indent=1, default=str))[:14000]
    if session.action_calls >= session.max_trials:
        obs += ("\n\nTRIAL BUDGET SPENT. No further commit is possible. "
                "Reply {\"done\": \"...\"} saying what you found.")

final = session.list_failing_requirements()
summary = {
    "trials_used": session.action_calls, "check_staged_calls": session.check_calls,
    "rounds": len(log),
    "failing_before": [r["req_uid"] for r in json.loads(
        (RUN / "surface.json").read_text())["failing"]] if (RUN / "surface.json").exists() else None,
    "failing_after": [r["req_uid"] for r in final["failing"]],
    "uncovered_after": len(final["uncovered"]),
    "passing_after": final["passing_count"],
}
print("\n" + json.dumps(summary, indent=1))
json.dump({"summary": summary, "log": log},
          open(S / "asrt" / a.name / "trajectory.json", "w"), indent=1, default=str)
shutil.copy(RUN / "rtl.sv", S / "asrt" / a.name / "final_rtl.v")
