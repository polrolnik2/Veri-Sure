"""WHICH bodies convict once the pool is deepened, and what shape are they?

    e6_diagnose_depth.py <corpus-dir> <golden-suite-dir> [--limit N]

`FRONTIER.md` leaves the decisive question unanswered. At 122 bodies with both
rules the audit column is **1 of 40** and that one conviction is diagnosed
(REQ-0055, `normalize` naming the wrong observable). At 241 bodies blindness falls
under the target and the audit column is **6 of 44** -- so five convictions arrive
with the depth and NONE of them has been looked at.

That matters because of which way it cuts. If the five are the mechanical shapes
this branch already has instruments for -- an unbounded `TO_END` invariant, a
hand-rolled window, an over-width probe read as a flag, a strong existential over
zero rows -- then a grade-blind ADMISSION criterion stricter than `well_formed`
excludes them, and blindness under 10% with an audit column near the accepted
set's is reachable from stored artifacts. If they are five unrelated
interpretations of five different sentences, it is not, and the frontier stands.

Either way the answer is a fact about the bodies and costs no model call.

**THIS DIAGNOSES; IT DOES NOT SELECT.** Naming a shape here is not licence to drop
the bodies that have it -- a rule whose population is only the convicting bodies is
gating on the grade, which `LAST-CONVICTION.md` is the worked example of refusing.
What a shape earns is a CENSUS over the whole pool, reported beside it, so a rule
built on it can be judged on coverage rather than on the numbers it would produce.

Golden is RUN and never read.
"""
import ast
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, "/home/user/Veri-Sure")
from specflow.refmodel.oracle_gen import RequirementOracle  # noqa: E402
from specflow.refmodel.oracles import well_formed  # noqa: E402
from specflow.refmodel.rtl_trace import decide_rtl, load_traces  # noqa: E402
from specflow.refmodel.temporal import (hand_rolled_window,  # noqa: E402
                                        licenses_a_cycle_count,
                                        strong_not_stated, unbounded_invariant)

SRC, GOLD = Path(sys.argv[1]), Path(sys.argv[2])
LIMIT = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else 1
#: The same two admission/rule switches `e6_admit_corpus.py` carries, so the
#: decomposition can be checked against the configuration it is a decomposition
#: OF rather than against a different one.
NO_HAND_ROLLED = "--no-hand-rolled" in sys.argv
EXIST_ONLY = "--licence-existential-only" in sys.argv
EXISTENTIAL = frozenset({"eventually", "pulse", "nexttime", "sequence", "until",
                         "nth"})
blob = json.loads((SRC / "oracles.json").read_text())
oracles, corpus = blob["oracles"], (blob.get("corpus") or {})
requirements = json.loads((SRC / "requirements.json").read_text())["requirements"]
text_of = {r["uid"]: str(r.get("text") or "") for r in requirements}
kind_of = {r["uid"]: str(r.get("unit_kind") or "?") for r in requirements}
_s = json.loads((SRC / "stimulus.json").read_text())
stim = _s["testpoints"] if isinstance(_s, dict) else _s
by_tp = {s["tp_uid"]: s.get("stimulus_steps") or [] for s in stim}
contract = json.loads((GOLD / "contract.json").read_text())
plan = json.loads((SRC / "testplan.json").read_text())["elements"]
traces = load_traces(GOLD / "suite" / "results")
accepted = {x["req_uid"]: x for x in oracles}
SEQ = re.compile(r"\b(after|then|subsequently|following|in response to|once|"
                 r"thereafter|next)\b", re.I)
#: The probes golden reports wider than the contract declares -- measured, all
#: 482 traces. A check reading one of these as a flag is comparing quantities.
WIDE = ("cscl", "csda", "fscl", "fsda", "filter_cnt", "idle")


def _existential_sites(src):
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return []
    out = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        f = node.func
        name = (f.id if isinstance(f, ast.Name)
                else f.attr if isinstance(f, ast.Attribute) else None)
        if name not in EXISTENTIAL:
            continue
        for kw in node.keywords:
            if (kw.arg == "after_activation"
                    and isinstance(kw.value, ast.Constant)
                    and kw.value.value is True):
                out.append((kw.value.lineno, kw.value.col_offset))
    return out


def demote(x):
    t = text_of.get(x["req_uid"], "")
    if SEQ.search(t) or licenses_a_cycle_count(t):
        return x
    src = x["source"]
    if EXIST_ONLY:
        lines = src.splitlines(keepends=True)
        for ln, col in sorted(_existential_sites(src), reverse=True):
            i = ln - 1
            if 0 <= i < len(lines) and lines[i][col:col + 4] == "True":
                lines[i] = lines[i][:col] + "False" + lines[i][col + 4:]
        out = "".join(lines)
    else:
        out = re.sub(r"after_activation\s*=\s*True", "after_activation=False",
                     src)
    out = re.sub(r"^(\s*follows\s*=\s*)True", r"\1False", out, flags=re.M)
    return {**x, "source": out} if out != src else x


