#!/usr/bin/env python3
"""Does the window reach the check, and does the check use it?

Two halves, because the defect spans two stages and fixing one alone proves
nothing:

  1. NORMALISE. Given the prompt that now asks for `until`/`opens_on`, does a
     requirement whose text names a span come back carrying a close condition?
  2. GENERATE. Given a normalized form that HAS a window, does the check author
     transcribe it -- `after(trace, opens, until=closes)` -- instead of writing
     its own index arithmetic over `trace`?

Scoped to the population that went wrong on a2-i2c: the 29 checks the
known-good control fails, plus the 12 that pass every variant. Those two are
one defect with opposite signs (79% and 83% of them are a windowed requirement
flattened to a one-row activation, against 58% of the checks carrying neither
flag), so both belong in the same probe.

The baseline this is measured against is v1's, and it is stark: 254 prompts
offered the temporal operators and 0 of 306 responses used them. But v1 never
said what they RETURN, and -- more to the point -- the normalized block it
handed the author contained no window to transcribe. This probe changes both.

Reads nothing from the environment at call time: credentials come from the env
file, every other knob is a switch. See `PortSettings`.

    python benchmarks/window_probe.py --run /home/user/runs/a2-i2c \\
        --out /tmp/window_probe --limit 8
"""

from __future__ import annotations

import argparse
import ast
import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from specflow.model_io import PortSettings, make_port, resumable  # noqa: E402
from specflow.normalize import run_normalize_fanout  # noqa: E402
from specflow.refmodel.oracle_gen import run_oracle_gen  # noqa: E402

#: The operators, by name. A check that imports the module but calls nothing is
#: not uptake, so this counts CALLS, in the AST, not mentions in the text.
OPERATORS = {"after", "eventually", "throughout", "stable", "pulse", "worst"}


