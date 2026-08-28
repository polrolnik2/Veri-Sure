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

The test is mechanical: find every path on which this check REPORTS A FAILURE,
and ask what the requirement's own words would have to say for that failure to
be deserved. If the requirement does not say it, that is a surplus claim -- YES,
and quote it.

A failure path is NOT only `return (False, ...)`. Most checks build their
verdict out of the temporal combinators -- `after`, `eventually`, `throughout`,
`stable`, `pulse`, folded by `worst` -- and there the failure is whatever the
combinator convicts on: the predicate it is given, over the window it is given.
Read those the same way.

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


#: THE SECOND QUESTION, and a strictly different axis from surplus.
#:
#: A direction error asserts NOTHING EXTRA -- it asserts the wrong end of the
#: requirement's own implication -- so the surplus reviewer above passes it by
#: construction. Its LABEL differs too, which is the part that would have made
#: a joint score meaningless: a check that asserts its own antecedent CANNOT
#: FAIL, so a known-good implementation satisfies it and it lands in the
#: negative class of the control label. Scoring direction against
#: control-refutation would count every correct catch as a false positive.
#: Vacuity is its label.
#:
#: c1-i2c REQ-0015 is the worked case, and it is why this is worth a second
#: call rather than another bullet in the first. The requirement is "Releasing
#: scl_oen or sda_oen high shall allow the external pull-up to drive the
#: corresponding line high"; the check opens its window on the enables and
#: asserts the enables, which is the premise. The LIVE correspondence gate saw
#: it three times across the repair rounds and passed it three times, r2 saying
#: in as many words: "It does not sample the external line levels
#: (scl_i/sda_i), but partial checks of the controller releasing the outputs
#: are considered ON TARGET."
#:
#: That is that gate's own partial-is-on-target rule working exactly as
#: written, and the rule is right -- it is what keeps the gate from drifting
#: into demanding more, which an earlier calibration showed costs 56 rejections
#: in 70. What it cannot do is separate "decides half the requirement" from
#: "decides the half that is the premise". So the fix is not to weaken that
#: rule; it is to ask the half it does not cover, separately. Only the vacuity
#: leg convicted REQ-0015, and vacuity needs variants and an execution to say
#: so, where this needs two texts.
DIRECTION_SYSTEM = """\
You are given a requirement and a decision procedure written to decide it.
Answer ONE question: does the procedure assert the requirement's CONSEQUENT, or
has it got the implication the wrong way round?

Almost every requirement has the shape: WHEN some condition holds (the
ANTECEDENT), THEN some effect appears (the CONSEQUENT). A check must OPEN on
the antecedent and ASSERT the consequent. You are asked only whether it does.

You are not judging any design -- none appears below. You are not judging
whether the check is thorough, strict, complete, or well-timed. A check that
asserts the right consequent WEAKLY, PARTIALLY, or without any timing is
CORRECTLY DIRECTED. Say no.

Say YES only when what the check ASSERTS is one of these:

  - THE ANTECEDENT ITSELF. It opens its window on a condition and then requires
    that same condition, or a restatement of it, to hold. It reduces to "when
    X, X" and cannot fail. This is the common one.
  - THE CONVERSE. The requirement says the antecedent produces the effect; the
    check asserts the effect implies the antecedent, convicting a design that
    produced that effect for another legitimate reason.
  - THE INVERSE. It convicts on what happens when the antecedent does NOT hold.
    A requirement saying what happens under X says nothing about not-X.
  - SWAPPED ROLES. It guards on the consequent and asserts the antecedent --
    the two halves used in each other's place.

Work in this order, and put the first two steps in `reasoning`: name the
requirement's antecedent and its consequent, in the requirement's own words.
Then say which of the two the check asserts. If it asserts the consequent --
however partially -- the answer is NO.

The normalized form is a hint, not the authority: `activation` is usually the
antecedent and `expectation` the consequent, but the requirement's text
decides.

A check may assert on a port the requirement's text never names, because the
normalized form gave it an OBSERVATION ROUTE. That is not a direction error.
What matters is whether what it asserts THERE is the effect or the premise.

Reply with ONE JSON object and nothing else:

{
  "reasoning": "the antecedent, the consequent, and which of them the check asserts",
  "antecedent": "the requirement's condition, quoted",
  "consequent": "the requirement's effect, quoted",
  "wrong_direction": true,
  "which": "on true: one of antecedent | converse | inverse | swapped",
  "detail": "on true: what the check asserts, and what it would have to assert instead"
}
"""

