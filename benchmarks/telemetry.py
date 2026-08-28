#!/usr/bin/env python3
"""Every run's telemetry, extracted from its artifacts into one row.

WHY EXTRACTED AND NOT TYPED IN. Numbers in this project have had to be
retracted twice, both times because a figure was transcribed into prose and
then read back without its provenance. So nothing here is hand-entered: every
column is read out of an artifact the run wrote, and a column whose artifact is
absent stays EMPTY rather than becoming 0. "not measured" and "measured as
zero" are different findings, and a spreadsheet that renders them identically
is how the first retraction happened.

THE CONFOUND COLUMNS ARE NOT DECORATION. `bound`, `small_model`,
`small_effort`, `commit` and `reuse` sit beside the results because every
comparison this project has got wrong was got wrong by comparing two runs that
differed in one of them:

  * a stage run bounded by the WITNESS was compared against a baseline bounded
    by witness+control -- a strictly weaker test, so 7 of 17 "trusted" checks
    were ones the control fails;
  * a probe's normalized forms predated a gate by eleven minutes, so three
    clock-as-edge activations survived into the measurement;
  * an effort raised from medium to high would have put a second variable
    beside the change under test.

A row without those columns cannot be compared to another row, so they come
first, before anything anyone wants to look at.

    python benchmarks/telemetry.py --run /home/user/runs/c1-i2c
    python benchmarks/telemetry.py --run ... --csv benchmarks/telemetry.csv
    python benchmarks/telemetry.py --run ... --by-stage
"""

from __future__ import annotations

import argparse
import collections
import csv
import datetime as dt
import json
import pathlib
import re
import subprocess

#: Column order. Provenance and confounds first -- see the module docstring.
COLUMNS = [
    "run", "packaged_utc", "commit", "task",
    "small_model", "small_effort", "big_model", "big_effort", "bound", "reuse",
    # cost
    "calls", "input_tokens", "cached_tokens", "cache_hit_pct",
    "output_tokens", "reasoning_tokens", "continuations",
    "debug_input", "debug_cached", "debug_output", "debug_cache_hit_pct",
    # oracle stage
    "requirements", "trusted", "abandoned", "vacuous", "oracle_invalid",
    "unobservable", "considered", "oracle_rounds", "variants",
    "over_strict_vs_control", "over_strict_after_repair",
    "stimulus_added", "testpoints_no_oracle_names",
    # downstream
    "conforms", "violates", "not_exercised",
    "adequate", "inadequate", "adequacy_unknown",
    "golden_pass", "candidate_pass", "separation",
    # THE PAPER'S HEADLINE PAIR. `syntax_pass` is the compile gate; ChipVerilog
    # is level-aware and never reaches a functional verdict without it, so a
    # functional number quoted without it is unreadable. `functional_pass` is
    # the verifier's own status, and `flow` says WHICH oracle produced it --
    # only 6 task dirs ship a testbench, so for most tasks this is an
    # equivalence result and NOT a testbench pass rate. Reporting it as one is
    # the mistake benchmarks/baselines/'s README exists to prevent.
    # THE MISS RATE. `self_tb_pass` is the pipeline's verdict on its OWN
    # testbench; `functional_pass` is the held-out verifier's. `tb_agreement`
    # crosses them, and `miss` is the cell that matters: the pipeline declared
    # the RTL good and the golden oracle disagreed. That is the inert-testbench
    # failure this project exists to prevent, and it is invisible in either
    # column alone -- a run reporting only self_tb_pass reports its own opinion
    # of itself.
    "produced_rtl", "syntax_pass", "self_tb_pass", "tb_agreement",
    "functional_pass", "verdict",
    "flow", "proof_type", "cv_compile_gate", "formal_status",
    "interface_status", "reference_precheck", "verdict_reason",
    # health
    "gates_ok", "leaf_exception", "done_rc",
]

#: An `agent_io` filename minus its per-item and per-round parts. The whole
#: point is to group a FAMILY of calls that share a prompt prefix, which is the
#: same unit `prompt_cache_key` groups by -- so a cache rate per stage here is
#: comparable to the routing the key requests.
_STAGE = re.compile(r"^(.*?)(?:_REQ-\d+.*|_TP-\d+.*|_\d+.*)?(?:_r\d+)?_meta\.json$")


