"""arbitration_offline.py -- can a narrow spec judgment decide the commits the latch cannot?

LATCH-OFFLINE.md: when a commit raises passing requirements but costs a little agreement with
the fresh samples, agreement no longer separates real fixes from regressions (dc_fsm luna14's fix
and sb luna12's regression both lose ~0.85 points). TARGETED ARBITRATION asks a judge about only
the cells the commit changed: the spec, the ports, and one testpoint's excerpt in which the design
before and after the commit got the same inputs and their outputs diverge. Which one does the
spec require? The judge never sees golden, the peers, the checks or which candidate is the edit.

TARGETS. Every audited commit (LATCH-OFFLINE.json, both arms) on which the signals conflict:
passing requirements rose, agreement neither rose by the 0.1-point margin nor fell by 2 points,
and golden sees a change. Plus the live consensus-latch runs' commits in the same range
(dc_fsm luna14's refused fixes, the tolerance-1 smoke runs), deduplicated by behaviour.

EPISODES. On the run's own stimulus, each testpoint where the two designs' outputs differ is one
episode: from the first differing row, the differing rows within HORIZON rows. K episodes per
commit, drawn with probability proportional to their changed cells. Each is asked twice, the
candidates' labels swapped, so a position preference cancels.

SCORING (golden only here). Episode truth: after-correct minus before-correct cells, golden X
don't-care. A commit is accepted when the cell-weighted vote favours the edit. Set against the
consensus latch at tolerance 0.5 and 1 and against golden's net cells (all runs' stimulus and the
run's own).

VARIANT 2 (ARB_VARIANT=2), designed from variant 1's errors on these same commits, so tuned
rather than tested: (a) the judge is told whether each configuration macro the spec names is
defined, by preprocessing the design's own include files (sb's spec describes the module with and
without its store buffer; or1200_defines.v leaves it out); (b) it must quote the governing spec
sentences and rebuild every internal register the marked outputs depend on, edge by edge, before
comparing (dc_fsm's write enables depend on a cache-inhibit flag set one edge after a request is
accepted, not on the input).

Judge prompts and replies stay in EQ/arbitration (private); the repo gets counts and verdicts.
ARB_DRY=1 lists targets and episodes without calling; ARB_LIMIT=N stops after N new calls.
-> docs/evidence/e7/ARBITRATION-OFFLINE.json, tables on stdout.
"""

import asyncio
import glob
import hashlib
import json
import os
import random
import re
import statistics as st
import sys
import urllib.parse
from pathlib import Path

EQ = Path(os.environ.get("E7_BEHAVIOUR_WORK", "/tmp/e7_behaviour"))
RUNS = Path(os.environ.get("E7_RUNS", "/home/user/runs-cf"))
HERE = Path(__file__).resolve().parent
E = HERE.parent / "e7"
_src = (HERE / "feedback_audit.py").read_text().split("\nout = {")[0]
FA = {"__file__": str(HERE / "feedback_audit.py"), "__name__": "feedback_audit"}
exec(compile(_src, str(HERE / "feedback_audit.py"), "exec"), FA)  # replay + simulator, no main
SH, DES = FA["SH"], FA["DES"]
LONG = {v: k for k, v in SH.items()}
POOL = {"i2c_master_byte_ctrl": ("acg1", "acg2", "acg3")}
K, HORIZON, CONTEXT = int(os.environ.get("ARB_K", "4")), 16, 24
EFFORT = os.environ.get("ARB_EFFORT", os.environ.get("OPENAI_REASONING_EFFORT", "xhigh"))
VARIANT = os.environ.get("ARB_VARIANT", "1")
CALLS = EQ / "arbitration" / "calls"
LIVE = [("luna14", "or1200_dc_fsm", "val-cons-fv"), ("luna12", "or1200_sb", "smoket1-cons-fv"),
        ("luna14", "or1200_dc_fsm", "smoket1b-cons-fv")]


def in_range(dpass, dcons):
    return dpass > 0 and -0.02 < dcons < 0.001


