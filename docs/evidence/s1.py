"""S1 re-run with the sentence floor and whole-unit spans.

`divide` now cuts at sentence ends and `to_requirements` records the WHOLE UNIT
as a requirement's span, so `requirements.json` changes -- and with it every
stage downstream, because normalization, S2's testpoints, stimulus and the
oracles all read the requirement text and its span. c1-i2c's 127 requirements
over 65 units cannot be carried forward; this produces the new set.

WHAT THIS MEASURES, beyond producing the artifact:

  * how many units the classifier calls behavioural, interface, scaffolding
  * how many claim `continues_previous` -- the open risk. A continuation's
    obligations are DROPPED and its span folded into the previous requirement,
    which was rare when a unit was a paragraph and is not rare now. The prompt
    was narrowed to say a continuation states no obligation of its own, but
    that is a prompt and not a gate. This is the number that says whether the
    narrowing held.
  * requirements per behavioural unit, and the gate's issues by kind
  * that every span is exactly one unit (or a fold of adjacent ones), which is
    the property the change exists to create

The port is `resumable`, so an interrupted run costs only the units it did not
reach. Nothing here reads an environment variable: the model, the effort and
the run directory are switches.
"""
from __future__ import annotations

import argparse
import collections
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, "/home/user/Veri-Sure")

SRC = Path("/home/user/runs/c1-i2c")


def main() -> int:
    from specflow.divide import divide, splits_a_sentence
    from specflow.integration import _run_divided_s1
    from specflow.model_io import PortSettings, make_port, resumable

    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", default="/home/user/runs/n3-i2c")
    ap.add_argument("--spec", default=str(SRC / "prompt.txt"))
    ap.add_argument("--contract", default=str(SRC / "contract.json"))
    ap.add_argument("--model", default="gpt-5-mini")
    ap.add_argument("--effort", default="medium")
    ap.add_argument("--max-repairs", type=int, default=3)
    a = ap.parse_args()

    run_dir = Path(a.run_dir)
    spec = Path(a.spec).read_text(encoding="utf-8")
    contract_json = Path(a.contract).read_text(encoding="utf-8")

    units = divide(spec)
    bad = splits_a_sentence(spec, units)
    print(f"divide: {len(units)} units, splits_a_sentence={len(bad)}", flush=True)
    if bad:
        raise SystemExit("the divider cut inside a sentence; fix that first")

    settings = PortSettings(model=a.model, effort=a.effort,
                            small_model=a.model, small_effort=a.effort,
                            developer_role_prefix=True)
    port = resumable(make_port("api", run_dir / "agent_io", settings=settings),
                     run_dir / "agent_io")

    t0 = time.time()
    print(f"classifying {len(units)} units on {a.model}/{a.effort}, "
          f"max_repairs={a.max_repairs}", flush=True)
    reqs, issues, _ = _run_divided_s1(
        run_dir=run_dir, spec=spec, contract_json=contract_json, port=port,
        max_repairs=a.max_repairs, reuse=False,
    )
    dt = time.time() - t0

    # --- what the classifier said about the units ----------------------------
    gate = json.loads((run_dir / "specflow" / "s1_gate.json").read_text())
    by_kind: collections.Counter[str] = collections.Counter()
    conts = 0
    for p in sorted((run_dir / "agent_io").glob("classify_*_r*_response.txt")):
        try:
            obj = json.loads(p.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        by_kind[str(obj.get("kind", "?"))] += 1
        conts += bool(obj.get("continues_previous"))

    # --- the property the change exists to create ----------------------------
    starts = {u.start for u in units}
    ends = {u.end for u in units}
    whole = sum(
        1 for r in reqs
        for s in r["spec_spans"][:1]
        if s["start"] in starts and s["end"] in ends
    )

    print(f"\nunits           {len(units)}  (c1-i2c: 65)")
    print(f"requirements    {len(reqs)}  (c1-i2c: 127)")
    print(f"gate ok         {gate['ok']}, issues {len(issues)}")
    kinds = collections.Counter(
        (i.kind or "-") for i in issues)
    for k, n in kinds.most_common():
        print(f"  issue {k:<12} {n}")
    print(f"classified      {dict(by_kind)}")
    print(f"continues_prev  {conts} of {sum(by_kind.values())} responses")
    print(f"spans on unit boundaries  {whole} of {len(reqs)}  (c1-i2c: 6 of 127)")
    print(f"word-carrying gaps        {gate['word_carrying_gaps']}")
    print(f"largest requirement span  {gate['largest_requirement_chars']} chars")
    print(f"\ndone in {dt:.0f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
