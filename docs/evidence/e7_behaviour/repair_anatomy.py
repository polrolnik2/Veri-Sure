"""repair_anatomy.py -- what the checks-only repair changed, output by output, and why so little.

For each checks-arm job (`cfc`) against its start (`r0`; `cfg` for byte_ctrl):

  PORTS     per spec output: the share of edges equal to golden for the start, the final and the
            job's fresh samples (as in checks_vs_ablation.py), on every run's stimulus, open loop,
            golden X don't-care.
  EDGES     every (edge, output) where the final differs from its start, classed against golden:
            fixed (start wrong, final right), broken (start right, final wrong), still wrong
            (both wrong, differently), or golden don't-care. Also per whole edge (all outputs).
  EDITS     the editor's edit calls and where they went: into commits that latched, commits that
            did not (reverted), discarded, or never committed (counts only; the editor logs under
            E7_RUNS). And the final's net difference from its start in RTL lines, with probe logic
            and as delivered (probes stripped).
  CHECKS    the shipped requirements the repair moved from failing to passing (and back), and what
            their checks read: a spec output, or only probes (internal signals the contract names).

Reads EQ/out traces, the evidence tree's RTL, the corpora's shipped checks and probes, and the
editor logs (E7_RUNS). Prints counts and names only. -> docs/evidence/e7/REPAIR-ANATOMY.json
"""

import difflib
import glob
import json
import os
import re
import statistics as st
from pathlib import Path

EQ = Path(os.environ.get("E7_BEHAVIOUR_WORK", "/tmp/e7_behaviour"))
RUNS = Path(os.environ.get("E7_RUNS", "/home/user/runs-cf"))
E = Path(__file__).resolve().parents[1] / "e7"
SH = {"i2c_master_bit_ctrl": "bit_ctrl", "i2c_master_byte_ctrl": "byte_ctrl",
      "or1200_dc_fsm": "dc_fsm", "or1200_sb": "sb"}
ABL = {"i2c_master_byte_ctrl": ("cfg", "acg1", "acg2", "acg3")}
ABL_DEFAULT = ("gen1", "gen2", "gen3", "r0")
START = {"i2c_master_byte_ctrl": "cfg"}
EDITS = {"replace_block", "edit", "add_block", "remove_block"}


def dc(v):
    return any(c in v for c in "xXzZ")


def load(mod, name):
    f = EQ / "out" / mod / f"{name}.json"
    return json.loads(f.read_text()) if f.is_file() else None


def port_agree(x, G, n):
    ok, tot = [0] * n, [0] * n
    for r in G:
        for tp, g in G[r].items():
            d = x[r][tp]
            for i in range(max(len(g), len(d))):
                for k in range(n):
                    if i < len(g) and dc(g[i][k]):
                        continue
                    tot[k] += 1
                    ok[k] += i < len(g) and i < len(d) and d[i][k] == g[i][k]
    return [a / b if b else None for a, b in zip(ok, tot)]


def decompose(s, f, G, n):
    """Per output and per whole edge: unchanged right/wrong, fixed, broken, still wrong, don't-care."""
    keys = ("same_right", "same_wrong", "fixed", "broken", "still_wrong", "dc_changed")
    per = [dict.fromkeys(keys, 0) for _ in range(n)]
    edge = dict.fromkeys(keys, 0)
    for r in G:
        for tp, g in G[r].items():
            a, b = s[r][tp], f[r][tp]
            for i in range(min(len(g), len(a), len(b))):
                er_s = er_f = True
                changed = False
                for k in range(n):
                    gv, sv, fv = g[i][k], a[i][k], b[i][k]
                    if dc(gv):
                        per[k]["dc_changed" if sv != fv else "same_right"] += 0 if sv == fv else 1
                        continue
                    rs, rf = sv == gv, fv == gv
                    er_s &= rs
                    er_f &= rf
                    if sv == fv:
                        per[k]["same_right" if rs else "same_wrong"] += 1
                    else:
                        changed = True
                        per[k]["fixed" if rf else "broken" if rs else "still_wrong"] += 1
                if not changed:
                    edge["same_right" if er_s else "same_wrong"] += 1
                else:
                    edge["fixed" if er_f and not er_s else "broken" if er_s and not er_f
                         else "still_wrong" if not er_s and not er_f else "same_right"] += 1
    return per, edge