def start_of(run, mod):
    return ((E / run / "editor-cf-gen" / mod / "rtl.sv") if mod == "i2c_master_byte_ctrl"
            else (E / run / "editor" / mod / "rtl_generated.sv")).read_text()


def replay(run, mod, log, traj):
    text = Path(log).read_text(errors="replace")
    t = [json.loads(line) for line in open(traj)]
    return FA["replay"](start_of(run, mod), t, FA["log_records"](text, "input"), FA["log_records"](text, "output"))[0]


def agree(x, y, run):
    e = n = 0
    for tp, a in x[run].items():
        b = y[run][tp]
        e += sum(ra == rb for ra, rb in zip(a, b))
        n += max(len(a), len(b))
    return e / n


def episodes(A, B, run, G):
    """Per testpoint of the run's own stimulus: the first divergence and the changed cells after it."""
    out = []
    for tp in sorted(A[run]):
        a, b, g = A[run][tp], B[run][tp], G[run][tp]
        diff = [i for i in range(min(len(a), len(b))) if a[i] != b[i]]
        if not diff:
            continue
        rows = [i for i in diff if i < diff[0] + HORIZON]
        cells = [(i, k) for i in rows for k in range(len(a[i])) if a[i][k] != b[i][k]]
        scored = [(i, k) for i, k in cells if i < len(g) and not FA["dc"](g[i][k])]
        out.append({"tp": tp, "first": rows[0], "end": rows[-1], "cells": len(cells),
                    "before_ok": sum(a[i][k] == g[i][k] for i, k in scored),
                    "after_ok": sum(b[i][k] == g[i][k] for i, k in scored)})
    return out


def pick(eps, seed):
    rng, pool, chosen = random.Random(seed), list(eps), []
    while pool and len(chosen) < K:
        r, acc = rng.random() * sum(e["cells"] for e in pool), 0
        for j, e in enumerate(pool):
            acc += e["cells"]
            if acc >= r:
                chosen.append(pool.pop(j))
                break
    return chosen


SYSTEM = """You are a hardware verification judge. You are given a module's specification, its \
ports, and a simulation excerpt in which two candidate implementations of the module, X and Y, \
received exactly the same inputs. Their outputs differ on the rows marked <<. Decide from the \
specification alone which candidate's outputs on the marked rows are the ones the specification \
requires. Work through the specification's behaviour cycle by cycle over the excerpt. If the \
specification does not determine the marked outputs, answer "undetermined"; if neither \
candidate matches it, answer "both wrong". Reply with one JSON object and nothing else: \
{"verdict": "X" | "Y" | "both wrong" | "undetermined", "reason": "<one sentence>"}"""


SYSTEM2 = """You are a hardware verification judge. You are given a module's specification, its \
build configuration, its ports, and a simulation excerpt in which two candidate implementations of \
the module, X and Y, received exactly the same inputs. Their outputs differ on the rows marked <<. \
Decide which candidate's outputs on the marked rows are the ones the specification requires, for \
this configuration. Proceed in order: (1) quote the specification sentences that determine each \
differing output, including the internal registers and flags they depend on and when each is \
updated; (2) rebuild those registers and flags from reset, edge by edge, through the excerpt, as \
the specification defines their updates -- a registered flag takes its new value only after the \
clock edge, so do not substitute an input for a flag on the same row unless the specification \
makes it combinational; (3) compute the value the specification requires on each marked row; \
(4) compare with X and Y. If the specification does not determine the marked outputs, answer \
"undetermined"; if neither candidate matches it, answer "both wrong". End your reply with one JSON \
object: {"verdict": "X" | "Y" | "both wrong" | "undetermined", "reason": "<one sentence>"}"""
if VARIANT == "2":
    SYSTEM = SYSTEM2