def advance(tr, probes):
    out = {}
    for tp, t in tr.items():
        edges = [dict(e) for e in (t.get("edges") or [])]
        duts = [dict(e.get("dut") or {}) for e in edges]
        for i, e in enumerate(edges):
            d = dict(duts[i])
            nxt = duts[i + 1] if i + 1 < len(duts) else {}
            for n in probes:
                if n in d:
                    d[n] = nxt.get(n)
            e["dut"] = d
        out[tp] = {**t, "edges": edges}
    return out


def shapes(src: str) -> list[str]:
    """The mechanical shapes this branch has an instrument for."""
    out = []
    if unbounded_invariant(src):
        out.append("TO_END-invariant")
    if hand_rolled_window(src):
        out.append("hand-rolled-window")
    if strong_not_stated(src):
        out.append("strong-not-stated")
    named = sorted(w for w in WIDE if f"'{w}'" in src or f'"{w}"' in src)
    if named:
        out.append("reads-over-width(" + ",".join(named) + ")")
    if not re.search(r"\b(eventually|throughout|stable|pulse|never|nexttime|"
                     r"sequence|until|nth)\s*\(", src):
        out.append("NO-temporal-operator")
    return out


def pool(limit):
    """`[(key, body, origin)]`; origin is "accepted" or "corpus"."""
    out = [(f"{x['req_uid']}", x, "accepted") for x in oracles]
    for uid, members in sorted(corpus.items()):
        a = accepted.get(uid)
        if a is None:
            continue
        n = 0
        for m in members:
            src = m.get("source") or ""
            if not src or src == a["source"]:
                continue
            o = RequirementOracle(req_uid=uid, tp_uids=list(a["tp_uids"]),
                                  clause=a.get("clause", ""), source=src)
            if well_formed(o, contract, plan) is not None:
                continue
            if NO_HAND_ROLLED and hand_rolled_window(src):
                continue
            n += 1
            out.append((f"{uid}#{n}", {**a, "source": src}, "corpus"))
            if limit is not None and n >= limit:
                break
    return out


entries = [(k, demote(b), o) for k, b, o in pool(LIMIT)]
adv = advance(traces, ("sta_condition", "sto_condition"))
print(f"pool: {len(entries)} bodies (+{LIMIT} corpus body per requirement), "
      f"licence{' (existentials only)' if EXIST_ONLY else ''} + phase rules"
      + (", hand-rolled REFUSED" if NO_HAND_ROLLED else "") + "\n", flush=True)

#: **PER BODY, NOT PER REQUIREMENT.** `decide_rtl` folds by `req_uid`, so a
#: requirement with several bodies reports one verdict and the body that produced
#: it is lost -- which is exactly the question here. Each body is decided alone.
convicting = []
for key, body, origin in entries:
    o = RequirementOracle(req_uid=key, tp_uids=list(body["tp_uids"]),
                          clause=body.get("clause", ""), source=body["source"])
    for r in decide_rtl([o], adv, contract, transactional=True):
        if r.broken or r.ok is not False:
            continue
        uid = key.split("#")[0]
        convicting.append((uid, key, origin, r.tp_uid, r.edge,
                           str(r.detail or "")[:130], shapes(body["source"])))

print(f"BODIES THAT CONVICT GOLDEN: {len(convicting)} of {len(entries)}\n")
for uid, key, origin, tp, edge, detail, sh in sorted(convicting):
    print(f"  {key:14} [{kind_of.get(uid, '?'):11}] {origin:8} {tp} edge={edge}")
    print(f"       shapes: {', '.join(sh) or '(none this branch has an instrument for)'}")
    print(f"       {detail}")
    print(f"       req: {' '.join(text_of.get(uid, '').split())[:110]}")

print("\n=== CENSUS OF EACH SHAPE OVER THE WHOLE POOL, convicting or not ===")
print("  (a shape whose population is only the convicting bodies cannot be used;")
print("   see LAST-CONVICTION.md)\n")
allshapes: dict = {}
for key, body, origin in entries:
    for s in shapes(body["source"]):
        allshapes.setdefault(s.split("(")[0], set()).add(key)
conv_keys = {k for _u, k, _o, _t, _e, _d, _s in convicting}
for s in sorted(allshapes):
    keys = allshapes[s]
    print(f"  {s:22} {len(keys):4} of {len(entries)} bodies, "
          f"{len(keys & conv_keys)} of which convict")
