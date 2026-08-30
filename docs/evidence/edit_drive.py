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
ap.add_argument("--reuse-baseline", action="store_true",
                help="decide the frozen set on the recording `loop_run.py` "
                     "already wrote instead of re-running the whole suite for "
                     "a result that is already on disk")
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
                                     SpecflowStimulusStager,
                                     _frozen_oracles)
from specflow.model_io import AgentPort                    # noqa: E402

contract = json.loads((RUN / "contract.json").read_text())
cov = json.loads((RUN / "specflow/coverage_model.json").read_text())
incs = [p for p in a.include.split(",") if p]

# THE STIMULUS ROUTE. Without it an UNCOVERED requirement reaches the agent as a
# finding it cannot act on -- and `list_failing_requirements` says in its own
# note that `add_stimulus` "is the only route for an UNCOVERED one", so omitting
# the tool made the harness name a remedy it did not provide. Measured on run 5:
# that note was shown five times, the tool was absent, and 27 requirements
# stayed uncovered from first round to last.
#
# `AgentPort` IS the `Port` shape `model_port` wants, so the same rendezvous --
# the same agent -- answers the stimulus-generation prompt. No second model.
stager = SpecflowStimulusStager(
    run_dir=RUN, contract=contract, bins=cov.get("bins") or [],
    suite_dir=RUN / "suite", model_port=AgentPort(root=IO, timeout=a.timeout))

reviewer = SpecflowReviewer(
    built=SimpleNamespace(suite_dir=RUN / "suite",
                          refmodel_path=RUN / "ref_model.py",
                          bins=cov.get("bins") or []),
    hdl_toplevel="i2c_master_bit_ctrl", output_dir=RUN,
    include_dirs=incs, stager=stager,
    oracles=_frozen_oracles(RUN), contract=contract)

print("baseline ...", flush=True)
t0 = time.time()
if a.reuse_baseline:
    # `loop_run.py` has already simulated THIS rtl.sv against THIS suite and
    # left every `{tp}.trace.json` on disk. Re-running costs a full suite --
    # twenty minutes on the paced stimulus -- to recompute a result that is
    # already there. The failing count is read off the same records.
    reviewer.req_results = reviewer._decide_requirements()
    failing = sum(1 for p in sorted((RUN / "suite/results").glob("*.json"))
                  if not p.name.endswith(".trace.json")
                  and json.loads(p.read_text()).get("status") == "FAIL")
    is_pass = failing == 0
    # `review()` is what normally publishes this, and the reuse path skips it.
    # An EMPTY uncovered set is a refusal, not a waiver, so without this
    # `add_stimulus` would decline every request as "not currently uncovered".
    stager.uncovered = {u for u, (r, _t) in reviewer.req_results.items()
                        if getattr(r, "ok", None) is None}
else:
    is_pass, failing, sim_output = reviewer.review()
print(f"  {time.time()-t0:.0f}s  pass={is_pass}  failing testpoints={failing}",
      flush=True)

session = _EditSession(
    tb_path=None, rtl_path=str(RUN / "rtl.sv"), output_dir=str(RUN),
    last_mismatch_cnt=failing, sim_reviewer=reviewer, max_trials=a.trials,
    requirements=load_requirement_views(RUN, contract), contract=contract,
    stimulus_stager=stager)
session._pull_req_results()

TOOLS = {
    "list_failing_requirements": lambda: session.list_failing_requirements(),
    "explain": lambda req_uid: session.explain(req_uid),
    "focus": lambda req_uid: session.focus(req_uid),
    "list_suspect_blocks": lambda: session.list_suspect_blocks(),
    "read_block": lambda block_id: session.read_block(block_id),
    "replace_block": lambda block_id, new_code: session.stage_replace(block_id, new_code),
    "edit": lambda old_text, new_text: session.stage_edit(old_text, new_text),
    "add_block": lambda anchor_id, code: session.stage_add(anchor_id, code),
    "remove_block": lambda block_id: session.stage_remove(block_id),
    "check_staged": lambda: session.check_staged(),
    "discard_staged": lambda: session.discard_staged(),
    "add_stimulus": lambda req_uid, what_the_scenario_needs: session.add_stimulus(
        req_uid, what_the_scenario_needs),
    "commit": lambda: session.commit(),
}