def configuration(mod):
    """The state of every macro the spec names, from preprocessing the design's own include files."""
    task = next(p.parent for p in DES.rglob("description.txt") if p.parent.name == mod)
    spec = (task / "description.txt").read_text()
    defs = sorted({p for d in (task, task.parent) for p in d.glob("*define*.v")})
    known = set(re.findall(r"define\s+(\w+)", "".join(p.read_text(errors="replace") for p in defs)))
    names = sorted(set(re.findall(r"\b[A-Z][A-Z0-9_]*_[A-Z0-9_]+\b", spec)) & known)
    if not names:
        return ""
    probe = "".join(f'`include "{p.name}"\n' for p in defs) + "".join(
        f"`ifdef {n}\nDEFINED {n} = `{n}\n`else\nUNDEFINED {n} =\n`endif\n" for n in names)
    d = EQ / "arbitration"
    d.mkdir(parents=True, exist_ok=True)
    (d / "probe.v").write_text(probe)
    out = __import__("subprocess").run(["iverilog", "-E", f"-I{task}", f"-I{task.parent}", "-o", "/dev/stdout",
                                        str(d / "probe.v")], capture_output=True, text=True).stdout
    state = {n: (d, v.strip()) for d, n, v in re.findall(r"^(DEFINED|UNDEFINED) (\w+) =(.*)$", out, re.M)}
    return "".join(f"- {n} is NOT defined\n" if state.get(n, ("UNDEFINED",))[0] == "UNDEFINED" else
                   f"- {n} is defined" + (f" as {state[n][1]}\n" if state[n][1] else "\n") for n in names)


