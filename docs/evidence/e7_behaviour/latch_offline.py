"""latch_offline.py -- would a different latch rule agree with golden? Tested on the audited commits.

FEEDBACK-AUDIT.md found that the editor's latch (passing shipped requirements rise; or hold with
the failing-testpoint gradient falling) is unrelated in direction to golden. This replays the
same 73 commits (feedback_audit.py) and asks, for each candidate rule, whether ITS accept / reject
decision lines up with golden. Every rule is golden-free: it uses only what a run has.

PRIMARY RULE, fixed before any result was computed:
  TARGETED   the current latch AND the commit changes outputs only on testpoints that belong to a
             requirement failing on the accepted design (the oracles' `tp_uids`). A commit that
             changes behaviour where every check was satisfied is rejected, whatever it repairs.
Secondary rules, reported with it:
  STRICT     the current latch AND no requirement broke, silenced or went dark
  CONSENSUS  the current latch AND agreement with the job's independent fresh samples does not
             fall (edges where every output equals the sample's; the samples other than the start)
  REF        the current latch AND agreement with the run's reference model does not fall
  TARGETED+CONSENSUS   both
  CONSENSUS-ONLY       agreement with the fresh samples rises (checks ignored)
  REF-ONLY             agreement with the reference model rises (checks ignored)
All behaviour is measured on the run's own stimulus (what the run itself can simulate), open
loop, from feedback_audit.py's cached traces.

LIMITATION: decisions are scored commit by commit. Under a different rule the session would have
gone differently after the first changed decision; this measures decision quality, not outcome.
-> docs/evidence/e7/LATCH-OFFLINE.json, tables on stdout.
"""

import glob
import json
import os
import re
import statistics as st
from math import comb
from pathlib import Path

EQ = Path(os.environ.get("E7_BEHAVIOUR_WORK", "/tmp/e7_behaviour"))
RUNS = Path(os.environ.get("E7_RUNS", "/home/user/runs-cf"))
HERE = Path(__file__).resolve().parent
E = HERE.parent / "e7"
_src = (HERE / "feedback_audit.py").read_text().split("\nout = {")[0]
FA = {"__file__": str(HERE / "feedback_audit.py"), "__name__": "feedback_audit"}
exec(compile(_src, str(HERE / "feedback_audit.py"), "exec"), FA)  # replay + simulator, no main
SH = FA["SH"]
POOL = {"i2c_master_byte_ctrl": ("acg1", "acg2", "acg3")}
POOL_DEFAULT = ("gen1", "gen2", "gen3")
#: The arm whose commits are tested: cf-checks (where the rules were chosen) or cf-model (held out).
ARM = os.environ.get("E7_ARM", "cf-checks")
SUFFIX = "" if ARM == "cf-checks" else f"-{ARM}"
AUD = {(j["module"], j["run"]): j["commits"]
       for j in json.loads((E / f"FEEDBACK-AUDIT{SUFFIX}.json").read_text())["jobs"]}


def num(s):
    try:
        return int(s, 16)
    except ValueError:
        return None


def agree_edges(x, y, run):
    """Edges where every output of x equals y's, on run's stimulus (traces: {run: {tp: rows}})."""
    e = t = 0
    for tp, a in x[run].items():
        b = y[run][tp]
        e += sum(ra == rb for ra, rb in zip(a, b))
        t += max(len(a), len(b))
    return e / t if t else None


def agree_ref(x, stim, run):
    e = t = 0
    for tp, rows in x[run].items():
        ref = stim["tps"][tp].get("ref") or []
        for i, row in enumerate(rows):
            t += 1
            exp = ref[i] if i < len(ref) else None
            e += exp is not None and all(num(s) == (int(v) if v is not None else None) for s, v in zip(row, exp))
    return e / t if t else None


def changed_tps(a, b, run):
    return {tp for tp in a[run] if a[run][tp] != b[run][tp]}


def fisher(a, b, c, d):
    n, r1, c1 = a + b + c + d, a + b, a + c
    if n == 0:
        return 1.0

    def p(x):
        return comb(r1, x) * comb(n - r1, c1 - x) / comb(n, c1)
    obs = p(a)
    return min(1.0, sum(p(x) for x in range(max(0, c1 - (n - r1)), min(r1, c1) + 1) if p(x) <= obs + 1e-12))


