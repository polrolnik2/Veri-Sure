"""arbitration_why.py -- why arbitration variant 2 decides dc_fsm and sb but abstains on the I2C modules.

Per module, over the excerpts ARBITRATION-OFFLINE asked about:
  - testpoint length, the row of the first divergence, and how many excerpts start mid-testpoint
    (history cut), with the judge's abstentions;
  - keyword counts over the one-sentence reasons the judge gave for abstaining (counts only; the
    replies stay in EQ/arbitration);
  - the kind of each difference: a time shift of 1-3 rows, or a value;
  - how each excerpt's answer moved from variant 1 to variant 2 (right / wrong / split / abstain,
    per golden).
Needs the judge-call cache that arbitration_offline.py writes.
"""

import contextlib
import hashlib
import io
import json
import os
import re
import statistics as st
from collections import Counter, defaultdict
from pathlib import Path

P = str(Path(__file__).resolve().parent / "arbitration_offline.py")
SRC = Path(P).read_text().split('if os.environ.get("ARB_DRY"):')[0]
DECISIVE = ("after", "before")
KW = {"history / omitted rows": r"omit|not shown|history|earlier rows|prior rows|before row|cut|truncat|start of",
      "prescaler / divider / counter": r"prescal|divid|clk_cnt|counter|count",
      "filter / synchroniser": r"filter|synchron|sampl|glitch",
      "arbitration / bus state": r"arbitrat|busy|al\b|lost",
      "spec does not determine": r"not specif|doesn.t specif|does not specif|ambigu|unspecif|not defin|not determin"
                                 r"|underspec|no .*rule|silent",
      "cycle timing / latency": r"cycle|latenc|timing|exact"}


def load(variant):
    os.environ["ARB_VARIANT"] = variant
    g = {"__file__": P, "__name__": "arb"}
    with contextlib.redirect_stdout(io.StringIO()):
        exec(compile(SRC, P, "exec"), g)  # targets, episodes and prompts; no calls
    return g


def reason_of(text):
    m = re.search(r'\{[^{}]*"verdict"[^{}]*\}', text or "", re.S)
    try:
        return (json.loads(m.group(0)).get("reason") or "").lower() if m else ""
    except ValueError:
        return ""


def rows_of(tpd):
    return json.loads(tpd["rows"]) if isinstance(tpd["rows"], str) else tpd["rows"]


for variant in ("1", "2"):
    g = load(variant)
    stats = defaultdict(list)
    for r in g["rows"]:
        stim = json.loads((g["EQ"] / "stim" / r["run"] / f"{r['mod']}.json").read_text())
        for e in r["asked"]:
            for swap in (False, True):
                user = g["prompt"](r["mod"], r["run"], e, r["_A"], r["_B"], swap)
                key = hashlib.sha256(json.dumps([os.environ["OPENAI_MODEL"], g["EFFORT"], g["SYSTEM"], user])
                                     .encode()).hexdigest()[:24]
                f = g["CALLS"] / f"{key}.json"
                rec = json.loads(f.read_text()) if f.is_file() else {}
                stats[r["mod"]].append({"first": e["first"], "tp_rows": len(rows_of(stim["tps"][e["tp"]])),
                                        "cut": e["first"] > 40, "verdict": g["parse"](rec.get("text")),
                                        "reason": reason_of(rec.get("text")), "tokens": rec.get("output_tokens") or 0})
    print(f"\n## Variant {variant}\n")
    for mod, xs in stats.items():
        ab = [x for x in xs if x["verdict"] not in ("X", "Y")]
        print(f"- {mod}: {len(xs)} calls, {len(ab)} abstain; testpoint rows median "
              f"{st.median(x['tp_rows'] for x in xs)}, first divergence median row {st.median(x['first'] for x in xs)}, "
              f"history cut in {sum(x['cut'] for x in xs)}; output tokens median {st.median(x['tokens'] for x in xs)}")
        if ab:
            c = Counter(k for x in ab for k, p in KW.items() if re.search(p, x["reason"]))
            print(f"  abstention reasons mention (of {len(ab)}): {dict(c)}")

g = load("1")
v1 = {r["source"]: r for r in json.load(open(g["E"] / "ARBITRATION-OFFLINE.json"))["commits"]}
v2 = {r["source"]: r for r in json.load(open(g["E"] / "ARBITRATION-OFFLINE-v2.json"))["commits"]}


def shift(a, b, rows, ports):
    """The 1-3 row offset at which every differing cell of b equals a's, if there is one."""
    for d in (1, -1, 2, -2, 3, -3):
        if all(0 <= i + d < len(a) and b[i][k] == a[i + d][k] for i in rows for k in ports if a[i][k] != b[i][k]):
            return d
    return None


def outcome(answers, truth):
    if not answers:
        return "none"
    ok = [x for x in answers if x in DECISIVE]
    if not ok:
        return "abstain"
    return "right" if all(x == truth for x in ok) else "wrong" if all(x != truth for x in ok) else "split"


kind, trans, ports = defaultdict(Counter), defaultdict(Counter), defaultdict(Counter)
for r in g["rows"]:
    outs = json.loads((g["EQ"] / "stim" / r["run"] / f"{r['mod']}.json").read_text())["outputs"]
    for j, e in enumerate(r["asked"]):
        a, b = r["_A"][r["run"]][e["tp"]], r["_B"][r["run"]][e["tp"]]
        rows = range(e["first"], e["end"] + 1)
        dk = sorted({k for i in rows for k in range(len(a[i])) if a[i][k] != b[i][k]})
        ports[r["mod"]].update(outs[k] for k in dk)
        s = shift(a, b, rows, dk)
        kind[r["mod"]][f"time shift {s:+d}" if s else "value"] += 1
        truth = "after" if e["after_ok"] > e["before_ok"] else "before" if e["after_ok"] < e["before_ok"] else "tie"
        trans[r["mod"]][(outcome(v1[r["source"]]["asked"][j].get("answers"), truth),
                         outcome(v2[r["source"]]["asked"][j].get("answers"), truth))] += 1
print("\n## Differences and answer changes, per excerpt\n")
for m in kind:
    print(f"- {m}: {dict(kind[m])}; ports {dict(ports[m].most_common(6))}")
    print(f"  variant 1 -> 2: {', '.join(f'{x} -> {y}: {n}' for (x, y), n in sorted(trans[m].items()))}")
