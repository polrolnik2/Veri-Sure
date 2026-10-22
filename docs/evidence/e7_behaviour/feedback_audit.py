"""feedback_audit.py -- was the editor's feedback right, commit by commit?

The checks-only editor judges each commit on the shipped checks: "passing requirements a -> b,
repairing X, but Y BROKE", latched or not. This replays every checks-arm editing session exactly
and scores every design the editor submitted against golden, then sets the two side by side.

REPLAY. The session's own records give every staged edit:
  - debug_trajectory.jsonl: the order of actions, session (round) boundaries, each edit's
    success, `remove_block`'s removed text and `add_block`'s code, and `replace_block`'s diff of
    the block before -> after;
  - editor.log: each tool call's exact input (`replace_block` new code, `edit` old/new text), and
    each commit's verdict: latched, the requirements repaired / broken / silenced, staged kept.
Edits are applied with the editor's own splice (`_EditSession._splice`, whitespace-tolerant
matching included). A replaced block's prior text is the parsed block whose diff against the new
code reproduces the recorded diff exactly. A job counts only if the replay reproduces the RTL the
job delivered.

SCORING. Every submitted design and every accepted design is simulated as in sim.py (open loop,
every run's stimulus, golden X don't-care, probes stripped). Per commit:
  delta   the submitted design minus the accepted one: edges equal to golden, whole testpoints
          equal, and (edge, output) cells fixed / broken
  verdict latched or not, and what the feedback reported broken
Classes: a TRUE ACCEPT latches a change golden agrees is better; a FALSE ACCEPT latches one golden
scores worse; a FALSE REJECT throws away one golden scores better; a TRUE REJECT throws away one
golden scores worse; NEUTRAL changes nothing golden can see on this stimulus.

Reads E7_RUNS (editor logs and trajectories) and EQ (testbench, stimulus, golden traces). Writes
EQ/feedback_audit/ (designs and traces, regenerable) and docs/evidence/e7/FEEDBACK-AUDIT.json
(scores, verdicts and requirement ids only).
"""

import difflib
import glob
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, "/home/user/Veri-Sure")
sys.path.insert(0, "/home/user/Veri-Sure/benchmarks")
from eda_agent.rtl_editor import _EditSession  # noqa: E402
from eda_agent.strip_probes import deliverable  # noqa: E402
from eda_agent.trace_slicer import parse_rtl_blocks  # noqa: E402
from run_chipverilog import child_sources, submodules  # noqa: E402

EQ = Path(os.environ.get("E7_BEHAVIOUR_WORK", "/tmp/e7_behaviour"))
RUNS = Path(os.environ.get("E7_RUNS", "/home/user/runs-cf"))
E = Path(__file__).resolve().parents[1] / "e7"
DES = Path("/home/user/Veri-Sure/benchmarks/chipverilog/Des")
SH = {"i2c_master_bit_ctrl": "bit_ctrl", "i2c_master_byte_ctrl": "byte_ctrl",
      "or1200_dc_fsm": "dc_fsm", "or1200_sb": "sb"}
EDITS = ("replace_block", "edit", "add_block", "remove_block")
WORK = EQ / "feedback_audit"
dec = json.JSONDecoder()


def log_records(text, key):
    """Tool calls ("input") or results ("output") in log order: [(tool, record)]."""
    out = []
    for m in re.finditer(r'"name": "_tool_(\w+)",\s*"%s"' % key, text):
        pos, lo = m.start(), max(0, m.start() - 400)
        for st in [b.start() + lo for b in re.finditer(r"\{", text[lo:pos])][::-1]:
            try:
                o, end = dec.raw_decode(text, st)
            except ValueError:
                continue
            if end > pos:
                out.append((m.group(1), o))
                break
    return out


def result_json(rec):
    o = rec["output"]
    o = o[0] if isinstance(o, list) else o
    try:
        return json.loads(o["text"])
    except (KeyError, TypeError, ValueError):
        return {}


class Shim(_EditSession):
    """Just the editor's buffer: accepted RTL in a file, staged text in memory."""

    def __init__(self, rtl):  # noqa: D401 -- deliberately not the session's __init__
        self.rtl_path = tempfile.NamedTemporaryFile("w", suffix=".sv", delete=False).name
        self.write_rtl(rtl)
        self.staged_rtl = None
        self.staged_text = {}
        self.retired_ids = set()


def udiff(before, after, bid):
    return "".join(difflib.unified_diff(before.splitlines(keepends=True), after.splitlines(keepends=True),
                                        fromfile=f"{bid}.before", tofile=f"{bid}.after", n=2))


def reverse_patch(after, recorded):
    """The block's text before the edit, from its text after and the recorded unified diff."""
    al = after.splitlines(keepends=True)
    out, ptr = [], 0
    lines = recorded.splitlines(keepends=True)
    i = 0
    while i < len(lines):
        m = re.match(r"@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@", lines[i])
        i += 1
        if not m:
            continue
        c, d = int(m.group(1)), int(m.group(2) if m.group(2) is not None else 1)
        upto = c if d == 0 else c - 1
        out += al[ptr:upto]
        ptr = upto
        while i < len(lines) and not lines[i].startswith("@@"):
            ln = lines[i]
            if ln[:1] in (" ", "-"):
                out.append(ln[1:])
            if ln[:1] in (" ", "+"):
                ptr += 1
            i += 1
    out += al[ptr:]
    return "".join(out)


