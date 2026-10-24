#!/usr/bin/env python3
"""Rewrite every check a known-good implementation refutes, from the REQUIREMENT.

The 43 checks the control refutes are not off-target and are not mis-scoped.
Read against their requirements they are ON topic and treat as a FAILURE
something the requirement never states:

  REQ-0094  "arbitration checking is performed during WRITE operations"
            -> demanded BOTH lines released when `al` asserts
  REQ-0026  "the idle FSM decodes cmd as one of the supported commands"
            -> demanded `cmd_ack` pulse for exactly one clock
  REQ-0021  "when ena is low the clock divider reloads"
            -> demanded `scl_oen` CHANGE on the ena-fall

THE HOLD-OUT IS THE WHOLE DISCIPLINE HERE. The control decides WHICH checks are
rewritten; it never appears in the prompt and never says WHAT to change. The
plan records why in as many words: a control may reject an oracle but never
repair one, because quoting a known-good design's trace tunes the check to it,
the model is then tuned to the check, and `golden_check` stops being held out.
So the author sees the requirement, its normalized form, and its own check --
and is asked one question about the relationship between them.

AND THE REPAIR HAS AN OBVIOUS FAILURE MODE, which is why it is measured on both
sides. A check told "you assert too much" can answer by asserting nothing, and a
check that passes everything is worse than one that fails correct hardware: the
first is undetectable, the second at least announces itself. So every rewrite is
re-decided against the control (did it stop refuting?) AND against the generated
model (does it still fail something?). A rewrite that the control satisfies and
that also stops failing the model it used to fail has probably gone vacuous, and
is reported as such rather than counted as a win.

Usage:
    python benchmarks/repair_overstrict.py --run <run-dir> --model gpt-5-mini \\
        --env-file .env.local [--limit N] [--out repaired.json]
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from eda_agent.utils import extract_json_object, strip_markdown_code_fences  # noqa: E402
from specflow.model_io import ApiPort, PortSettings, load_env_file  # noqa: E402
from specflow.refmodel import verdict as V  # noqa: E402
from specflow.refmodel.compose import choose_base  # noqa: E402
from specflow.refmodel.oracles import (RequirementOracle, decide_all,  # noqa: E402
                                       well_formed)

SYSTEM = """\
You are given a requirement, its normalized form, and a decision procedure
written to decide it. The procedure treats as a FAILURE something the
requirement does not state. Rewrite it so it does not.

You are not shown any design and you are not being told what any design does.
The only authority here is the requirement's own words.

WHAT TO REMOVE. Find every `return (False, ...)` path and ask: what would the
requirement have to say for that failure to be deserved? If its words do not
say it, that condition is yours and not the requirement's. Typical surplus:

  - a port required to hold a value, or to change, that the requirement says
    nothing about;
  - a timing, duration, pulse width or ordering the requirement does not state;
  - a condition demanded of a port the requirement mentions only as a
    precondition, not as an effect;
  - "X happens" turned into "X happens AND Y".

WHAT NOT TO DO, AND THIS IS THE HARDER HALF. Do not answer by checking nothing.
A check that cannot fail is worse than one that is too strict: it passes every
design, including designs with none of this behaviour, and nothing downstream
can tell. Keep every condition the requirement DOES state, and keep the check
able to return False for a design that violates it.

If a requirement genuinely states no falsifiable condition -- it restates its
own antecedent, or it names no observable effect -- say so in `reasoning` and
return the check unchanged rather than inventing something to assert.

The trace is a sequence of DISTINCT STATES, not clock edges: consecutive edges
with identical inputs and outputs collapse into one row carrying `held`. So
`len(rows)` is not a cycle count, and a duration is a sum of `held`.

Return `(ok, edge, detail)` where ok is True, False, or None -- None when the
scenario the requirement is about never occurred in this trace.

Reply with ONE JSON object and nothing else:

{
  "reasoning": "what the old check asserted that the requirement does not state",
  "surplus_removed": "the exact condition you removed",
  "source": "def decide(trace):\\n    ..."
}
"""


def build_prompt(requirement: dict, normalized: dict | None, source: str) -> str:
    parts = ["REQUIREMENT", json.dumps({
        "uid": requirement.get("uid"), "text": requirement.get("text"),
        "ports": requirement.get("ports")}, indent=2)]
    if normalized:
        parts += ["", "NORMALIZED FORM", json.dumps({
            "observable": normalized.get("observable"),
            "observed_via": normalized.get("observed_via"),
            "activation": normalized.get("activation"),
            "expectation": normalized.get("expectation")}, indent=2)]
    parts += ["", "THE CHECK AS WRITTEN", source]
    return "\n".join(parts)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", required=True, type=pathlib.Path)
    ap.add_argument("--control", type=pathlib.Path,
                    default=REPO_ROOT / "benchmarks" / "controls"
                    / "i2c_master_bit_ctrl" / "ref_model.py")
    # The fan-out model, per the standing rule that per-item authoring
    # runs on the small model and never on Luna.
    ap.add_argument("--model", default="gpt-5.1-codex-mini")
    ap.add_argument("--effort", default="medium")
    ap.add_argument("--env-file", type=pathlib.Path)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--out", type=pathlib.Path)
    args = ap.parse_args(argv)

    if args.env_file:
        load_env_file(str(args.env_file))

    sf = args.run / "specflow"
    contract = json.loads((args.run / "contract.json").read_text())
    raw = json.loads((sf / "oracles.json").read_text())["oracles"]
    by_uid = {o["req_uid"]: o for o in raw}
    reqs = json.loads((sf / "requirements.json").read_text())
    reqs = reqs.get("requirements") if isinstance(reqs, dict) else reqs
    rt = {r.get("uid"): r for r in reqs}
    nm = {n.get("req_uid"): n for n in
          (json.loads((sf / "normalized.json").read_text()).get("normalized") or [])}
    tp_doc = json.loads((sf / "testplan.json").read_text())
    testplan = (tp_doc.get("elements") if isinstance(tp_doc, dict) else tp_doc) or []
    stim = json.loads((sf / "stimulus.json").read_text())
    by_tp = {t["tp_uid"]: t["stimulus_steps"] for t in stim["testpoints"]}
    base = choose_base(contract)
    control = args.control.read_text()
    model_src = (sf / "ref_model.py").read_text()

    def oracle_of(uid: str, source: str) -> RequirementOracle:
        o = by_uid[uid]
        return RequirementOracle(req_uid=uid, tp_uids=o["tp_uids"],
                                 clause=o.get("clause", ""), source=source,
                                 hash=o.get("hash", ""))

    def verdicts(oracles, src):
        return {r.req_uid: V.of_result(r) for r in decide_all(
            oracles, src, contract, by_tp, base=base, transactional=True)}

    originals = [oracle_of(u, by_uid[u]["source"]) for u in sorted(by_uid)]
    print("deciding the ORIGINAL set against the control ...", flush=True)
    before_ctl = verdicts(originals, control)
    print("deciding the ORIGINAL set against the model ...", flush=True)
    before_mdl = verdicts(originals, model_src)
    targets = sorted(u for u, v in before_ctl.items() if v == "VIOLATES")
    if args.limit:
        targets = targets[:args.limit]
    print(f"\n{len(targets)} checks the control refutes; rewriting each from its "
          f"requirement on {args.model}\n", flush=True)

    settings = PortSettings(small_model=args.model, small_effort=args.effort)
    port = ApiPort(root=str(args.run / "agent_io_repair"), settings=settings)
    rewritten: dict[str, str] = {}
    notes: dict[str, str] = {}
    for i, uid in enumerate(targets):
        prompt = SYSTEM + "\n\n" + build_prompt(
            rt.get(uid, {}), nm.get(uid), by_uid[uid]["source"])
        try:
            out = extract_json_object(strip_markdown_code_fences(
                port.complete(stage="repair", round_=i, prompt=prompt))) or {}
        except Exception as exc:  # noqa: BLE001
            print(f"  {uid}: call failed: {type(exc).__name__}", flush=True)
            continue
        src = out.get("source") or ""
        # The stage's own structural gate, not a second one: a rewrite that
        # cannot parse, names an undeclared port, or cites an unknown testpoint
        # is not an improvement over a check that is merely too strict.
        bad = (well_formed(oracle_of(uid, src), contract, testplan)
               if src else "no source returned")
        if bad:
            print(f"  {uid}: rejected, {str(bad)[:90]}", flush=True)
            continue
        rewritten[uid] = src
        notes[uid] = out.get("surplus_removed", "")
        print(f"  {uid}: removed {notes[uid][:80]!r}", flush=True)

    if not rewritten:
        print("\nnothing was rewritten")
        return 1

    patched = [oracle_of(u, rewritten.get(u, by_uid[u]["source"]))
               for u in sorted(by_uid)]
    print(f"\nre-deciding {len(rewritten)} rewrites against the control ...",
          flush=True)
    after_ctl = verdicts(patched, control)
    print("re-deciding against the model ...", flush=True)
    after_mdl = verdicts(patched, model_src)

    fixed = [u for u in rewritten if after_ctl[u] != "VIOLATES"]
    # THE FAILURE MODE, counted rather than assumed: it stopped refuting the
    # control AND stopped failing the model it used to fail.
    vacuous = [u for u in fixed
               if before_mdl.get(u) == "VIOLATES" and after_mdl.get(u) == "CONFORMS"]
    print(f"\ncontrol still refutes:      {len(rewritten) - len(fixed)} of {len(rewritten)}")
    print(f"control now satisfies:      {len(fixed)}")
    print(f"  ...of which went quiet:   {len(vacuous)}  "
          f"(stopped failing the model too -- probably vacuous, NOT a win)")
    print(f"  ...genuine repairs:       {len(fixed) - len(vacuous)}")
    if vacuous:
        print("  went quiet:", " ".join(sorted(vacuous)))
    if args.out:
        args.out.write_text(json.dumps({
            "model": args.model, "rewritten": rewritten, "surplus_removed": notes,
            "before_control": before_ctl, "after_control": after_ctl,
            "before_model": before_mdl, "after_model": after_mdl,
            "fixed": fixed, "went_quiet": vacuous}, indent=2) + "\n")
        print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