rows, checks = [], []
for traj_f in sorted(glob.glob(str(RUNS / "luna1*" / f"editor-{ARM}" / "*" / "debug_trajectory.jsonl"))):
    run, mod = traj_f.split("/")[-4], traj_f.split("/")[-2]
    if (mod, run) not in AUD:
        continue
    logs = sorted(glob.glob(str(RUNS / run / "results" / mod / f"{ARM}*" / "editor.log")))
    text = Path(logs[0]).read_text(errors="replace")
    traj = [json.loads(line) for line in open(traj_f)]
    start = ((E / run / "editor-cf-gen" / mod / "rtl.sv") if mod == "i2c_master_byte_ctrl"
             else (E / run / "editor" / mod / "rtl_generated.sv")).read_text()
    commits, final, _ = FA["replay"](start, traj, FA["log_records"](text, "input"), FA["log_records"](text, "output"))
    contract = json.loads((EQ / "corpora" / run / mod / "contract.json").read_text())
    stim = json.loads((EQ / "stim" / run / f"{mod}.json").read_text())
    sim = FA["simulator"](mod)
    tp_of = {o["req_uid"]: set(o.get("tp_uids") or [])
             for o in json.loads((RUNS / run / mod / "shipped.json").read_text())["oracles"]}
    pool = [json.loads((EQ / "out" / mod / f"{run}.{k}.json").read_text()) for k in POOL.get(mod, POOL_DEFAULT)]
    hist = json.loads((E / run / f"editor-{ARM}" / mod / "editor_summary.json").read_text())["history"]
    # session boundaries in commit order
    sess, s = [], 0
    prev = 0
    for r in traj:
        if r["iter"] <= prev:
            s += 1
        prev = r["iter"]
        if r["action"] == "commit":
            sess.append(s)
    failing, cur = None, -1
    for i, c in enumerate(commits):
        if sess[i] != cur:  # a session starts from the accepted design of the round history
            if failing is not None and cur >= 0:
                checks.append((f"{SH[mod]} {run}", cur, set(hist[cur + 1]["failing"]) == failing))
            cur = sess[i]
            failing = set(hist[cur]["failing"])
        aud = AUD[(mod, run)][i]
        req = c["requirements"]
        T = set().union(*[tp_of.get(q, set()) for q in failing]) if failing else set()
        if req and "cells_fixed" in aud:
            A, B = sim(c["before"], contract), sim(c["submitted"], contract)
            ch = changed_tps(A, B, run)
            a0, a1 = (int(x) for x in req["passing"].split(" -> "))
            rows.append({
                "job": f"{SH[mod]} {run}", "commit": i + 1, "latched": c["latched"], "dpass": a1 - a0,
                "broken": len(req["broken"]), "silenced": len(req["silenced"]) + len(req.get("went_dark_from_passing", [])),
                "tps_changed": len(ch), "tps_changed_outside": len(ch - T), "targeted_tps": len(T),
                "dcons": st.mean(agree_edges(B, p, run) - agree_edges(A, p, run) for p in pool),
                "dref": agree_ref(B, stim, run) - agree_ref(A, stim, run),
                "golden_net": aud["cells_fixed"] - aud["cells_broken"],
                "golden_net_own": aud["own"]["cells_fixed"] - aud["own"]["cells_broken"],
                "dedge": aud["edge_after"] - aud["edge_before"],
                "dedge_own": aud["own"]["edge_after"] - aud["own"]["edge_before"]})
        if c["latched"] and req:
            failing = (failing - set(req["repaired"]) - set(req["silenced"])) | set(req["broken"])
            want = int(req["failing"].split(" -> ")[1])
            if len(failing) != want:  # an uncovered requirement started failing: not in the lists
                failing |= set(re.findall(r"REQ-\d+", c.get("reason", "")))
    checks.append((f"{SH[mod]} {run}", cur, set(hist[cur + 1]["failing"]) == failing))

