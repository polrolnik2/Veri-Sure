"""Does the sentence floor lose requirements through `continues_previous`?

`to_requirements` folds a continuation unit's span into the previous
requirement and **drops its obligations entirely**. That was defensible when a
unit was a paragraph -- a list stem and its items really are one requirement
group -- and it is the open risk of moving the floor to the sentence, because a
four-sentence paragraph whose last three claim continuation collapses to ONE
requirement.

The prompt was narrowed to say a continuation states no obligation of its own.
This measures whether that held, on the two runs side by side:

    c1-i2c   65 units,  paragraph floor, classifier free to subdivide
    <run>   168 units,  sentence floor,  spans snapped to whole units

For each run it reports the continuation RATE, and then the thing that actually
matters -- **every obligation the fold discarded, in full**, with the text of
the unit it came from. A discarded restatement that names ports and states
behaviour is a lost requirement; one that reads as a fragment of the unit
before it is the fold doing its job. That judgement is left to a reader rather
than guessed at by a regex, which is why they are printed rather than counted.

Reads only recorded responses. No model calls.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, "/home/user/Veri-Sure")

#: A restatement that asserts something a design could get wrong. Reported as a
#: HINT beside each discarded obligation, never as the verdict -- the point of
#: printing them in full is that the reader decides.
_BEHAVIOURAL = re.compile(
    r"\b(shall|must|drives?|asserts?|holds?|samples?|latches?|clears?|sets?|"
    r"remains?|transitions?|outputs?|releases?|counts?|equals?|becomes?)\b", re.I)


def _final_response(agent_io: Path, stage: str) -> dict | None:
    """The response the stage actually used: the highest round recorded."""
    rounds = sorted(
        (int(m.group(1)), p)
        for p in agent_io.glob(f"{stage}_r*_response.txt")
        if (m := re.search(r"_r(\d+)_response\.txt$", p.name))
    )
    for _, p in reversed(rounds):
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
    return None


def survey(run_dir: Path, spec: str, label: str, *, show: int) -> dict:
    from specflow.divide import divide, normalize_spec

    text = normalize_spec(spec)
    units = divide(spec) if label != "c1-i2c" else None
    agent_io = run_dir / "agent_io"

    # c1-i2c was divided by the OLD divider; its unit offsets are whatever its
    # own stage names record, so read them back rather than re-deriving them.
    stages = sorted(
        {int(m.group(1))
         for p in agent_io.glob("classify_*_r*_response.txt")
         if (m := re.match(r"classify_(\d+)_r", p.name))}
    )
    if units is not None:
        starts = [u.start for u in units]
        assert starts == stages, (
            f"{label}: the divider produced {len(starts)} units but the run "
            f"recorded {len(stages)}; they are different partitions")
        extent = {u.start: (u.start, u.end) for u in units}
    else:
        bounds = stages + [len(text)]
        extent = {s: (s, e) for s, e in zip(stages, bounds[1:])}

    behavioural = conts = dropped_units = 0
    discarded: list[tuple[int, str, list[dict]]] = []
    for start in stages:
        obj = _final_response(agent_io, f"classify_{start}")
        if obj is None:
            continue
        if str(obj.get("kind")) != "behavioural":
            continue
        behavioural += 1
        if not obj.get("continues_previous"):
            continue
        conts += 1
        obs = [o for o in (obj.get("obligations") or []) if str(o.get("text", "")).strip()]
        if obs:
            dropped_units += 1
            a, b = extent[start]
            discarded.append((start, text[a:b], obs))

    print(f"\n=== {label} ===")
    print(f"units recorded          {len(stages)}")
    print(f"behavioural             {behavioural}")
    print(f"continues_previous      {conts}"
          f"  ({conts / behavioural:.0%} of behavioural)" if behavioural else "")
    print(f"  ...carrying an obligation the fold DISCARDS   {dropped_units}")
    print(f"  ...obligations discarded in total             "
          f"{sum(len(o) for _, _, o in discarded)}")

    for start, unit_text, obs in discarded[:show]:
        print(f"\n  unit @{start}: {unit_text[:150]!r}")
        for o in obs:
            t = str(o.get("text", "")).strip()
            hint = "BEHAVIOURAL" if _BEHAVIOURAL.search(t) else "fragment?"
            print(f"    [{hint}] ports={o.get('ports') or []}  {t!r}")
    if len(discarded) > show:
        print(f"\n  ... {len(discarded) - show} more not shown (--show to raise)")

    return {"units": len(stages), "behavioural": behavioural,
            "continuations": conts, "dropping": dropped_units,
            "obligations_dropped": sum(len(o) for _, _, o in discarded)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", default="/home/user/runs/n3-i2c")
    ap.add_argument("--baseline", default="/home/user/runs/c1-i2c")
    ap.add_argument("--spec", default="/home/user/runs/c1-i2c/prompt.txt")
    ap.add_argument("--show", type=int, default=12)
    a = ap.parse_args()

    spec = Path(a.spec).read_text(encoding="utf-8")
    old = survey(Path(a.baseline), spec, "c1-i2c", show=a.show)
    new = survey(Path(a.run_dir), spec, Path(a.run_dir).name, show=a.show)

    print("\n=== side by side ===")
    for k in ("units", "behavioural", "continuations", "dropping",
              "obligations_dropped"):
        print(f"{k:<22} {old[k]:>5}  ->  {new[k]:>5}")
    if old["behavioural"] and new["behavioural"]:
        print(f"{'continuation rate':<22} "
              f"{old['continuations']/old['behavioural']:>5.0%}  ->  "
              f"{new['continuations']/new['behavioural']:>5.0%}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