#: `(system prompt, the boolean field its reply carries, the field naming what
#: it found)`. The two questions are deliberately separate calls: a reviewer
#: given two questions answers the easier one, which is how the retired judge
#: produced 50 AMBIGUOUS verdicts in 77.
QUESTIONS = {
    "surplus": (SYSTEM, "asserts_beyond_the_requirement", "surplus_claim"),
    "direction": (DIRECTION_SYSTEM, "wrong_direction", "detail"),
}

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


def recover_rejected(run: pathlib.Path, uids: set[str]) -> dict[str, dict]:
    """`{req_uid: {clause, source}}` for oracles the stage rejected.

    A rejected oracle never reaches `oracles.json`'s frozen list, and for the
    direction question that list is precisely the wrong population: its
    positives are the VACUOUS ones, which are rejected by definition. Their
    generated source is still in `agent_io`, so read the LAST round the author
    produced -- the repair rounds write `_fix1`, `_fix2`, and the version the
    gate actually convicted is the newest, not `_r0`.
    """
    io = run / "agent_io"
    out: dict[str, dict] = {}
    for uid in uids:
        seen = sorted(io.glob(f"oracle_{uid}_*response.txt"),
                      key=lambda f: f.stat().st_mtime)
        for path in reversed(seen):
            try:
                obj = json.loads(path.read_text())
            except Exception:  # noqa: BLE001, PERF203
                continue
            if isinstance(obj, dict) and obj.get("source"):
                out[uid] = {"req_uid": uid, "clause": obj.get("clause", ""),
                            "source": obj["source"]}
                break
    return out