def hexw(v, w):
    return format(int(v), "x").zfill(max(1, -(-w // 4)))


def prompt(mod, run, ep, A, B, swap):
    stim = json.loads((EQ / "stim" / run / f"{mod}.json").read_text())
    spec = next(p for p in DES.rglob("description.txt") if p.parent.name == mod).read_text()
    tpd = stim["tps"][ep["tp"]]
    rows_in = json.loads(tpd["rows"]) if isinstance(tpd["rows"], str) else tpd["rows"]
    ins = [(j, n) for j, n in enumerate(stim["inputs"]) if n != stim["clock"]]
    outs, W = stim["outputs"], stim["width"]
    x, y = (A[run][ep["tp"]], B[run][ep["tp"]]) if swap else (B[run][ep["tp"]], A[run][ep["tp"]])
    lo = 0 if ep["first"] <= 40 else ep["first"] - CONTEXT
    hi = min(len(x), len(y), len(rows_in), ep["end"] + 4) - 1
    D = [k for k in range(len(outs)) if any(x[i][k] != y[i][k] for i in range(lo, hi + 1))]
    S = [k for k in range(len(outs)) if k not in D]
    head = (["row"] + [n for _, n in ins] + [outs[k] for k in S] + [f"X.{outs[k]}" for k in D]
            + [f"Y.{outs[k]}" for k in D] + [""])
    lines = [" | ".join(head)]
    for i in range(lo, hi + 1):
        cells = ([str(i)] + [hexw(rows_in[i][j], W[n]) for j, n in ins] + [x[i][k] for k in S]
                 + [x[i][k] for k in D] + [y[i][k] for k in D] + ["<<" if x[i] != y[i] else ""])
        lines.append(" | ".join(cells))
    omitted = (f"Rows 0-{lo - 1} of this testpoint are omitted; on them both candidates' outputs "
               f"were identical.\n" if lo else "")
    ports = "\n".join(f"- {d} {n} [{W[n]} bit]" for d, names in (("input", [n for _, n in ins]), ("output", outs))
                      for n in names)
    cfg = configuration(mod) if VARIANT == "2" else ""
    cfg = f"## Configuration\n\nFrom the design's include files:\n{cfg}\n" if cfg else ""
    return f"""## Specification

{spec}

{cfg}## Ports

{ports}

## Simulation conventions

- Each testpoint starts with a reset sequence that is not shown: rst is 1 for two clock cycles,
  then 0 for one cycle. Every register starts from that reset.
- In row i the inputs of row i are applied, the outputs are sampled shortly afterwards (before
  the rising clock edge), and then the rising edge occurs. The outputs in row i therefore show
  the state left by the edges of the earlier rows, plus any combinational path from row i's
  inputs.
- Values are hexadecimal. Outputs the two candidates agree on throughout the excerpt are shown
  once; outputs on which they differ are shown as X.<name> and Y.<name>.
- Before row {ep["first"]} both candidates' outputs were identical.
{omitted}
## Excerpt ({hi - lo + 1} rows)

{chr(10).join(lines)}
"""


def parse(text):
    m = re.search(r"\{.*\}", text or "", re.S)
    try:
        v = json.loads(m.group(0))["verdict"].strip().lower() if m else ""
    except (ValueError, KeyError, AttributeError):
        v = ""
    return {"x": "X", "y": "Y"}.get(v, v or "unparsed")


async def judge(client, sem, model, user, budget):
    key = hashlib.sha256(json.dumps([model, EFFORT, SYSTEM, user]).encode()).hexdigest()[:24]
    f = CALLS / f"{key}.json"
    if f.is_file():
        return json.loads(f.read_text())
    if budget["left"] <= 0:
        return None
    budget["left"] -= 1
    async with sem:
        for attempt in range(6):
            try:
                stream = await client.responses.create(
                    model=model, store=False, max_output_tokens=64000, stream=True,
                    reasoning={"effort": EFFORT, "summary": "auto"},
                    input=[{"role": "developer", "content": SYSTEM}, {"role": "user", "content": user}])
                final = None
                async for ev in stream:
                    if getattr(ev, "type", "") in ("response.completed", "response.incomplete", "response.failed"):
                        final = ev.response
                if final is None:
                    raise RuntimeError("stream ended without a terminal event")
                u = final.usage
                rec = {"text": final.output_text, "status": final.status,
                       "output_tokens": u.output_tokens, "input_tokens": u.input_tokens}
                CALLS.mkdir(parents=True, exist_ok=True)
                f.write_text(json.dumps(rec))
                return rec
            except Exception as exc:  # noqa: BLE001 -- the gateway drops streams; resend
                print(f"  call retry {attempt + 1}: {type(exc).__name__}", flush=True)
                await asyncio.sleep(min(60, 5 * 2 ** attempt))
    return None


# ---------------------------------------------------------------- targets
targets, seen = [], set()
for arm, f in (("cf-checks", "LATCH-OFFLINE.json"), ("cf-model", "LATCH-OFFLINE-cf-model.json")):
    want = {}
    for r in json.loads((E / f).read_text())["rows"]:
        if in_range(r["dpass"], r["dcons"]) and r["golden_net"] != 0:
            want.setdefault(tuple(r["job"].split()), []).append(r)
    for (sh, run), rs in sorted(want.items()):
        mod = LONG[sh]
        log = sorted(glob.glob(str(RUNS / run / "results" / mod / f"{arm}*" / "editor.log")))[0]
        commits = replay(run, mod, log, RUNS / run / f"editor-{arm}" / mod / "debug_trajectory.jsonl")
        for r in rs:
            c = commits[r["commit"] - 1]
            targets.append({"source": f"{arm} {sh} {run} commit {r['commit']}", "run": run, "mod": mod,
                            "before": c["before"], "after": c["submitted"], "dpass": r["dpass"],
                            "dcons": r["dcons"], "golden_net": r["golden_net"],
                            "golden_net_own": r["golden_net_own"]})
for run, mod, tag in LIVE:
    log = RUNS / run / "results" / mod / tag / "editor.log"
    if not log.is_file():
        continue
    commits = replay(run, mod, log, RUNS / run / f"editor-{tag}" / mod / "debug_trajectory.jsonl")
    for i, c in enumerate(commits, 1):
        j = c["requirements"] or {}
        if not j.get("passing"):
            continue
        a0, a1 = (int(v) for v in j["passing"].split(" -> "))
        targets.append({"source": f"live {tag} {SH[mod]} {run} commit {i}", "run": run, "mod": mod,
                        "before": c["before"], "after": c["submitted"], "dpass": a1 - a0, "dcons": None})

rows = []
for t in targets:
    mod, run = t["mod"], t["run"]
    contract = json.loads((EQ / "corpora" / run / mod / "contract.json").read_text())
    sim = FA["simulator"](mod)
    A, B = sim(t["before"], contract), sim(t["after"], contract)
    if A is None or B is None:
        continue
    G = json.loads((EQ / "out" / mod / "golden.json").read_text())
    if t["dcons"] is None:  # live: agreement and golden computed here, as the audit does
        pool = [json.loads((EQ / "out" / mod / f"{run}.{k}.json").read_text())
                for k in POOL.get(mod, ("gen1", "gen2", "gen3"))]
        t["dcons"] = st.mean(agree(B, p, run) - agree(A, p, run) for p in pool)
        c, o = FA["compare"](A, B, G), FA["compare"](A, B, {run: G[run]})
        t["golden_net"], t["golden_net_own"] = c["cells_fixed"] - c["cells_broken"], o["cells_fixed"] - o["cells_broken"]
        if not in_range(t["dpass"], t["dcons"]) or t["golden_net"] == 0:
            continue
    fp = hashlib.sha256(json.dumps(B[run], sort_keys=True).encode()).hexdigest()
    if (mod, run, fp) in seen:
        continue
    seen.add((mod, run, fp))
    eps = episodes(A, B, run, G)
    chosen = pick(eps, t["source"])
    rows.append({**{k: v for k, v in t.items() if k not in ("before", "after")},
                 "episodes_total": len(eps), "cells_total": sum(e["cells"] for e in eps), "asked": chosen,
                 "_A": A, "_B": B})
    del G

print(f"{len(rows)} target commits (golden: {sum(r['golden_net'] > 0 for r in rows)} better, "
      f"{sum(r['golden_net'] < 0 for r in rows)} worse), {sum(len(r['asked']) for r in rows)} episodes, "
      f"{2 * sum(len(r['asked']) for r in rows)} judge calls\n")
for r in rows:
    print(f"- {r['source']}: passing +{r['dpass']}, agreement {100 * r['dcons']:+.2f} pt, golden net "
          f"{r['golden_net']:+d} (own {r['golden_net_own']:+d}); {r['episodes_total']} episodes, "
          f"asking {[(e['tp'], e['cells'], e['after_ok'] - e['before_ok']) for e in r['asked']]}")
if os.environ.get("ARB_DRY"):
    for r in rows[:int(os.environ.get("ARB_DUMP", "0"))]:  # the rendered prompts, for checking
        d = EQ / "arbitration" / "prompts"
        d.mkdir(parents=True, exist_ok=True)
        e = r["asked"][0]
        (d / f"{r['source'].replace(' ', '_')}.{e['tp']}.txt").write_text(
            SYSTEM + "\n\n" + prompt(r["mod"], r["run"], e, r["_A"], r["_B"], False))
    sys.exit(0)


# ---------------------------------------------------------------- judge
async def main():
    import openai
    p = urllib.parse.urlparse(os.environ["OPENAI_BASE_URL"])
    client = openai.AsyncOpenAI(api_key=os.environ["OPENAI_API_KEY"], base_url=f"{p.scheme}://{p.netloc}/v1",
                                timeout=1800)
    sem, budget = asyncio.Semaphore(int(os.environ.get("ARB_PARALLEL", "6"))), {"left": int(os.environ.get("ARB_LIMIT", "100000"))}
    jobs = [(r, e, swap) for r in rows for e in r["asked"] for swap in (False, True)]
    recs = await asyncio.gather(*(judge(client, sem, os.environ["OPENAI_MODEL"],
                                        prompt(r["mod"], r["run"], e, r["_A"], r["_B"], swap), budget)
                                  for r, e, swap in jobs))
    for (r, e, swap), rec in zip(jobs, recs):
        if rec is None:
            continue
        v = parse(rec["text"])
        # swap False: X is the edit (after); swap True: X is the design before the commit
        pick_ = {"X": "before" if swap else "after", "Y": "after" if swap else "before"}.get(v, v)
        e.setdefault("answers", []).append(pick_)
        e.setdefault("tokens", []).append(rec["output_tokens"])

asyncio.run(main())


def vote(e):
    a = e.get("answers") or []
    return sum((x == "after") - (x == "before") for x in a) / len(a) if a else None


out = {"variant": VARIANT, "k": K, "horizon": HORIZON, "effort": EFFORT, "commits": []}
for r in rows:
    vs = [(vote(e), e["cells"]) for e in r["asked"] if vote(e) is not None]
    score = sum(v * c for v, c in vs) / sum(c for _, c in vs) if vs else None
    r["arbiter"] = None if score is None else score > 0
    r["score"] = score
    # a perfect judge on the same episodes: how much of the error is the sample's
    r["oracle"] = sum(((e["after_ok"] > e["before_ok"]) - (e["after_ok"] < e["before_ok"])) * e["cells"]
                      for e in r["asked"]) > 0
    out["commits"].append({k: v for k, v in r.items() if not k.startswith("_")})

done = [r for r in rows if r["score"] is not None]
eps = [e for r in done for e in r["asked"] if e.get("answers")]
calls = [(a, e) for e in eps for a in e["answers"]]
print(f"\n## Episodes ({len(eps)} asked, {len(calls)} calls, "
      f"{sum(sum(e.get('tokens', [])) for e in eps)} output tokens)\n")
dec = [(a, e) for a, e in calls if a in ("after", "before")]
right = sum((a == "after") == (e["after_ok"] > e["before_ok"]) for a, e in dec if e["after_ok"] != e["before_ok"])
print(f"- answers: {dict((k, sum(a == k for a, _ in calls)) for k in sorted({a for a, _ in calls}))}")
print(f"- decisive answers right per golden: {right} of {sum(e['after_ok'] != e['before_ok'] for _, e in dec)}")
cons = sum(len(set(e["answers"])) == 1 for e in eps if len(e["answers"]) == 2)
print(f"- both label orders gave the same answer: {cons} of {sum(len(e['answers']) == 2 for e in eps)}")
print("\nBy module (decisive answers right / decisive answers on episodes golden decides; undetermined or both wrong):\n")
for mod in sorted({r["mod"] for r in done}):
    md = [(a, e) for r in done if r["mod"] == mod for e in r["asked"] for a in e.get("answers", [])]
    dd = [(a, e) for a, e in md if a in ("after", "before") and e["after_ok"] != e["before_ok"]]
    ok = sum((a == "after") == (e["after_ok"] > e["before_ok"]) for a, e in dd)
    out.setdefault("by_module", {})[mod] = [ok, len(dd), sum(a not in ("after", "before") for a, _ in md)]
    print(f"- {SH[mod]}: {ok} / {len(dd)}; {sum(a not in ('after', 'before') for a, _ in md)}")

print("\n## Commits\n")
print("| commit | agreement, pt | golden net (own) | arbiter score | arbiter | tolerance 0.5 | tolerance 1 | perfect judge |")
print("|---|---|---|---|---|---|---|---|")
RULES = {"arbiter": lambda r: r["arbiter"], "tolerance 0.5": lambda r: r["dcons"] > -0.005,
         "tolerance 1": lambda r: r["dcons"] > -0.01, "perfect judge, same episodes": lambda r: r["oracle"]}
for r in done:
    g = "better" if r["golden_net"] > 0 else "worse"
    print(f"| {r['source']} | {100 * r['dcons']:+.2f} | {g} {r['golden_net']:+d} ({r['golden_net_own']:+d}) | "
          f"{r['score']:+.2f} | " + " | ".join("keep" if f(r) else "refuse" for f in RULES.values()) + " |")
print("\n| rule | kept better / worse | refused better / worse |\n|---|---|---|")
for name, f in RULES.items():
    kb = sum(bool(f(r)) and r["golden_net"] > 0 for r in done)
    kw = sum(bool(f(r)) and r["golden_net"] < 0 for r in done)
    rb = sum(not f(r) and r["golden_net"] > 0 for r in done)
    rw = sum(not f(r) and r["golden_net"] < 0 for r in done)
    out[name] = [kb, kw, rb, rw]
    print(f"| {name} | {kb} / {kw} | {rb} / {rw} |")
if not os.environ.get("ARB_LIMIT"):
    (E / f"ARBITRATION-OFFLINE{'' if VARIANT == '1' else '-v' + VARIANT}.json").write_text(json.dumps(out, indent=1, default=str) + "\n")
