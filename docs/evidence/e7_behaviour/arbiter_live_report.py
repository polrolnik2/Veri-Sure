"""arbiter_live_report.py RUN:MODULE ... -- matched live sessions, consensus latch with and without the spec arbiter.

For each job, the sessions tagged `<PREFIX>cons-fv` (the consensus latch at its 0.5-point
tolerance) and `<PREFIX>cons-fv-arb` (the same, with `--arbiter`), started from the same design
with the same budget. Golden is used only here, to score:
  - the delivered design: edges and testpoints equal to golden, and output cells fixed / broken
    against the start (open loop, every run's stimulus, golden X don't-care, as metrics.py);
  - every commit: how the latch decided it (agreement rose / spec judgment / tolerance / refused),
    the judge's score when it was asked, and golden's net cells for the commit itself;
  - output tokens: the editor's, and the judge's.
Counts and verdicts only; no model text. PREFIX defaults to smokem6- (E7_PREFIX).
"""

import json
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
_src = (HERE / "feedback_audit.py").read_text().split("\nout = {")[0]
FA = {"__file__": str(HERE / "feedback_audit.py"), "__name__": "feedback_audit"}
exec(compile(_src, str(HERE / "feedback_audit.py"), "exec"), FA)  # replay + simulator, no main
EQ = Path(os.environ.get("E7_BEHAVIOUR_WORK", "/tmp/e7_behaviour"))
RUNS = Path(os.environ.get("E7_RUNS", "/home/user/runs-cf"))
E = HERE.parent / "e7"
PREFIX = os.environ.get("E7_PREFIX", "smokem6-")
S = Path(os.environ.get("E7_SCRATCH", "/tmp/claude-0/-home-user-Veri-Sure/12bb865e-7a51-5506-b55a-e5ac7cf72a4a/"
                        "scratchpad/cf"))


def start_of(run, mod):
    return ((S / "gen" / f"{run}.{mod}.sv") if mod == "i2c_master_byte_ctrl"
            else (E / run / "editor" / mod / "rtl_generated.sv")).read_text()


def how(reason, latched):
    if not latched:
        return "refused"
    for k, v in (("ON AGREEMENT", "agreement rose"), ("ON THE SPECIFICATION", "spec judge"),
                 ("WITHIN TOLERANCE", "tolerance")):
        if k in reason:
            return v
    return "other"