def load_labels(args, artifact: dict,
                oracles: dict) -> tuple[dict[str, str], str, str]:
    """`(uid -> label, positive class, negative class)` for the chosen question.

    THE TWO QUESTIONS DO NOT SHARE A LABEL, and that is the reason they are not
    one call. Surplus is labelled by the known-good control: a check asserting
    more than the requirement states convicts correct hardware, so the control
    refutes it. Direction is not: a check that asserts its own antecedent
    CANNOT FAIL, so the control satisfies it and it sits in surplus's NEGATIVE
    class. Scored there, every correct direction catch would count as a false
    positive. Vacuity is the label that sees it -- a check that cannot fail is
    what `variants.must_fail` exists to convict.
    """
    if args.question == "direction":
        disp = artifact["dispositions"]
        graded = {u: v for u, v in disp.items()
                  if v in ("VACUOUS", "TRUSTED") and u in oracles}
        return graded, "VACUOUS", "TRUSTED"

    if not args.labels:
        raise SystemExit("--labels is required for --question surplus")
    labels = json.loads(args.labels.read_text())
    # Only checks the control DECIDED: an abstention is not a label.
    graded = {u: v["verdict"] for u, v in labels.items()
              if v.get("verdict") in ("VIOLATES", "CONFORMS") and u in oracles}
    return graded, "VIOLATES", "CONFORMS"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", required=True, type=pathlib.Path)
    ap.add_argument("--question", default="surplus", choices=sorted(QUESTIONS),
                    help="surplus: asserts more than the requirement states, "
                         "labelled by the control. direction: asserts the "
                         "premise instead of the effect, labelled by vacuity.")
    ap.add_argument("--labels", type=pathlib.Path,
                    help="req_uid -> {verdict} from deciding against the "
                         "control. Required for --question surplus; unused by "
                         "--question direction, which reads its label from "
                         "oracles.json's dispositions.")
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
    artifact = json.loads((sf / "oracles.json").read_text())
    oracles = {o["req_uid"]: o for o in artifact["oracles"]}
    # A REJECTED oracle is not in the frozen list, and the rejected ones are
    # exactly the direction question's positive class -- REQ-0015 is VACUOUS
    # and absent here. Its source is still on disk in `agent_io`, so read it
    # back rather than scoring the question on a set its positives cannot
    # appear in.
    oracles.update(recover_rejected(args.run, set(artifact["dispositions"])
                                    - set(oracles)))
    reqs = json.loads((sf / "requirements.json").read_text())
    reqs = reqs.get("requirements") if isinstance(reqs, dict) else reqs
    rt = {r.get("uid"): r for r in reqs}
    norm = json.loads((sf / "normalized.json").read_text())
    nm = {n.get("req_uid"): n for n in (norm.get("normalized") or [])}
    graded, pos, neg = load_labels(args, artifact, oracles)
    uids = sorted(graded)
    if args.limit:
        # Balanced, so a truncated run is not silently all of one class.
        bad = [u for u in uids if graded[u] == pos][:args.limit // 2]
        good = [u for u in uids if graded[u] == neg][:args.limit // 2]
        uids = sorted(bad + good)
    n_pos = sum(1 for u in uids if graded[u] == pos)
    print(f"{len(uids)} labelled checks ({n_pos} {pos}, "
          f"{len(uids) - n_pos} {neg})", flush=True)
    if n_pos < 10:
        print(f"  NOTE: {n_pos} positives is too few to read precision and "
              f"recall as anything but directional.", flush=True)

    settings = PortSettings(small_model=args.model, small_effort=args.effort)
    port = ApiPort(root=str(args.run / "agent_io_calib"), settings=settings)

    system, said_field, detail_field = QUESTIONS[args.question]
    rows = []
    for i, uid in enumerate(uids):
        prompt = system + "\n\n" + build_prompt(rt.get(uid, {}), oracles[uid],
                                                 nm.get(uid))
        try:
            raw = port.complete(stage="calibrate", round_=i, prompt=prompt)
            obj = extract_json_object(strip_markdown_code_fences(raw)) or {}
        except Exception as exc:  # noqa: BLE001
            print(f"  {uid}: call failed: {type(exc).__name__}: {exc}", flush=True)
            continue
        said = bool(obj.get(said_field))
        rows.append({"uid": uid, "label": graded[uid], "flagged": said,
                     "found": obj.get(detail_field, ""),
                     "which": obj.get("which", ""),
                     "reasoning": obj.get("reasoning", "")})
        print(f"  {uid} label={graded[uid]:<9} flagged={said}", flush=True)

    tp = sum(1 for r in rows if r["flagged"] and r["label"] == pos)
    fp = sum(1 for r in rows if r["flagged"] and r["label"] == neg)
    fn = sum(1 for r in rows if not r["flagged"] and r["label"] == pos)
    tn = sum(1 for r in rows if not r["flagged"] and r["label"] == neg)
    prec = tp / (tp + fp) if tp + fp else 0.0
    rec = tp / (tp + fn) if tp + fn else 0.0
    print(f"\n{'':>14}{pos:>18}{neg:>19}")
    print(f"{'flagged':>14}{tp:>18}{fp:>19}")
    print(f"{'not flagged':>14}{fn:>18}{tn:>19}")
    print(f"\nprecision {prec:.2f}   recall {rec:.2f}   n={len(rows)}")
    print("A reviewer that flags everything scores recall 1.0 and is useless; "
          "read both.")
    if args.out:
        args.out.write_text(json.dumps(
            {"question": args.question, "positive": pos, "negative": neg,
             "model": args.model, "effort": args.effort, "rows": rows,
             "tp": tp, "fp": fp, "fn": fn, "tn": tn,
             "precision": prec, "recall": rec}, indent=2) + "\n")
        print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
