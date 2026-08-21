"""Is the JUDGE the limiting factor, or is the evidence?

Escalating a judge's model or effort on a hunch is unfalsifiable -- a verdict
set that looks wrong is equally consistent with a reader too small to use the
evidence and with evidence too weak to support any reader. This separates them
using something neither interpretation can argue with: a verdict that
contradicts the trace sitting in its own prompt.

The marker is `met` returned for a requirement about an output port, when the
behavioural evidence in that same prompt shows the model's outputs never moving.
Nothing about that requires judgement to call wrong. The reader was shown a
constant trace, was asked whether a design that must drive an output satisfies
the requirement, and said yes. That is a reading failure, and it is the licence
to raise the model or the effort.

The converse matters as much. If the judge returns `met` and the trace genuinely
shows the behaviour, or returns `not_met` with a cited edge, then the reader is
using what it was given and a bigger model is not the missing piece.

Reports rather than gates. Which knob to turn is a decision about cost, and this
supplies the fact that decision needs, not the decision.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


def _outputs(contract: dict) -> set[str]:
    return {
        str(p.get("name")) for p in (contract.get("io") or [])
        if p.get("dir") == "output" and p.get("name")
    }


def _trace_is_inert(prompt: str) -> bool | None:
    """Did the behaviour block in THIS prompt show outputs that never move?

    Read off the trace the judge was actually shown, not recomputed, so the
    finding is about what that call could see.
    """
    m = re.search(r"(\d+) distinct output state\(s\) over", prompt)
    return None if not m else int(m.group(1)) == 1


def analyse(run_dir: Path) -> dict:
    run_dir = Path(run_dir)
    contract = json.loads((run_dir / "contract.json").read_text(encoding="utf-8"))
    outs = _outputs(contract)
    reqs = json.loads(
        (run_dir / "specflow" / "requirements.json").read_text(encoding="utf-8")
    )["requirements"]
    by_uid = {str(r.get("uid")): r for r in reqs}

    # Verdict and prompt must come from the SAME round. `refmodel_judge.json`
    # holds one round's verdicts -- the last COMPLETED one -- while agent_io
    # holds prompts for every round, so reading verdicts from the report and
    # prompts from the glob pairs a round-0 `met` with a round-2 trace. On this
    # run that manufactured 17 contradictions out of nothing: round 0's model
    # had 3 output states and round 2's had 1, so every round-0 `met` looked
    # like a verdict against a flat trace. The per-round response files are the
    # only place where a verdict and the prompt that produced it are known to
    # belong together.
    contradictions, checked, inert_prompts = [], 0, 0
    for path in sorted((run_dir / "agent_io").glob("judge_REQ-*_r*_prompt.txt")):
        m = re.search(r"judge_(REQ-\d+)_r(\d+)_prompt", path.name)
        if not m:
            continue
        uid, rnd = m.group(1), m.group(2)
        answer = path.parent / f"judge_{uid}_r{rnd}_response.txt"
        if not answer.exists():
            continue
        try:
            body = re.search(r"\{.*\}", answer.read_text(encoding="utf-8"), re.S)
            verdict = str(json.loads(body.group(0)).get("verdict") or "")
        except Exception:  # noqa: BLE001 -- an unparseable answer judges nothing
            continue
        prompt = path.read_text(encoding="utf-8")
        inert = _trace_is_inert(prompt)
        if inert is None:
            continue
        checked += 1
        inert_prompts += bool(inert)
        # Only requirements ABOUT an output can be contradicted by a flat trace.
        req_ports = {str(p) for p in (by_uid.get(uid, {}).get("ports") or [])}
        if inert and verdict == "met" and (req_ports & outs):
            contradictions.append({
                "uid": uid,
                "ports": sorted(req_ports & outs),
                "text": str(by_uid.get(uid, {}).get("text", ""))[:120],
            })
    return {
        "requirements_checked": checked,
        "prompts_whose_trace_was_inert": inert_prompts,
        "verdict_contradicts_its_own_trace": len(contradictions),
        "contradictions": contradictions[:10],
        "reading_failure": bool(contradictions),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run", required=True, type=Path)
    args = ap.parse_args()
    out = analyse(args.run)
    print(json.dumps(out, indent=2))
    n = out["verdict_contradicts_its_own_trace"]
    if out["reading_failure"]:
        print(
            f"\nREADING FAILURE: {n} of {out['requirements_checked']} verdicts say "
            f"`met` for an output requirement while the trace in that same prompt "
            f"shows outputs that never move.\nThe reader is the limit here, not "
            f"the evidence -- raising the model or the effort is warranted."
        )
    elif out["prompts_whose_trace_was_inert"]:
        print(
            "\nNo contradiction: where the trace was inert the judge did not "
            "call it met. The reader is using the evidence; a bigger model is "
            "not the missing piece."
        )
    else:
        print("\nNo inert traces in this run -- this diagnostic has nothing to say.")


if __name__ == "__main__":
    main()