def _calls(source: str) -> set[str]:
    """Operator names actually called. AST, so a name inside a comment or a
    docstring does not count -- the failure mode of a text scan here is to
    report uptake that is not there."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return set()
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in OPERATORS:
                out.add(node.func.id)
    return out


def _hand_rolled(source: str) -> bool:
    """Own index arithmetic over the trace -- the shape that produces a point
    check. `range(len(trace))`, or `trace[i]` with an integer name."""
    return bool(re.search(r"range\s*\(\s*len\s*\(\s*trace", source)
                or re.search(r"\btrace\s*\[\s*[a-z_]+\s*[+\-]", source))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run", required=True, type=pathlib.Path,
                    help="a completed run dir: contract.json + specflow/")
    ap.add_argument("--out", required=True, type=pathlib.Path)
    ap.add_argument("--limit", type=int, default=0,
                    help="first N of the target population; 0 = all")
    ap.add_argument("--model", default="gpt-5.1-codex-mini",
                    help="the fan-out model. NOT Luna: this is a fan-out.")
    ap.add_argument("--effort", default="medium")
    ap.add_argument("--skip-normalize", action="store_true",
                    help="reuse a previous probe's normalized forms")
    args = ap.parse_args(argv)

    src = args.run / "specflow"
    contract = json.loads((args.run / "contract.json").read_text(encoding="utf-8"))
    contract_json = json.dumps(contract, indent=2, sort_keys=True)
    reqs = json.loads((src / "requirements.json").read_text(encoding="utf-8"))
    reqs = reqs.get("requirements") or reqs
    by_uid = {r["uid"]: r for r in reqs}
    testplan = json.loads((src / "testplan.json").read_text(encoding="utf-8"))
    testplan = testplan.get("elements") or testplan.get("testplan") or testplan
    stim = json.loads((src / "stimulus.json").read_text(encoding="utf-8"))
    stim_by_tp = {t["tp_uid"]: t.get("stimulus_steps") or []
                  for t in (stim.get("testpoints") or [])}

    # THE TARGET POPULATION: over-strict + vacuous, the two signs of one defect.
    oracles = json.loads((src / "oracles.json").read_text(encoding="utf-8"))
    disp = oracles.get("dispositions") or {}

    def dv(v):
        return v.get("disposition") if isinstance(v, dict) else v

    over = {u for u, v in disp.items() if dv(v) == "TRUSTED"} & set(
        oracles.get("unsatisfiable_by_the_control") or [])
    vac = {u for u, v in disp.items() if dv(v) == "VACUOUS"}
    target = sorted(over | vac)
    if args.limit:
        target = target[:args.limit]
    print(f"target: {len(target)} requirements "
          f"({len(over & set(target))} over-strict, {len(vac & set(target))} vacuous)")

    args.out.mkdir(parents=True, exist_ok=True)
    settings = PortSettings(model=args.model, effort=args.effort)

    # ---- half 1: does normalisation emit a window? -----------------------
    norm_path = args.out / "normalized.json"
    if args.skip_normalize and norm_path.exists():
        norm_by_uid = json.loads(norm_path.read_text(encoding="utf-8"))
    else:
        port = resumable(make_port("api", args.out, settings=settings), args.out)
        normed, _ = run_normalize_fanout(
            requirements=[by_uid[u] for u in target if u in by_uid],
            contract_json=contract_json, contract=contract, port=port)
        norm_by_uid = {n.req_uid: n.model_dump() for n in normed}
        norm_path.write_text(json.dumps(norm_by_uid, indent=2, sort_keys=True),
                             encoding="utf-8")

    windowed = [u for u, n in norm_by_uid.items()
                if (n.get("activation") or {}).get("until")]
    opens = [u for u, n in norm_by_uid.items()
             if (n.get("activation") or {}).get("opens_on")]
    print("\nHALF 1 -- normalisation")
    print(f"  carry a close condition (`until`): {len(windowed)}/{len(norm_by_uid)}")
    print(f"  carry an output trigger (`opens_on`): {len(opens)}/{len(norm_by_uid)}")

    # ---- half 2: does the check transcribe it? ---------------------------
    # RESUMABLE. `run_fanout` persists nothing per item, so a reclaim part
    # way through loses every call already paid for -- which is exactly how
    # this probe lost its second half once. A recorded response costs no call.
    port = resumable(make_port("api", args.out, settings=settings), args.out)
    got = run_oracle_gen(
        requirements=[by_uid[u] for u in target if u in by_uid],
        contract_json=contract_json, contract=contract, testplan=testplan,
        port=port, normalized=norm_by_uid, stimulus_by_tp=stim_by_tp,
        only=set(target))
    oracles_out = got[0] if isinstance(got, tuple) else got

    rows = []
    for o in oracles_out:
        uid = getattr(o, "req_uid", "")
        source = getattr(o, "source", "") or ""
        rows.append({
            "req_uid": uid,
            "operators": sorted(_calls(source)),
            "hand_rolled": _hand_rolled(source),
            "had_window": bool((norm_by_uid.get(uid, {}).get("activation")
                                or {}).get("until")),
            "source": source,
        })
    (args.out / "oracles.json").write_text(
        json.dumps(rows, indent=2, sort_keys=True), encoding="utf-8")

    # THE TWO DEFAULTS MOST OFTEN WRONG, now that both are reachable. Uptake
    # of `after` says the author found the window; these say it aimed it.
    follows = [r for r in rows if "after_activation" in r["source"]]
    strong = [r for r in rows if "strong=True" in r["source"]]
    used = [r for r in rows if r["operators"]]
    used_after = [r for r in rows if "after" in r["operators"]]
    hand = [r for r in rows if r["hand_rolled"]]
    print("\nHALF 2 -- check generation  (v1 baseline: 0 of 306 used any)")
    print(f"  call ANY temporal operator: {len(used)}/{len(rows)}")
    print(f"  call `after`:               {len(used_after)}/{len(rows)}")
    print(f"  still hand-roll an index:   {len(hand)}/{len(rows)}")
    print(f"  pass `after_activation`:   {len(follows)}/{len(rows)}  (derived; |=>)")
    print(f"  pass `strong=True`:        {len(strong)}/{len(rows)}  (authored; s_eventually)")

    # The conditional is the number that decides whether the SCHEMA is the
    # lever: uptake among checks that were actually handed a window.
    with_w = [r for r in rows if r["had_window"]]
    if with_w:
        hit = sum(1 for r in with_w if "after" in r["operators"])
        print(f"  of those GIVEN a window:   {hit}/{len(with_w)} used `after`")
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