def rtl_diff(a, b):
    """Net changed lines between two RTL texts, ignoring whitespace-only and blank lines."""
    def norm(t):
        return [re.sub(r"\s+", " ", ln).strip() for ln in t.splitlines() if ln.strip()]
    added = removed = 0
    for ln in difflib.unified_diff(norm(a), norm(b), lineterm="", n=0):
        if ln.startswith("+") and not ln.startswith("+++"):
            added += 1
        elif ln.startswith("-") and not ln.startswith("---"):
            removed += 1
    return added, removed


def assigned(a, b):
    """Signals assigned on the lines the final changed relative to its start (LHS of = / <=)."""
    def norm(t):
        return [re.sub(r"\s+", " ", ln).strip() for ln in t.splitlines() if ln.strip()]
    lhs = {}
    for ln in difflib.unified_diff(norm(a), norm(b), lineterm="", n=0):
        if ln[:1] in "+-" and ln[:3] not in ("+++", "---"):
            for m in re.finditer(r"(?:^|[\s;(])(?:assign\s+)?(\w+)(?:\[[^\]]*\])?\s*<?=(?!=)", ln[1:]):
                if m.group(1) not in ("if", "else", "case", "begin", "end", "parameter", "localparam"):
                    lhs[m.group(1)] = lhs.get(m.group(1), 0) + 1
    return dict(sorted(lhs.items(), key=lambda kv: -kv[1]))


def editor_edits(run, mod):
    """Edit calls by fate: latched, not latched (reverted), rejected, discarded, never committed."""
    logs = sorted(glob.glob(str(RUNS / run / "results" / mod / "cf-checks*" / "editor.log")))
    if not logs:
        return None
    fate = {"edits": 0, "commits": 0, "latched_rise": 0, "latched_gradient": 0, "not_latched": 0,
            "rejected": 0, "edits_latched": 0, "edits_reverted": 0, "edits_discarded": 0,
            "edits_uncommitted": 0, "launches": len(logs)}
    call = re.compile(r'"name": "_tool_(\w+)",\s*"input"')
    res = re.compile(r'"name": "_tool_commit",\s*"output"')
    anyname = re.compile(r'"name": "_tool_\w+"')
    for p in logs:
        text = open(p, errors="replace").read()
        if not call.search(text):
            continue
        marks = [m.start() for m in anyname.finditer(text)] + [len(text)]

        def upto_next(pos):
            nxt = next(x for x in marks if x > pos)
            return text[pos:nxt]
        evs = sorted([(m.start(), "call", m.group(1)) for m in call.finditer(text)]
                     + [(m.start(), "commit_result", upto_next(m.start() + 1)) for m in res.finditer(text)])
        pending = 0
        for _, kind, val in evs:
            if kind == "call":
                if val in EDITS:
                    fate["edits"] += 1
                    pending += 1
                elif val == "discard_staged":
                    fate["edits_discarded"] += pending
                    pending = 0
                elif val == "commit":
                    fate["commits"] += 1
            else:
                if "LATCHED ON THE GRADIENT" in val:
                    fate["latched_gradient"] += 1
                    fate["edits_latched"] += pending
                elif "LATCHED: passing requirements" in val:
                    fate["latched_rise"] += 1
                    fate["edits_latched"] += pending
                elif "did NOT latch" in val:
                    fate["not_latched"] += 1
                    fate["edits_reverted"] += pending
                else:
                    fate["rejected"] += 1
                    fate["edits_reverted"] += pending
                pending = 0
        fate["edits_uncommitted"] += pending
    return fate if fate["edits"] or fate["commits"] else None


def reads(run, mod, outs):
    """Requirement -> (spec outputs read, probes read) by its shipped check."""
    d = RUNS / run / mod
    probes = {p["name"] for p in json.loads((d / "probes.json").read_text())["probes"]}
    ports = set(outs) - probes
    r = {}
    for o in json.loads((d / "shipped.json").read_text())["oracles"]:
        names = set(re.findall(r"""["'](\w+)["']""", o.get("source") or ""))
        r[o["req_uid"]] = (sorted(names & ports), sorted(names & probes))
    return r