def budget(payload, limit: int = 14000) -> str:
    """Fit an observation to `limit` WITHOUT cutting JSON in half.

    Slicing a serialised dict at a character count produces an unparseable
    fragment ending mid-string, which is a worse thing to hand a model than a
    shorter but complete object. Measured on round 0 of the first live run: the
    seeded `list_failing_requirements()` payload was cut inside REQ-0035's
    requirement text.

    So: strings slice (that is what they are), and structures SHED WHOLE
    ELEMENTS. For the failing-requirements payload the uncovered rows go first,
    because the agent is told to ignore them, and a note records what was
    dropped rather than letting the list look complete.
    """
    if isinstance(payload, str):
        return payload[:limit]
    text = json.dumps(payload, indent=1, default=str)
    if len(text) <= limit:
        return text
    # SHED DETAIL, NEVER THE IDENTIFIERS. This used to empty the `uncovered`
    # list and keep a count, on the reasoning that the agent was told to ignore
    # them. With `add_stimulus` wired that is exactly backwards: an uncovered
    # requirement is now actionable and its UID is the argument. MEASURED on run
    # 7 -- the run started to test `add_stimulus` -- the uncovered rows were
    # dropped in all three payloads, so the agent knew "28 uncovered" as a
    # number and could not name one, and the tool it had been given was
    # unusable. A uid list is a few hundred characters; a count is a dead end.
    if isinstance(payload, dict) and payload.get("uncovered"):
        rows = payload["uncovered"]
        payload = {**payload,
                   "uncovered": [r.get("req_uid") if isinstance(r, dict) else r
                                 for r in rows],
                   "note": (payload.get("note", "")
                            + "  [uncovered shown as UIDs only to fit; "
                              "explain(uid) says why each never fired and "
                              "add_stimulus(uid, ...) is the route]")}
        text = json.dumps(payload, indent=1, default=str)
        if len(text) <= limit:
            return text
    # THEN SHORTEN THE PROSE INSIDE THE ROWS, still keeping every row. A
    # requirement's text truncated to 140 characters still identifies it; a row
    # replaced by "<omitted: 9500 chars>" identifies nothing. The generic
    # fallback below does the second, and reached it because 19 failing rows of
    # full requirement text do not fit however the uncovered half is encoded.
    if isinstance(payload, dict) and isinstance(payload.get("failing"), list):
        for cut in (200, 120, 60):
            trimmed = [{k: (v[:cut] if isinstance(v, str) else v)
                        for k, v in row.items()} if isinstance(row, dict) else row
                       for row in payload["failing"]]
            payload = {**payload, "failing": trimmed}
            text = json.dumps(payload, indent=1, default=str)
            if len(text) <= limit:
                return text
    if isinstance(payload, dict):
        out, keys = dict(payload), sorted(payload, key=lambda k: -len(str(payload[k])))
        for k in keys:
            out[k] = f"<omitted: {len(str(payload[k]))} chars>"
            text = json.dumps(out, indent=1, default=str)
            if len(text) <= limit:
                return text
    if isinstance(payload, list):
        for keep in range(len(payload) - 1, 0, -1):
            text = json.dumps(payload[:keep] + [f"<{len(payload)-keep} more omitted>"],
                              indent=1, default=str)
            if len(text) <= limit:
                return text
    return text[:limit]


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

  edit(old_text, new_text)            FREE. Replace a FRAGMENT, quoting enough
                                      context to be unique. WHITESPACE DOES NOT
                                      HAVE TO MATCH -- indentation, tabs and
                                      line breaks are ignored, only the tokens
                                      matter, so do not spend calls tuning it.
                                      If it says the text is not there, the
                                      TOKENS are not there. USE THIS for a small
                                      change inside a large block -- the FSM
                                      here is two thirds of the design, and
                                      retyping it to change one line is how
                                      edits go wrong.
  replace_block(block_id, new_code)   FREE. Replaces a WHOLE block. Right for a
                                      small block, wasteful for a large one.
  add_block(anchor_id, code)          FREE. anchor_id is a block id, or
                                      "endmodule" for the module end.
  remove_block(block_id)              FREE.
  check_staged()                      FREE and unlimited: syntax and driver
                                      checks on the batch. No simulation.
  discard_staged()                    FREE. Back to the last accepted RTL.

  add_stimulus(req_uid,               FREE, and the ONLY route for an UNCOVERED
               what_the_scenario_needs) requirement -- one whose check never saw
                                      its own situation. You describe in PROSE
                                      what must happen ("issue a WRITE and hold
                                      it until cmd_ack"); the harness generates
                                      the vectors and APPENDS a testpoint, so
                                      nothing existing changes. It cannot
                                      discharge a FAILING requirement and will
                                      refuse one.

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
obs = budget(session.list_failing_requirements(), 12000)
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
    obs = budget(out)
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
