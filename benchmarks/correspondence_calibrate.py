#!/usr/bin/env python3
"""Calibrate a correspondence reviewer against a KNOWN-GOOD-LABELLED check set.

The gap this measures. `correspondence` asks one question -- is this check
ABOUT this requirement -- and answers it well: 3 rejections in 70, all genuinely
off-target. It is deliberately not asked whether a check is too strict, because
a reviewer given that question drifts into wanting MORE, and an earlier
calibration showed exactly that: 56 of 70 rejected, of which 26 said "it should
also check X" and 15 wanted tighter timing.

But the checks that reject correct hardware are not off-target. Read against
their requirements they are ON topic and assert something the requirement never
states:

  REQ-0094  "arbitration checking is performed during WRITE operations"
            -> check demands BOTH lines released when `al` asserts
  REQ-0026  "the idle FSM decodes cmd as one of the supported commands"
            -> check demands `cmd_ack` pulse for exactly one clock
  REQ-0021  "when ena is low the clock divider reloads"
            -> check demands `scl_oen` CHANGE on the ena-fall

Three mechanical screens were tried and all three found nothing: ports read
outside the requirement (86% of failing checks, 82% of passing ones), ports
CONVICTED on outside the requirement and its routes (0 of 43), and an
observable port no route explains (1 of 43 against 0 of 49). No structural
property separates them. What is left is a reader comparing CLAIMS.

So this asks a second, strictly one-directional question -- does the check
assert anything the requirement does not state -- and measures it against a
label no reviewer can see: whether a known-good implementation of the same spec
satisfies the check. 43 refuted, 49 satisfied, same requirements, same author.

The reviewer never sees a design, a trace, or the label. Two texts, as before.

Usage:
    python benchmarks/correspondence_calibrate.py --run <run-dir> \\
        --model gpt-5.4-mini --labels <control_verdicts.json> [--limit N]
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from eda_agent.utils import extract_json_object, strip_markdown_code_fences  # noqa: E402
from specflow.model_io import ApiPort, PortSettings  # noqa: E402

#: The added question. Strictly one-directional, and the wording carries that:
#: a check that decides LESS than the requirement is fine here, because the
#: opposite instruction is what turned an earlier calibration into 56 of 70
#: rejections, 41 of them asking for more.
SYSTEM = """\
You are given a requirement and a decision procedure written to decide it.
Answer ONE question: does the procedure treat as a FAILURE anything the
requirement does not state?

You are not judging any design -- none appears below. You are not judging
whether the check is thorough, complete, or strict enough.

**A check that decides LESS than the requirement is FINE. Say no.**
"It should also check X" is NO. "It should check X more precisely" is NO.
"It only covers part of the requirement" is NO. Missing anything is NO.

Say YES only when the check can return a FAILING verdict for a reason the
requirement does not give. Concretely:

  - it requires a port to hold a value, or to change, that the requirement
    never says anything about;
  - it requires a timing, duration, pulse width or ordering the requirement
    does not state;
  - it requires a condition to hold on a port the requirement mentions only as
    a precondition, not as an effect;
  - it turns "X happens" into "X happens AND Y", where Y is yours.

The test is mechanical: find each `return (False, ...)` path. Ask what the
requirement's own words would have to say for that failure to be deserved. If
the requirement does not say it, that is a surplus claim -- YES, and quote it.

A requirement often names an OBSERVATION ROUTE: a port it is decided at even
though its text does not name it. Asserting on that port is not surplus. What
the check claims the port must DO is what can be surplus.

Reply with ONE JSON object and nothing else:

{
  "reasoning": "one or two sentences",
  "asserts_beyond_the_requirement": true,
  "surplus_claim": "on true: the exact thing the check treats as a failure that the requirement does not state"
}
"""


def build_prompt(requirement: dict, oracle: dict, normalized: dict | None) -> str:
    parts = ["REQUIREMENT", json.dumps({
        "uid": requirement.get("uid"),
        "text": requirement.get("text"),
        "ports": requirement.get("ports"),
    }, indent=2)]
    if normalized:
        parts += ["", "NORMALIZED FORM (the observation routes it was given)",
                  json.dumps({
                      "observable": normalized.get("observable"),
                      "observed_via": normalized.get("observed_via"),
                      "activation": normalized.get("activation"),
                      "expectation": normalized.get("expectation"),
                  }, indent=2)]
    parts += ["", "THE CHECK", oracle.get("source", "")]
    return "\n".join(parts)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", required=True, type=pathlib.Path)
    ap.add_argument("--labels", required=True, type=pathlib.Path,
                    help="req_uid -> {verdict} from deciding against the control")
    ap.add_argument("--model", default="gpt-5.4-mini")
    ap.add_argument("--effort", default="medium")
    ap.add_argument("--env-file", type=pathlib.Path)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--out", type=pathlib.Path)
    args = ap.parse_args(argv)

    if args.env_file:
        from specflow.model_io import load_env_file
        load_env_file(str(args.env_file))

    sf = args.run / "specflow"
    oracles = {o["req_uid"]: o for o in json.loads(
        (sf / "oracles.json").read_text())["oracles"]}
    reqs = json.loads((sf / "requirements.json").read_text())
    reqs = reqs.get("requirements") if isinstance(reqs, dict) else reqs
    rt = {r.get("uid"): r for r in reqs}
    norm = json.loads((sf / "normalized.json").read_text())
    nm = {n.get("req_uid"): n for n in (norm.get("normalized") or [])}
    labels = json.loads(args.labels.read_text())

    # Only checks the control DECIDED: an abstention is not a label.
    graded = {u: v["verdict"] for u, v in labels.items()
              if v.get("verdict") in ("VIOLATES", "CONFORMS") and u in oracles}
    uids = sorted(graded)
    if args.limit:
        # Balanced, so a truncated run is not silently all of one class.
        bad = [u for u in uids if graded[u] == "VIOLATES"][:args.limit // 2]
        good = [u for u in uids if graded[u] == "CONFORMS"][:args.limit // 2]
        uids = sorted(bad + good)
    print(f"{len(uids)} labelled checks "
          f"({sum(1 for u in uids if graded[u]=='VIOLATES')} refuted by the "
          f"control, {sum(1 for u in uids if graded[u]=='CONFORMS')} satisfied)",
          flush=True)

    settings = PortSettings(small_model=args.model, small_effort=args.effort)
    port = ApiPort(root=str(args.run / "agent_io_calib"), settings=settings)

    rows = []
    for i, uid in enumerate(uids):
        prompt = SYSTEM + "\n\n" + build_prompt(rt.get(uid, {}), oracles[uid],
                                                nm.get(uid))
        try:
            raw = port.complete(stage="calibrate", round_=i, prompt=prompt)
            obj = extract_json_object(strip_markdown_code_fences(raw)) or {}
        except Exception as exc:  # noqa: BLE001
            print(f"  {uid}: call failed: {type(exc).__name__}: {exc}", flush=True)
            continue
        said = bool(obj.get("asserts_beyond_the_requirement"))
        rows.append({"uid": uid, "label": graded[uid], "flagged": said,
                     "surplus": obj.get("surplus_claim", ""),
                     "reasoning": obj.get("reasoning", "")})
        print(f"  {uid} label={graded[uid]:<9} flagged={said}", flush=True)

    tp = sum(1 for r in rows if r["flagged"] and r["label"] == "VIOLATES")
    fp = sum(1 for r in rows if r["flagged"] and r["label"] == "CONFORMS")
    fn = sum(1 for r in rows if not r["flagged"] and r["label"] == "VIOLATES")
    tn = sum(1 for r in rows if not r["flagged"] and r["label"] == "CONFORMS")
    prec = tp / (tp + fp) if tp + fp else 0.0
    rec = tp / (tp + fn) if tp + fn else 0.0
    print(f"\n{'':>14}{'control REFUTES':>18}{'control SATISFIES':>19}")
    print(f"{'flagged':>14}{tp:>18}{fp:>19}")
    print(f"{'not flagged':>14}{fn:>18}{tn:>19}")
    print(f"\nprecision {prec:.2f}   recall {rec:.2f}   n={len(rows)}")
    print("A reviewer that flags everything scores recall 1.0 and is useless; "
          "read both.")
    if args.out:
        args.out.write_text(json.dumps(
            {"model": args.model, "effort": args.effort, "rows": rows,
             "tp": tp, "fp": fp, "fn": fn, "tn": tn,
             "precision": prec, "recall": rec}, indent=2) + "\n")
        print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