RULES = {
    "current": lambda r: r["latched"],
    "TARGETED (primary)": lambda r: r["latched"] and r["tps_changed_outside"] == 0,
    "STRICT": lambda r: r["latched"] and not r["broken"] and not r["silenced"],
    "CONSENSUS": lambda r: r["latched"] and r["dcons"] >= -1e-12,
    "REF": lambda r: r["latched"] and r["dref"] >= -1e-12,
    "TARGETED+CONSENSUS": lambda r: r["latched"] and r["tps_changed_outside"] == 0 and r["dcons"] >= -1e-12,
    "CONSENSUS-ONLY": lambda r: r["dcons"] > 1e-12,
    #: Specified before the held-out (cf-model) test was run, as its one secondary rule.
    "CONSENSUS + passing does not fall": lambda r: r["dcons"] > 1e-12 and r["dpass"] >= 0,
    "REF-ONLY": lambda r: r["dref"] > 1e-12,
}
print(f"{len(rows)} commits. Failing-list tracking matched the next round's history in "
      f"{sum(ok for *_, ok in checks)} of {len(checks)} session ends.\n")
print("Judged by golden: net cells fixed − broken; the own-stimulus column uses only the run's own testpoints.\n")
print("| rule | accepted | accepted: better / worse | rejected: better / worse | Fisher p | "
      "own stimulus: accepted better / worse, rejected better / worse, p | edges equal, accepted gains / losses (points) |")
print("|---|---|---|---|---|---|---|")
out = {"rows": rows, "session_checks": checks, "rules": {}}
for name, f in RULES.items():
    acc = [r for r in rows if f(r)]
    rej = [r for r in rows if not f(r)]
    ab, aw = sum(r["golden_net"] > 0 for r in acc), sum(r["golden_net"] < 0 for r in acc)
    rb, rw = sum(r["golden_net"] > 0 for r in rej), sum(r["golden_net"] < 0 for r in rej)
    ob, ow = sum(r["golden_net_own"] > 0 for r in acc), sum(r["golden_net_own"] < 0 for r in acc)
    qb, qw = sum(r["golden_net_own"] > 0 for r in rej), sum(r["golden_net_own"] < 0 for r in rej)
    gains = 100 * sum(r["dedge"] for r in acc if r["dedge"] > 0)
    losses = 100 * sum(r["dedge"] for r in acc if r["dedge"] < 0)
    p, po = fisher(ab, aw, rb, rw), fisher(ob, ow, qb, qw)
    out["rules"][name] = {"accepted": len(acc), "acc_better": ab, "acc_worse": aw, "rej_better": rb, "rej_worse": rw,
                          "p": p, "own": [ob, ow, qb, qw, po], "gains": gains, "losses": losses}
    print(f"| {name} | {len(acc)} | {ab} / {aw} | {rb} / {rw} | {p:.2f} | {ob} / {ow}, {qb} / {qw}, {po:.2f} | "
          f"{gains:+.2f} / {losses:+.2f} |")


def rank(v):
    o = sorted(range(len(v)), key=lambda i: v[i])
    r = [0.0] * len(v)
    i = 0
    while i < len(o):
        j = i
        while j + 1 < len(o) and v[o[j + 1]] == v[o[i]]:
            j += 1
        for k in range(i, j + 1):
            r[o[k]] = (i + j) / 2
        i = j + 1
    return r


def spearman(x, y):
    rx, ry = rank(x), rank(y)
    mx, my = st.mean(rx), st.mean(ry)
    num_ = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = (sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry)) ** 0.5
    return num_ / den if den else 0.0


print("\nSpearman correlation of each golden-free signal with golden's net cells (all commits):\n")
for lab, key in (("passing requirements, change", "dpass"), ("testpoints changed outside the failing requirements' (negated)", "out_neg"),
                 ("agreement with fresh samples, change", "dcons"), ("agreement with reference model, change", "dref")):
    xs = [(-r["tps_changed_outside"] if key == "out_neg" else r[key]) for r in rows]
    rho = spearman(xs, [r["golden_net"] for r in rows])
    out.setdefault("spearman", {})[key] = rho
    print(f"- {lab}: {rho:+.2f}")
(E / f"LATCH-OFFLINE{SUFFIX}.json").write_text(json.dumps(out, indent=1) + "\n")
