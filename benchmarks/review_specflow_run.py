#!/usr/bin/env python3
"""Review what a specflow run actually built: reference model and testcases.

A verdict says whether the loop accepted; it does not say whether the oracle
deserved to be believed. This reads the artifacts a run leaves behind and
reports the properties that decide that, each chosen because its failure has
been observed rather than imagined:

* a fragment that writes nothing is a requirement the model does not actually
  model -- the reference model still "covers" it structurally, which is exactly
  how a decomposition full of interface trivia passes G4 while encoding no
  behaviour;
* a testpoint whose stimulus is a single vector cannot distinguish a design from
  one that ignores its inputs, however many bins it hits;
* a bin every stimulus hits is a bin that cannot discriminate, so counting it in
  the denominator makes the coverage gate easier rather than harder;
* checks come from the coverage model rather than the testcase author, so the
  count of distinct checks per testpoint bounds what a testpoint can ever catch.

Read-only. Takes a run directory, prints a report, exits non-zero only if the
run produced nothing to review.
"""

from __future__ import annotations

import argparse
import ast
import json
from collections import Counter
from pathlib import Path


def _load(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def review_refmodel(sf: Path) -> None:
    src_path = sf / "ref_model.py"
    print("== reference model ==")
    if not src_path.exists():
        print("  absent -- the run did not get past G4")
        return
    src = src_path.read_text(encoding="utf-8")
    tree = ast.parse(src)
    cls = next(
        (n for n in ast.walk(tree) if isinstance(n, ast.ClassDef) and n.name == "Model"),
        None,
    )
    if cls is None:
        print("  no Model class -- the file will not import")
        return

    methods = {n.name: n for n in cls.body if isinstance(n, ast.FunctionDef)}
    frags = sorted(n for n in methods if n.startswith("_req_"))
    dispatch = [n for n in ("evaluate", "step") if n in methods]

    # A fragment that assigns into `o` models something; one that does not is
    # structurally present and behaviourally empty.
    writes: dict[str, set[str]] = {}
    for name in frags:
        keys: set[str] = set()
        for node in ast.walk(methods[name]):
            if isinstance(node, ast.Subscript) and isinstance(node.ctx, ast.Store):
                if isinstance(node.value, ast.Name) and node.value.id == "o":
                    if isinstance(node.slice, ast.Constant):
                        keys.add(str(node.slice.value))
                    else:
                        keys.add("<computed>")
        writes[name] = keys

    empty = [n for n, k in writes.items() if not k]
    ports = sorted({p for k in writes.values() for p in k if p != "<computed>"})
    print(f"  fragments      : {len(frags)}")
    print(f"  dispatch       : {', '.join(dispatch) or 'MISSING (inherits and raises)'}")
    print(f"  output ports written: {ports or 'none'}")
    print(f"  fragments writing nothing: {len(empty)}/{len(frags)}"
          + (f"  -> {', '.join(empty[:8])}" if empty else ""))
    if empty:
        print("     (a no-op fragment satisfies G4's traceability check while")
        print("      encoding no behaviour -- usually an S1 decomposition that")
        print("      turned interface declarations into requirements)")
    print(f"  lines          : {len(src.splitlines())}")


def review_testcases(sf: Path) -> None:
    print("\n== testcases ==")
    suite = sf / "suite"
    manifest = _load(suite / "manifest.json")
    if manifest is None:
        print("  no suite rendered -- the run did not get past G5")
        return

    cov = _load(sf / "coverage_model.json") or {}
    bins = cov.get("bins") or []
    checks = cov.get("checks") or []
    tests_dir = suite / "tests"
    modules = sorted(tests_dir.glob("test_*.py")) if tests_dir.exists() else []
    print(f"  modules        : {len(modules)}")
    print(f"  bins / checks  : {len(bins)} / {len(checks)}")

    # How much stimulus does each testpoint actually apply, and how many
    # distinct checks can it fire? Both bound what the testpoint can detect.
    drives = Counter()
    check_calls = Counter()
    for m in modules:
        try:
            t = ast.parse(m.read_text(encoding="utf-8"))
        except SyntaxError:
            print(f"  {m.name}: DOES NOT PARSE")
            continue
        for node in ast.walk(t):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if node.func.attr == "drive":
                    drives[m.stem] += 1
                elif node.func.attr == "check":
                    check_calls[m.stem] += 1
                elif node.func.attr == "hit":
                    pass
        # The honest measure is the length of the stimulus list actually
        # iterated. The renderer binds it to a module-level name
        # (`STIMULUS = [...]`) rather than inlining it, so resolve names before
        # counting -- a walk that only matches `for stim in [literal]` reports
        # every testpoint as single-vector, which is a property of the walk and
        # not of the suite.
        consts = {
            tgt.id: len(node.value.elts)
            for node in t.body
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.List)
            for tgt in node.targets
            if isinstance(tgt, ast.Name)
        }
        for node in ast.walk(t):
            if isinstance(node, ast.For):
                if isinstance(node.iter, ast.List):
                    drives[m.stem] = max(drives[m.stem], len(node.iter.elts))
                elif isinstance(node.iter, ast.Name):
                    drives[m.stem] = max(drives[m.stem], consts.get(node.iter.id, 0))

    if modules:
        vals = [drives[m.stem] for m in modules]
        singles = [m.stem for m in modules if drives[m.stem] <= 1]
        print(f"  stimulus/testpoint: min={min(vals)} max={max(vals)} "
              f"mean={sum(vals)/len(vals):.1f}")
        if singles:
            print(f"  single-vector testpoints: {len(singles)}/{len(modules)}"
                  f" -> {', '.join(singles[:6])}")
            print("     (one vector cannot distinguish a design from one that")
            print("      ignores its inputs, however many bins it hits)")

    for path in sorted((suite / "results").glob("*.json")) if (suite / "results").exists() else []:
        data = _load(path) or {}
        print(f"  result {data.get('tp_uid')}: {data.get('status')} "
              f"checks={len(data.get('checks_invoked') or [])} "
              f"bins={len(data.get('bins_hit') or [])} "
              f"mismatches={len(data.get('mismatches') or [])}")


def review_gates(sf: Path) -> None:
    print("\n== gates ==")
    any_gate = False
    for name in ("s1", "s2", "s3", "refmodel"):
        g = _load(sf / f"{name}_gate.json")
        if g is None:
            continue
        any_gate = True
        print(f"  {name:9} ok={g.get('ok')} rounds={g.get('rounds')} "
              f"issues={len(g.get('issues') or [])}")
    if not any_gate:
        print("  none recorded")


def review_requirements(sf: Path) -> None:
    reqs = _load(sf / "requirements.json")
    print("\n== requirements ==")
    if not reqs:
        print("  none -- S1 did not complete")
        return
    items = reqs.get("requirements") or []
    with_ports = [r for r in items if r.get("ports")]
    print(f"  count          : {len(items)}")
    print(f"  with ports     : {len(with_ports)}")
    print(f"  underdetermined: {len(reqs.get('underdetermined') or [])}")
    for r in items[:40]:
        print(f"    {r.get('uid')} ports={','.join(r.get('ports') or []) or '-'}"
              f"  {(r.get('text') or '')[:96]}")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="review_specflow_run")
    p.add_argument("run_dir")
    args = p.parse_args(argv)

    sf = Path(args.run_dir) / "specflow"
    if not sf.exists():
        print(f"no specflow/ under {args.run_dir} -- nothing to review")
        return 1
    print(f"reviewing {sf}\n")
    review_gates(sf)
    review_requirements(sf)
    review_refmodel(sf)
    review_testcases(sf)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