def block_before(sh, bid, new_code, recorded):
    if recorded:
        b = reverse_patch(new_code, recorded)
        if udiff(b, new_code, bid) == recorded:
            return b
    cands = []
    if bid in sh.staged_text:
        cands.append(sh.staged_text[bid])
    for text in (sh.staged(), sh.read_rtl()):
        cands += [b.code for b in parse_rtl_blocks(text) if b.id == bid]
        cands += [b.code for b in parse_rtl_blocks(text)]
    for c in cands:
        if udiff(c, new_code, bid) == recorded:
            return c
    return None


def replay(start, traj, calls, results):
    """-> (submitted designs with their verdicts, final accepted RTL, unresolved edits)."""
    sh = Shim(start)
    ci = {t: [c for tt, c in calls if tt == t] for t in ("replace_block", "edit")}
    cr = [r for t, r in results if t == "commit"]
    k = {"replace_block": 0, "edit": 0, "commit": 0}
    commits, miss = [], 0
    batch_miss = 0  # unresolved edits in the batch now staged
    prev_iter = 0
    for r in traj:
        if r["iter"] <= prev_iter:  # a new session (round) starts from the accepted RTL
            sh.staged_rtl, sh.staged_text, sh.retired_ids = None, {}, set()
            batch_miss = 0
        m0 = miss
        prev_iter = r["iter"]
        a = r["action"]
        if a in ("replace_block", "edit"):
            inp = ci[a][k[a]]["input"]
            k[a] += 1
            if not r["accepted"]:
                continue
            if a == "edit":
                res = sh._splice(inp["old_text"], inp["new_text"], "edit")
            else:
                before = block_before(sh, r["block_id"], inp["new_code"], r["diff"] or "")
                if before is None:
                    miss += 1
                    continue
                res = sh._splice(before, inp["new_code"].rstrip("\n"), "replace")
                if res.get("is_action_executed"):
                    sh.staged_text[r["block_id"]] = inp["new_code"].rstrip("\n")
            miss += not res.get("is_action_executed")
        elif a == "remove_block" and r["accepted"]:
            res = sh._splice(r["diff"] or "", "", "remove")
            miss += not res.get("is_action_executed")
            sh.retired_ids.add(r["block_id"])
        elif a == "add_block" and r["accepted"]:
            body = (r["diff"] or "").rstrip("\n")
            if r["block_id"] == "endmodule":
                sh.staged_rtl = sh.staged().replace("endmodule", body + "\n\nendmodule", 1)
            else:
                anchor = sh.staged_text.get(r["block_id"]) or next(
                    (b.code for b in parse_rtl_blocks(sh.staged()) if b.id == r["block_id"]), None)
                res = sh._splice(anchor, anchor + "\n\n" + body, "add") if anchor else {}
                miss += not res.get("is_action_executed")
        elif a == "discard_staged":
            sh.staged_rtl, sh.staged_text, sh.retired_ids = None, {}, set()
            batch_miss = 0
        elif a == "commit":
            res = cr[k["commit"]]
            k["commit"] += 1
            j = result_json(res)
            reason = (j.get("accept_reason") or "") + " " + (j.get("error_msg") or "")
            latched = bool(j.get("is_action_executed")) and "LATCHED" in reason
            commits.append({"before": sh.read_rtl(), "submitted": sh.staged(), "latched": latched,
                            "requirements": j.get("requirements"), "reason": reason.strip()[:300],
                            "rejected_before_sim": "requirements" not in j, "exact": batch_miss == 0})
            if latched:
                sh.write_rtl(sh.staged())
                sh.staged_rtl, sh.staged_text, sh.retired_ids = None, {}, set()
                batch_miss = 0
        batch_miss += miss - m0
    final = sh.read_rtl()
    os.unlink(sh.rtl_path)
    return commits, final, miss


def norm(t):
    return re.sub(r"\s+", " ", t).strip()