out = {"prefix": PREFIX, "jobs": []}
for job in sys.argv[1:]:
    run, mod = job.split(":")
    G = json.loads((EQ / "out" / mod / "golden.json").read_text())
    contract = json.loads((EQ / "corpora" / run / mod / "contract.json").read_text())
    sim = FA["simulator"](mod)
    #: bit_ctrl's golden never resets dout and resets its capture registers low (golden_variants.py):
    #: absolute scores are also given against the corrected reference gC
    GC = None
    if mod == "i2c_master_bit_ctrl":
        sys.path.insert(0, str(HERE))
        from golden_variants import bit_ctrl_corrected
        GC = sim(bit_ctrl_corrected((FA["DES"] / "i2c" / mod / f"{mod}.v").read_text())[1], contract)
    start = start_of(run, mod)
    S0 = sim(start, contract)
    print(f"\n## {FA['SH'][mod]} {run}\n")
    for arm in ("cons-fv", "cons-fv-arb"):
        tag = PREFIX + arm
        log_f = RUNS / run / "results" / mod / tag / "editor.log"
        traj_f = RUNS / run / f"editor-{tag}" / mod / "debug_trajectory.jsonl"
        if not log_f.is_file() or not traj_f.is_file():
            print(f"- {arm}: not run or not finished")
            continue
        log = log_f.read_text(errors="replace")
        outs = FA["log_records"](log, "output")
        commits, final, miss = FA["replay"](start, [json.loads(x) for x in open(traj_f)],
                                            FA["log_records"](log, "input"), outs)
        arbs = [FA["result_json"](r).get("arbitration") for t, r in outs if t == "commit"]
        delivered = (RUNS / run / f"editor-{tag}" / mod / "rtl.sv").read_text()
        fin = FA["compare"](S0, sim(delivered, contract), G)
        d = RUNS / run / f"editor-{tag}" / mod
        ed_tok = sum(json.loads(x).get("output", 0) for x in open(d / "usage.jsonl")) if (d / "usage.jsonl").is_file() else None
        calls = d / "spec_arbiter" / "calls.jsonl"
        j_tok = sum(json.loads(x)["output_tokens"] for x in open(calls)) if calls.is_file() else 0
        row = {"arm": arm, "commits": [], "replay_reproduces": FA["norm"](final) == FA["norm"](delivered),
               "unresolved_edits": miss, "edge_start": fin["edge_before"], "edge_final": fin["edge_after"],
               "tp_start": fin["tp_before"], "tp_final": fin["tp_after"], "cells_fixed": fin["cells_fixed"],
               "cells_broken": fin["cells_broken"], "editor_output_tokens": ed_tok, "judge_output_tokens": j_tok}
        for i, c in enumerate(commits):
            g = FA["compare"](sim(c["before"], contract), sim(c["submitted"], contract), G)
            a = arbs[i] if i < len(arbs) else None
            m = re.search(r"([\d.]+)% -> ([\d.]+)%", c["reason"])
            w = re.search(r"on ([\d.]+)% of edges \(was ([\d.]+)%\)", c["reason"])  # LATCHED ON AGREEMENT
            agreement = m.groups() if m else (w.group(2), w.group(1)) if w else None
            row["commits"].append({"how": how(c["reason"], c["latched"]),
                                   "passing": (c["requirements"] or {}).get("passing"),
                                   "agreement": agreement,
                                   "judge_score": None if not a else a.get("score"),
                                   "judge_tokens": None if not a else a.get("tokens"),
                                   "golden_net": g["cells_fixed"] - g["cells_broken"],
                                   "golden_fixed": g["cells_fixed"], "golden_broken": g["cells_broken"]})
        out["jobs"].append({"run": run, "module": mod, **row})
        if GC is not None:
            fc = FA["compare"](S0, sim(delivered, contract), GC)
            row["corrected"] = {k: fc[k] for k in ("edge_before", "edge_after", "tp_before", "tp_after",
                                                   "cells_fixed", "cells_broken")}
        print(f"- **{arm}**: final {100 * fin['edge_after']:.1f}% edges (start {100 * fin['edge_before']:.1f}%), "
              f"{100 * fin['tp_after']:.1f}% testpoints (start {100 * fin['tp_before']:.1f}%); cells "
              f"+{fin['cells_fixed']} / -{fin['cells_broken']} vs start; tokens editor {ed_tok}, judge {j_tok}"
              + ("" if row["replay_reproduces"] else "; REPLAY DIFFERS"))
        if GC is not None:
            fc = row["corrected"]
            print(f"  - against the corrected reference gC: final {100 * fc['edge_after']:.1f}% edges (start "
                  f"{100 * fc['edge_before']:.1f}%), {100 * fc['tp_after']:.1f}% testpoints (start "
                  f"{100 * fc['tp_before']:.1f}%); cells +{fc['cells_fixed']} / -{fc['cells_broken']}")
        for k, c in enumerate(row["commits"], 1):
            agr = f"{c['agreement'][0]}->{c['agreement'][1]}%" if c["agreement"] else "?"
            jd = "" if c["judge_score"] is None else f", judge {c['judge_score']:+.2f}"
            verdict = ("right" if (c["how"] != "refused") == (c["golden_net"] > 0) else "wrong") if c["golden_net"] else "neutral"
            print(f"  - commit {k}: {c['how']}; passing {c['passing']}, agreement {agr}{jd}; golden "
                  f"+{c['golden_fixed']} / -{c['golden_broken']} -> decision {verdict}")
    del G
if not os.environ.get("E7_NO_WRITE"):
    (E / f"ARBITER-LIVE-{PREFIX.rstrip('-')}.json").write_text(json.dumps(out, indent=1, default=str) + "\n")