def summary(run, mod, kind):
    tag = {"cfc": "cf-checks", "cfg": "cf-gen"}[kind]
    return json.loads((E / run / f"editor-{tag}" / mod / "editor_summary.json").read_text())


out = {"jobs": []}
R = {(r["module"], r["run"], r["kind"]): r for r in json.loads((EQ / "latency.json").read_text())}
jobs = sorted({(m, run) for (m, run, k) in R if k == "cfc"}, key=lambda j: (SH[j[0]], j[1]))
for mod in sorted({m for m, _ in jobs}, key=lambda m: SH[m]):
    G = load(mod, "golden")
    some = next(iter(json.loads((EQ / "stim" / r / f"{mod}.json").read_text()) for r in ("luna12",)))
    outs = some["outputs"]
    n = len(outs)
    for m, run in [j for j in jobs if j[0] == mod]:
        sk = START.get(mod, "r0")
        S, F = load(mod, f"{run}.{sk}"), load(mod, f"{run}.cfc")
        pool = {k: port_agree(load(mod, f"{run}.{k}"), G, n) for k in ABL.get(mod, ABL_DEFAULT)}
        pa_s, pa_f = pool.get(sk) or port_agree(S, G, n), port_agree(F, G, n)
        per, edge = decompose(S, F, G, n)
        # RTL: start and final, with probes and as delivered
        if mod in ABL:
            s_full = (E / run / "editor-cf-gen" / mod / "rtl.sv").read_text()
            s_del = (E / run / "editor-cf-gen" / mod / "rtl_deliverable.sv").read_text()
        else:
            s_full = (E / run / "editor" / mod / "rtl_generated.sv").read_text()
            s_del = (EQ / "designs" / run / mod / "r0.sv").read_text()
        f_full = (E / run / "editor-cf-checks" / mod / "rtl.sv").read_text()
        f_del = (E / run / "editor-cf-checks" / mod / "rtl_deliverable.sv").read_text()
        rd = reads(run, mod, outs)
        sm = summary(run, mod, "cfc")
        h0, hf = sm["history"][0], sm["final"]
        f0, ff = set(h0["failing"]), set(hf["failing"])
        a0, af = set(h0.get("abstaining", [])), set(hf.get("abstaining", []))
        fixed_req = sorted((f0 | a0) - ff - af)
        broke_req = sorted(ff - f0)
        cls = {"port": 0, "probe_only": 0, "unknown": 0}
        for q in fixed_req:
            p, pr = rd.get(q, (None, None))
            cls["unknown" if p is None else "port" if p else "probe_only"] += 1
        all_cls = {"port": sum(1 for p, _ in rd.values() if p), "probe_only": sum(1 for p, _ in rd.values() if not p)}
        job = {
            "module": mod, "run": run, "outputs": outs,
            "ports": {o: {"start": pa_s[k], "final": pa_f[k],
                          "pool_mean": st.mean(pool[x][k] for x in pool if pool[x][k] is not None)
                          if any(pool[x][k] is not None for x in pool) else None,
                          "pool": [pool[x][k] for x in pool], **per[k]} for k, o in enumerate(outs)},
            "edges": edge,
            "rtl_lines": {"start_full": len(s_full.splitlines()), "final_full": len(f_full.splitlines()),
                          "diff_full": rtl_diff(s_full, f_full), "diff_delivered": rtl_diff(s_del, f_del)},
            "assigned_in_diff": assigned(s_del, f_del),
            "editor": editor_edits(run, mod),
            "checks": {"start_pass": h0["pass"], "final_pass": hf["pass"], "requirements": hf["requirements"],
                       "fixed": fixed_req, "broke": broke_req, "fixed_by_read": cls, "shipped_by_read": all_cls,
                       "ports_read_by_fixed": sorted({p for q in fixed_req for p in rd.get(q, ([], []))[0]}),
                       "probes_read_by_fixed": sorted({p for q in fixed_req for p in rd.get(q, ([], []))[1]})},
        }
        out["jobs"].append(job)
        del S, F
    del G