def simulator(mod):
    task = next(p.parent for p in DES.rglob("description.txt") if p.parent.name == mod)
    kids = [Path(p) for p in child_sources(submodules(task, mod))]
    runs = [r for r in ("luna12", "luna13", "luna14", "luna15") if (EQ / "stim" / r / f"{mod}.json").is_file()]
    tps = {r: sorted(json.loads((EQ / "stim" / r / f"{mod}.json").read_text())["tps"]) for r in runs}
    cache = {}

    def run(rtl, contract):
        text = deliverable(rtl, contract) or rtl
        h = hashlib.sha256(text.encode()).hexdigest()[:16]
        if h in cache:
            return cache[h]
        d = WORK / mod
        d.mkdir(parents=True, exist_ok=True)
        if (d / f"{h}.json").is_file():
            cache[h] = json.loads((d / f"{h}.json").read_text())
            return cache[h]
        src, vvp = d / f"{h}.sv", d / f"{h}.vvp"
        src.write_text(text)
        have = set(re.findall(r"^\s*module\s+(\w+)", text, re.M))
        libs = [str(k) for k in kids if k.stem not in have]
        c = subprocess.run(["iverilog", "-g2012", "-s", "tb", "-o", str(vvp), f"-I{task}", f"-I{task.parent}",
                            str(EQ / "work" / mod / "tb.v"), str(src), *libs], capture_output=True, text=True)
        if c.returncode:
            cache[h] = None
            return None
        res = {}
        for r in runs:
            o = d / f"{h}.{r}.out"
            subprocess.run(["vvp", "-n", str(vvp), f"+in={EQ / 'stimtxt' / r / f'{mod}.txt'}", f"+out={o}"],
                           capture_output=True, text=True, timeout=3600)
            per, cur = {tp: [] for tp in tps[r]}, -1
            for line in o.read_text().splitlines():
                if line == "#":
                    cur += 1
                else:
                    per[tps[r][cur]].append(line.split())
            o.unlink()
            res[r] = per
        vvp.unlink(missing_ok=True)
        (d / f"{h}.json").write_text(json.dumps(res))
        cache[h] = res
        return res
    return run


def dc(v):
    return any(c in v for c in "xXzZ")


def compare(A, B, G):
    """A = accepted, B = submitted: edges / testpoints equal to golden for each, and cells fixed / broken."""
    ea = eb = et = ta = tb = tt = fx = bk = 0
    pfx, pbk = {}, {}
    for r in G:
        for tp, g in G[r].items():
            a, b = A[r][tp], B[r][tp]
            oka = okb = True
            for i in range(len(g)):
                ra = rb = True
                for k, gv in enumerate(g[i]):
                    if dc(gv):
                        continue
                    va = i < len(a) and a[i][k] == gv
                    vb = i < len(b) and b[i][k] == gv
                    ra &= va
                    rb &= vb
                    fx += vb and not va
                    bk += va and not vb
                    if vb != va:
                        (pfx if vb else pbk)[k] = (pfx if vb else pbk).get(k, 0) + 1
                ea += ra
                eb += rb
                oka &= ra
                okb &= rb
            et += len(g)
            ta += oka
            tb += okb
            tt += 1
    return {"edge_before": ea / et, "edge_after": eb / et, "tp_before": ta / tt, "tp_after": tb / tt,
            "cells_fixed": fx, "cells_broken": bk, "port_fixed": pfx, "port_broken": pbk}


out = {"jobs": []}
for traj_f in sorted(glob.glob(str(RUNS / "luna1*" / "editor-cf-checks" / "*" / "debug_trajectory.jsonl"))):
    run, mod = traj_f.split("/")[-4], traj_f.split("/")[-2]
    logs = sorted(glob.glob(str(RUNS / run / "results" / mod / "cf-checks*" / "editor.log")))
    if len(logs) != 1:
        print(f"{SH[mod]} {run}: skipped ({len(logs)} launches; the trajectory holds only the last)")
        continue
    text = Path(logs[0]).read_text(errors="replace")
    traj = [json.loads(line) for line in open(traj_f)]
    start = ((E / run / "editor-cf-gen" / mod / "rtl.sv") if mod == "i2c_master_byte_ctrl"
             else (E / run / "editor" / mod / "rtl_generated.sv")).read_text()
    commits, final, miss = replay(start, traj, log_records(text, "input"), log_records(text, "output"))
    delivered = (E / run / "editor-cf-checks" / mod / "rtl.sv").read_text()
    ok = norm(final) == norm(delivered)
    print(f"{SH[mod]} {run}: {len(commits)} commits replayed, {miss} edits unresolved, "
          f"final {'REPRODUCED' if ok else 'DIFFERS'}", flush=True)
    if not ok:
        continue
    G = json.loads((EQ / "out" / mod / "golden.json").read_text())
    contract = json.loads((EQ / "corpora" / run / mod / "contract.json").read_text())
    sim = simulator(mod)
    rows = []
    for i, c in enumerate(commits):
        A, B = sim(c["before"], contract), sim(c["submitted"], contract)
        row = {"commit": i + 1, "latched": c["latched"], "requirements": c["requirements"],
               "rejected_before_sim": c["rejected_before_sim"], "compiles": B is not None,
               "exact": c["exact"]}
        if A is not None and B is not None:
            row.update(compare(A, B, G))
            outs = json.loads((EQ / "stim" / run / f"{mod}.json").read_text())["outputs"]
            row["port_fixed"] = {outs[k]: v for k, v in row["port_fixed"].items()}
            row["port_broken"] = {outs[k]: v for k, v in row["port_broken"].items()}
            own = compare(A, B, {run: G[run]})  # the stimulus the shipped checks see
            row["own"] = {k: own[k] for k in ("edge_before", "edge_after", "cells_fixed", "cells_broken")}
        rows.append(row)
    out["jobs"].append({"module": mod, "run": run, "commits": rows})
    del G

(E / "FEEDBACK-AUDIT.json").write_text(json.dumps(out, indent=1) + "\n")