def _stage_of(name: str) -> str:
    m = _STAGE.match(name)
    base = m.group(1) if m else name
    return re.sub(r"_(fix\d|r\d)$", "", base) or "?"


def _load(path: pathlib.Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _pct(part, whole):
    """None -- not a zero -- when the denominator is absent or empty."""
    if not whole:
        return None
    return round(100.0 * part / whole, 1)


def calls_by_stage(run: pathlib.Path) -> dict[str, dict]:
    """Per-stage token totals, read from every `*_meta.json` the run wrote."""
    out: dict[str, dict] = collections.defaultdict(
        lambda: {"calls": 0, "input": 0, "cached": 0, "cache_write": 0,
                 "output": 0, "reasoning": 0, "continuations": 0,
                 "models": set(), "efforts": set()})
    for p in sorted((run / "agent_io").glob("*_meta.json")):
        d = _load(p)
        if not isinstance(d, dict):
            continue
        u = d.get("usage") or {}
        det = u.get("input_tokens_details") or {}
        odet = u.get("output_tokens_details") or {}
        s = out[_stage_of(p.name)]
        s["calls"] += 1
        s["input"] += int(u.get("input_tokens") or 0)
        s["cached"] += int(det.get("cached_tokens") or 0)
        s["cache_write"] += int(det.get("cache_write_tokens") or 0)
        s["output"] += int(u.get("output_tokens") or 0)
        s["reasoning"] += int(odet.get("reasoning_tokens") or 0)
        s["continuations"] += int(d.get("continuations") or 0)
        if d.get("served_model"):
            s["models"].add(str(d["served_model"]))
        eff = ((d.get("generate_kwargs") or {}).get("reasoning") or {}).get("effort")
        if eff:
            s["efforts"].add(str(eff))
    return dict(out)


def _git_commit(repo: pathlib.Path) -> str:
    try:
        return subprocess.run(["git", "-C", str(repo), "rev-parse", "--short", "HEAD"],
                              capture_output=True, text=True, timeout=10).stdout.strip()
    except Exception:  # noqa: BLE001 -- provenance missing is not fatal
        return ""


def row_for(run: pathlib.Path, repo: pathlib.Path) -> dict:
    sf = run / "specflow"
    r: dict = {c: "" for c in COLUMNS}
    r["run"] = run.name
    r["packaged_utc"] = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    r["commit"] = _git_commit(repo)

    # ---- cost, from every recorded call ------------------------------------
    stages = calls_by_stage(run)
    if stages:
        tot = {k: sum(s[k] for s in stages.values())
               for k in ("calls", "input", "cached", "output", "reasoning",
                         "continuations")}
        r.update(calls=tot["calls"], input_tokens=tot["input"],
                 cached_tokens=tot["cached"], output_tokens=tot["output"],
                 reasoning_tokens=tot["reasoning"],
                 continuations=tot["continuations"])
        hit = _pct(tot["cached"], tot["input"])
        r["cache_hit_pct"] = "" if hit is None else hit
        # SPLIT, NOT LUMPED. `--full-strength-stages` defaults to
        # refmodel,witness, so a run legitimately uses two models -- and a
        # single column holding "gpt-5-mini,gpt-5.6-luna" cannot be compared
        # against another run's, which is the whole job of a confound column.
        big = {"refmodel", "witness"}
        def _join(keys, field):
            return ",".join(sorted({v for k, s in stages.items() if k in keys
                                    for v in s[field]}))
        small_keys = set(stages) - big
        r["small_model"] = _join(small_keys, "models")
        r["small_effort"] = _join(small_keys, "efforts")
        r["big_model"] = _join(big & set(stages), "models")
        r["big_effort"] = _join(big & set(stages), "efforts")

    # ---- the debug loop, which is its own budget ---------------------------
    # Newest round only: turns are cumulative, so summing them double-counts.
    rounds = sorted((sf / "judge").glob("r*/trust.json")) if (sf / "judge").is_dir() else []
    if rounds:
        t = _load(rounds[-1]) or {}
        dtk = t.get("debug_tokens") or {}
        r["debug_input"] = dtk.get("input", "")
        # ABSENT, NOT ZERO. A run from before the third counter reached the
        # artifact has no `cached` key at all, and writing 0 there would claim
        # a measured 0% cache rate on the largest line in the ledger.
        r["debug_cached"] = dtk.get("cached", "")
        r["debug_output"] = dtk.get("output", "")
        if isinstance(dtk.get("cached"), int) and dtk.get("input"):
            r["debug_cache_hit_pct"] = _pct(dtk["cached"], dtk["input"])
        counts = t.get("mechanical_verdicts") or t.get("counts") or {}
        for k, col in (("CONFORMS", "conforms"), ("VIOLATES", "violates"),
                       ("NOT_EXERCISED", "not_exercised")):
            if k in counts:
                r[col] = counts[k]

    # ---- the oracle stage --------------------------------------------------
    o = _load(sf / "oracles.json")
    if isinstance(o, dict):
        disp = o.get("dispositions") or {}
        c = collections.Counter(
            (v.get("disposition") if isinstance(v, dict) else v) for v in disp.values())
        r.update(requirements=len(disp), trusted=c.get("TRUSTED", 0),
                 abandoned=c.get("ABANDONED", 0), vacuous=c.get("VACUOUS", 0),
                 oracle_invalid=c.get("ORACLE_INVALID", 0),
                 unobservable=c.get("UNOBSERVABLE", 0),
                 considered=o.get("considered", ""),
                 oracle_rounds=o.get("rounds", ""),
                 variants=o.get("variants", ""),
                 bound=o.get("over_strictness_bounded_by") or o.get("witness") or "",
                 over_strict_vs_control=len(o.get("unsatisfiable_by_the_control") or []),
                 over_strict_after_repair=len(o.get("over_strict_after_repair") or []),
                 stimulus_added=len(o.get("stimulus_added") or {}),
                 testpoints_no_oracle_names=len(o.get("testpoints_no_oracle_names") or []))

    # ---- adequacy ----------------------------------------------------------
    adq = sorted(sf.glob("adequacy_r*.json"))
    if adq:
        a = _load(adq[-1]) or {}
        counts = a.get("counts") or {}
        r.update(adequate=counts.get("adequate", ""),
                 inadequate=counts.get("inadequate", ""),
                 adequacy_unknown=counts.get("unknown", ""))

    # ---- golden_check ------------------------------------------------------
    for name in ("golden_check.json", "golden.json"):
        g = _load(run / name) or _load(sf / name)
        if isinstance(g, dict):
            r["golden_pass"] = g.get("golden_pass", g.get("golden", ""))
            r["candidate_pass"] = g.get("candidate_pass", g.get("candidate", ""))
            r["separation"] = g.get("separation", "")
            break

    # ---- syntax and functional, the pair a paper reports --------------------
    base = _load(run / "baseline.json")
    if isinstance(base, dict):
        cg = base.get("compile_gate") or {}
        r["syntax_pass"] = cg.get("status", "")
        # `no candidate RTL was produced` is a DIFFERENT failure from RTL that
        # does not compile, and collapsing them loses the distinction between
        # "the pipeline made nothing" and "the pipeline made something wrong".
        r["produced_rtl"] = "no" if "no candidate RTL" in str(cg.get("reason", "")) else "yes"
        # Both arms record this: chipverilog_arm_a.py:177 and
        # run_chipverilog.py:313. Absent (an older run, or one that never got
        # far enough to simulate) stays empty rather than becoming "no" -- "did
        # not pass" and "was never asked" are different, and only the first
        # belongs in a miss rate's denominator.
        if "is_sim_pass" in base:
            r["self_tb_pass"] = "yes" if base.get("is_sim_pass") else "no"

    sc = _load(run / "score.json")
    if isinstance(sc, dict):
        status = sc.get("status", "")
        r["verdict"] = status
        r["functional_pass"] = ("yes" if status == "pass"
                                else "" if status in ("timeout", "tool_error")
                                else "no")
        r.update(flow=sc.get("flow", ""), proof_type=sc.get("proof_type", ""),
                 cv_compile_gate=sc.get("compile_gate_status", ""),
                 formal_status=sc.get("formal_status", ""),
                 interface_status=sc.get("interface_status", ""),
                 reference_precheck=sc.get("reference_precheck", ""),
                 verdict_reason=str(sc.get("reason", ""))[:160].replace("\n", " "))

    # ---- the two testbenches, crossed --------------------------------------
    self_tb, golden = r["self_tb_pass"], r["functional_pass"]
    if self_tb and golden:
        r["tb_agreement"] = {
            ("yes", "yes"): "agree_pass",
            # THE ONE TO COUNT: the pipeline passed its own testbench and the
            # held-out oracle failed the same RTL.
            ("yes", "no"): "miss",
            ("no", "no"): "agree_fail",
            # The opposite error, and worth its own name rather than being
            # folded in: the pipeline's testbench was stricter than the
            # verifier, which costs a good design rather than passing a bad one.
            ("no", "yes"): "self_tb_over_strict",
        }.get((self_tb, golden), "")

    # ---- health ------------------------------------------------------------
    gates = [p for p in sf.glob("*_gate.json")]
    if gates:
        oks = [(_load(p) or {}).get("ok") for p in gates]
        r["gates_ok"] = f"{sum(1 for v in oks if v is True)}/{len(oks)}"
    # THE TELL THAT AN EXIT CODE HIDES. A leaf exception is caught and reported
    # as a result, so a run that produced nothing still writes done=0.
    r["leaf_exception"] = "yes" if (run / "leaf_exception.txt").exists() else "no"
    done = run / "done"
    r["done_rc"] = done.read_text(encoding="utf-8").strip() if done.exists() else ""
    return r


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", required=True, type=pathlib.Path, action="append",
                    help="a run directory; repeat for several")
    ap.add_argument("--csv", type=pathlib.Path,
                    help="append a row per run, creating the header if needed. "
                         "A run already present is REPLACED, so re-running "
                         "after a stage completes updates rather than duplicates")
    ap.add_argument("--by-stage", action="store_true",
                    help="per-stage call and cache breakdown, which is where a "
                         "cache rate is actually actionable: the floor is per "
                         "prefix, so one stage below it drags a total nobody "
                         "can then attribute")
    args = ap.parse_args(argv)
    repo = pathlib.Path(__file__).resolve().parents[1]

    rows = []
    for run in args.run:
        if not run.is_dir():
            print(f"!! {run} is not a directory; skipped")
            continue
        rows.append(row_for(run, repo))

        if args.by_stage:
            stages = calls_by_stage(run)
            print(f"\n{run.name} -- per stage")
            print(f"  {'stage':22} {'calls':>6} {'input':>12} {'cached':>12} "
                  f"{'hit%':>6} {'output':>10}")
            for name, s in sorted(stages.items(), key=lambda kv: -kv[1]["input"]):
                hit = _pct(s["cached"], s["input"])
                # A stage under the 1024-token floor caches NOTHING, so a 0
                # there is the floor rather than a broken cache. Flagged, not
                # silently averaged into the total.
                avg_in = s["input"] / s["calls"] if s["calls"] else 0
                flag = "  <- under the 1024-token cache floor" if avg_in < 1024 else ""
                print(f"  {name:22} {s['calls']:6} {s['input']:12,} "
                      f"{s['cached']:12,} {'' if hit is None else hit:>6} "
                      f"{s['output']:10,}{flag}")

    for row in rows:
        print(f"\n{row['run']}")
        for c in COLUMNS:
            if row[c] != "":
                print(f"  {c:28} {row[c]}")

    if args.csv and rows:
        path = args.csv
        existing: list[dict] = []
        if path.exists():
            with path.open(newline="", encoding="utf-8") as fh:
                existing = [r for r in csv.DictReader(fh)]
        names = {r["run"] for r in rows}
        merged = [r for r in existing if r.get("run") not in names] + rows
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=COLUMNS, extrasaction="ignore")
            w.writeheader()
            for r in merged:
                w.writerow({c: r.get(c, "") for c in COLUMNS})
        print(f"\nwrote {path} ({len(merged)} run(s))")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
