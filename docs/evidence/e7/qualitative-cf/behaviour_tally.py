"""Behavioural profile of each editor arm from its logs. Prints counts only, never log text."""

import glob
import re
from collections import Counter, defaultdict

TOOLS = [
    "list_failing_requirements",
    "explain",
    "focus",
    "list_suspect_blocks",
    "read_block",
    "find_signal",
    "replace_block",
    "edit",
    "add_block",
    "remove_block",
    "check_staged",
    "discard_staged",
    "commit",
    "add_stimulus",
    "run_simulation",
]
EDITS = {"replace_block", "edit", "add_block", "remove_block"}
READS = {
    "list_failing_requirements",
    "explain",
    "focus",
    "list_suspect_blocks",
    "read_block",
    "find_signal",
}
TERMS = {
    "spec": re.compile(r"\b(spec|specification|description|datasheet)\b", re.I),
    "requirement": re.compile(r"\b(requirement|REQ-\d+)\b", re.I),
    "check": re.compile(
        r"(\b(the|this|its|that|each|a|failing|shipped) check\b|\bchecks\b|\bcheck's\b|\boracle|decide\()",
        re.I,
    ),
    "spec or requirement text": re.compile(
        r"\b(spec|specification|description|requirement|REQ-\d+)\b", re.I
    ),
    "ref model": re.compile(
        r"\b(reference model|ref model|the model|model's|model expects|model says)\b",
        re.I,
    ),
    "contract": re.compile(r"\bcontract\b", re.I),
    "golden-like": re.compile(
        r"\b(opencores|original design|canonical|typical implementation|standard i2c)\b",
        re.I,
    ),
}
OUTCOMES = {
    "latched (rise)": re.compile(r"LATCHED: passing requirements[^\"\n]{0,200}"),
    "latched on gradient": re.compile(r"LATCHED ON THE GRADIENT[^\"\n]{0,200}"),
    "not latched": re.compile(r"Commit did NOT latch[^\"\n]{0,200}"),
    "rejected (compile/driver)": re.compile(
        r"(Commit rejected[^\"\n]{0,200}|Edit rolled back[^\"\n]{0,200})"
    ),
}


def profile(paths):
    tools, outcome, terms = Counter(), Counter(), Counter()
    segs = 0
    for p in paths:
        text = open(p, errors="replace").read()
        for t in TOOLS:
            tools[t] += len(re.findall(r'"name": "_tool_%s"' % t, text))
        for k, rx in OUTCOMES.items():
            outcome[k] += len(
                set(m.group(0) for m in rx.finditer(text))
            )  # dedup restated outcomes
        lines = text.splitlines()
        i = 0
        while i < len(lines):
            if "Debugger(thinking):" in lines[i]:
                buf = [lines[i].split("Debugger(thinking):", 1)[1]]
                j = i + 1
                while (
                    j < len(lines)
                    and not lines[j].startswith("{")
                    and "(thinking):" not in lines[j]
                ):
                    buf.append(lines[j])
                    j += 1
                seg = "\n".join(buf)
                segs += 1
                for k, rx in TERMS.items():
                    terms[k] += bool(rx.search(seg))
                i = j
            else:
                i += 1
    return tools, outcome, terms, segs


arms = defaultdict(list)
for p in sorted(glob.glob("/home/user/runs-cf/luna1*/results/*/cf-*/editor.log")):
    run, mod, tag = p.split("/")[4], p.split("/")[6], p.split("/")[7]
    arm = (
        "checks"
        if tag.startswith("cf-checks")
        else "model"
        if tag.startswith("cf-model")
        else None
    )
    if arm and not (run == "luna12" and mod == "or1200_dc_fsm"):
        arms[(arm, run, mod)].append(p)

agg = {
    "checks": [Counter(), Counter(), Counter(), 0],
    "model": [Counter(), Counter(), Counter(), 0],
}
rows = []
for (arm, run, mod), paths in sorted(arms.items()):
    t, o, te, s = profile(paths)
    a = agg[arm]
    a[0].update(t)
    a[1].update(o)
    a[2].update(te)
    a[3] += s
    commits = max(1, t["commit"])
    rows.append(
        (
            arm,
            run,
            mod.replace("i2c_master_", "").replace("or1200_", ""),
            t["commit"],
            round(sum(t[x] for x in READS) / commits, 1),
            round(sum(t[x] for x in EDITS) / commits, 1),
            o["latched (rise)"],
            o["latched on gradient"],
            o["not latched"],
            s,
            {k: round(v / max(1, s), 2) for k, v in te.items()},
        )
    )
print(
    "arm    run    module     commits reads/commit edits/commit | rise grad notlatched | thinking segs | share of segments mentioning ..."
)
for r in rows:
    print(
        f"{r[0]:6} {r[1]} {r[2]:10} {r[3]:6} {r[4]:11} {r[5]:11} | {r[6]:4} {r[7]:4} {r[8]:10} | {r[9]:4} | {r[10]}"
    )
print()
for arm, (t, o, te, s) in agg.items():
    tot = sum(t.values())
    c = max(1, t["commit"])
    print(
        f"== {arm}: tool mix "
        + ", ".join(f"{k} {100 * t[k] / tot:.0f}%" for k in TOOLS if t[k])
    )
    print(
        f"   commits {t['commit']}, reads/commit {sum(t[x] for x in READS) / c:.1f}, edits/commit {sum(t[x] for x in EDITS) / c:.1f}, "
        f"outcomes {dict(o)}, thinking segments {s}, mention shares "
        + str({k: round(v / max(1, s), 2) for k, v in te.items()})
    )