print("## Whole edges, start -> checks final (% of compared edges)\n")
print("| job | changed | fixed | broken | still wrong | net | RTL lines changed, with probes / delivered | "
      "edit calls: latched / reverted / discarded / never committed | commits latched / not | "
      "requirements fixed: read a port / probes only |")
print("|---|---|---|---|---|---|---|---|---|---|")
for j in out["jobs"]:
    e = j["edges"]
    tot = sum(e.values())
    ch = e["fixed"] + e["broken"] + e["still_wrong"]
    ed = j["editor"] or {}
    df, dd = j["rtl_lines"]["diff_full"], j["rtl_lines"]["diff_delivered"]
    c = j["checks"]["fixed_by_read"]
    print(f"| {SH[j['module']]} {j['run']} | {100 * ch / tot:.1f} | {100 * e['fixed'] / tot:.1f} | "
          f"{100 * e['broken'] / tot:.1f} | {100 * e['still_wrong'] / tot:.1f} | "
          f"{100 * (e['fixed'] - e['broken']) / tot:+.1f} | +{df[0]}/−{df[1]} / +{dd[0]}/−{dd[1]} | "
          + (f"{ed['edits_latched']} / {ed['edits_reverted']} / {ed['edits_discarded']} / {ed['edits_uncommitted']} | "
             f"{ed['latched_rise'] + ed['latched_gradient']} / {ed['not_latched'] + ed['rejected']} | "
             if ed else "lost | lost | ")
          + f"{c['port']} / {c['probe_only']} |")

print("\n## Per output: edges equal to golden (%), start -> final, and the fresh samples\n")
print("Only outputs whose agreement moved by at least 0.5 points, or that the fixed checks read.\n")
print("| job | output | start | final | fresh samples min–max (mean) | fixed | broken | still wrong | "
      "read by a fixed check |")
print("|---|---|---|---|---|---|---|---|---|")
for j in out["jobs"]:
    rf = set(j["checks"]["ports_read_by_fixed"])
    for o, p in j["ports"].items():
        if p["start"] is None or p["final"] is None:
            continue
        if abs(p["final"] - p["start"]) < 0.005 and o not in rf:
            continue
        pool = [v for v in p["pool"] if v is not None]
        tot = p["same_right"] + p["same_wrong"] + p["fixed"] + p["broken"] + p["still_wrong"]
        print(f"| {SH[j['module']]} {j['run']} | {o} | {100 * p['start']:.1f} | {100 * p['final']:.1f} | "
              f"{100 * min(pool):.1f}–{100 * max(pool):.1f} ({100 * st.mean(pool):.1f}) | "
              f"{100 * p['fixed'] / tot:.2f} | {100 * p['broken'] / tot:.2f} | {100 * p['still_wrong'] / tot:.2f} | "
              f"{'yes' if o in rf else ''} |")

print("\n## Outputs the final moves outside the fresh samples' range, and what the diff assigns\n")
print("| job | outputs above every fresh sample | outputs below every fresh sample | port-edges fixed / broken (all outputs) | "
      "signals assigned on changed lines |")
print("|---|---|---|---|---|")
for j in out["jobs"]:
    up, dn = [], []
    fx = bk = 0
    for o, p in j["ports"].items():
        pool = [v for v in p["pool"] if v is not None]
        fx += p["fixed"]
        bk += p["broken"]
        if p["final"] is None or not pool:
            continue
        if p["final"] > max(pool) + 5e-4:
            up.append(f"{o} {100 * p['final']:.1f} (max {100 * max(pool):.1f})")
        if p["final"] < min(pool) - 5e-4:
            dn.append(f"{o} {100 * p['final']:.1f} (min {100 * min(pool):.1f})")
    j["outside_pool"] = {"above": up, "below": dn, "port_edges_fixed": fx, "port_edges_broken": bk}
    asg = ", ".join(f"{k} {v}" for k, v in list(j["assigned_in_diff"].items())[:8])
    print(f"| {SH[j['module']]} {j['run']} | {'; '.join(up) or '-'} | {'; '.join(dn) or '-'} | {fx} / {bk} | {asg or '-'} |")

(E / "REPAIR-ANATOMY.json").write_text(json.dumps(out, indent=1) + "\n")
