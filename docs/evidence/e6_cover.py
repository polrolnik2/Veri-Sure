"""The MINIMUM set of bodies that leaves blindness exactly where the pool does.

    e6_cover.py <corpus-dir> <golden-suite-dir> [--limit N]

**EVERY SELECTION RULE MEASURED ON THIS BRANCH TRADES A COLUMN FOR ANOTHER, AND
THIS ONE CANNOT, BY CONSTRUCTION.**

`FRONTIER.md` reduces the whole frontier to one sentence: the checks that convict
golden are also the checks that separate the population. `max_convictions` drops
objectors and takes separators with them; `min_placement` drops the checks that
object where designs AGREE -- but such a check can still separate a few cells, so
blindness went 0.0526 -> 0.1203 when it ran.

The question none of those rules asks: **does this body separate any cell that no
other kept body separates?** If not, dropping it changes the separated SET not at
all, so blindness is identical -- and one fewer body is one fewer chance to convict
a correct design, because rejections union.

    keep bodies greedily, always taking the one separating the most cells not yet
    separated, until no remaining body separates anything new. Then give every
    requirement that lost all its bodies its best single contributor back, so span
    is preserved.

**BLINDNESS IS PRESERVED EXACTLY**, because the union of separated cells is
unchanged by construction; greedy set cover changes how MANY sets are used, never
which cells the union holds. Span is preserved by the per-requirement floor. The
only column free to move is audit, and it can only move down or stay: the kept set
is a SUBSET, and a subset of objectors cannot convict more.

Population-only: cells come from the spec-derived designs and the verdict tables
come from replaying the checks against them. No audit column is read.

Golden is RUN and never read.
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, "/home/user/Veri-Sure")
from specflow import variety as V  # noqa: E402
from specflow.oracles_stage import (_population_rows,  # noqa: E402
                                    _population_tables, admitted_pool)
from specflow.probes import declared_probes  # noqa: E402
from specflow.refmodel.compose import choose_base  # noqa: E402
from specflow.refmodel.oracle_gen import RequirementOracle  # noqa: E402
from specflow.refmodel.rtl_trace import decide_rtl, load_traces  # noqa: E402
from specflow.refmodel.temporal import licenses_a_cycle_count  # noqa: E402
from specflow.scorecard import score  # noqa: E402

SRC, GOLD = Path(sys.argv[1]), Path(sys.argv[2])
LIMIT = (int(sys.argv[sys.argv.index("--limit") + 1])
         if "--limit" in sys.argv else None)
blob = json.loads((SRC / "oracles.json").read_text())
oracles, corpus = blob["oracles"], (blob.get("corpus") or {})
_n = json.loads((SRC / "normalized.json").read_text())
normalized = _n["normalized"] if isinstance(_n, dict) else _n
requirements = json.loads((SRC / "requirements.json").read_text())["requirements"]
text_of = {r["uid"]: str(r.get("text") or "") for r in requirements}
_s = json.loads((SRC / "stimulus.json").read_text())
stim = _s["testpoints"] if isinstance(_s, dict) else _s
by_tp = {s["tp_uid"]: s.get("stimulus_steps") or [] for s in stim}
contract = json.loads((GOLD / "contract.json").read_text())
plan = json.loads((SRC / "testplan.json").read_text())["elements"]
population = [p.read_text() for p in sorted((SRC / "population").glob("*.py"))]
traces = load_traces(GOLD / "suite" / "results")
seen_probe = {n for t in traces.values() for e in (t.get("edges") or [])
              for n, v in (e.get("dut") or {}).items() if v is not None}
absent = tuple(n for n in declared_probes(contract) if n not in seen_probe)
base = choose_base(contract)
outputs = [str(q.get("name")) for q in (contract.get("io") or [])
           if q.get("dir") == "output" and q.get("name")]
SEQ = re.compile(r"\b(after|then|subsequently|following|in response to|once|"
                 r"thereafter|next)\b", re.I)
EQ = ("sta_condition", "sto_condition")


def demote(x):
    """`TRIPLE.md`'s licence rule, existentials only -- see e6_admit_corpus."""
    import ast
    t = text_of.get(x["req_uid"], "")
    if SEQ.search(t) or licenses_a_cycle_count(t):
        return x
    src = x["source"]
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return x
    EX = {"eventually", "pulse", "nexttime", "sequence", "until", "nth"}
    hits = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        f = node.func
        nm = (f.id if isinstance(f, ast.Name)
              else f.attr if isinstance(f, ast.Attribute) else None)
        if nm not in EX:
            continue
        for kw in node.keywords:
            if (kw.arg == "after_activation"
                    and isinstance(kw.value, ast.Constant)
                    and kw.value.value is True):
                hits.append((kw.value.lineno, kw.value.col_offset))
    lines = src.splitlines(keepends=True)
    for ln, col in sorted(hits, reverse=True):
        i = ln - 1
        if 0 <= i < len(lines) and lines[i][col:col + 4] == "True":
            lines[i] = lines[i][:col] + "False" + lines[i][col + 4:]
    out = "".join(lines)
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


#: The pool the PIPELINE can now ship -- `oracles_stage.admitted_pool`, not a
#: reconstruction here.
class _Set:
    def __init__(self, trusted, corpus_map):
        self.trusted, self.corpus = trusted, corpus_map


class _Body:
    def __init__(self, uid, source, arm="", round_=0):
        self.req_uid, self.source, self.arm, self.round_ = uid, source, arm, round_
        self.answered, self.frozen = "", False


trusted = [RequirementOracle(req_uid=x["req_uid"], tp_uids=list(x["tp_uids"]),
                             clause=x.get("clause", ""), source=x["source"])
           for x in oracles]
cmap = {uid: [_Body(uid, m.get("source") or "", m.get("arm", ""),
                    int(m.get("round") or 0))
              for m in (members if LIMIT is None else members[:LIMIT + 2])]
        for uid, members in corpus.items()}
pool_oracles = admitted_pool(_Set(trusted, cmap), contract, plan)
if LIMIT is not None:
    capped, n = [], {}
    for o in pool_oracles:
        k = n.get(o.req_uid, 0)
        if k > LIMIT:
            continue
        n[o.req_uid] = k + 1
        capped.append(o)
    pool_oracles = capped
bodies = [{"req_uid": o.req_uid, "tp_uids": list(o.tp_uids),
           "clause": o.clause, "source": o.source} for o in pool_oracles]
bodies = [demote(b) for b in bodies]
print(f"pool {len(bodies)} bodies from admitted_pool "
      f"(accepted {len(oracles)})\n", flush=True)

held, req_of, n = {}, {}, {}
for b in bodies:
    uid = str(b["req_uid"])
    i = n.get(uid, 0)
    n[uid] = i + 1
    key = uid if i == 0 else f"{uid}#{i}"
    held[key] = RequirementOracle(req_uid=uid, tp_uids=list(b["tp_uids"]),
                                  clause=b["clause"], source=b["source"])
    req_of[key] = b

rows_by_design = _population_rows(population, contract, by_tp, base=base,
                                  transactional=True)
cells = V.cells(rows_by_design, outputs)
_v, by_tp_table, _obj = _population_tables(
    held, population, contract, by_tp, base=base, transactional=True)
print(f"cells {len(cells)}; verdict tables for {len(by_tp_table)} body(ies)",
      flush=True)

#: **WHICH CELLS EACH BODY SEPARATES, ONCE.** `blind_at` is the shipped predicate;
#: asking it per body with only that body's table gives exactly that body's
#: contribution, and the complement of its blind set is what it separates.
all_cells = set(cells)
sep_of = {}
for key, table in by_tp_table.items():
    blind = set(V.blind_at(cells, {key: table}))
    sep_of[key] = all_cells - blind
covered_by_pool = set().union(*sep_of.values()) if sep_of else set()
print(f"the whole pool separates {len(covered_by_pool)} of {len(cells)} cells\n",
      flush=True)

#: Greedy set cover: always the body adding the most uncovered cells, until none
#: adds any. The UNION is unchanged when it stops, so blindness is identical.
remaining = set(covered_by_pool)
kept: list[str] = []
while remaining:
    best, gain = None, 0
    for key, sep in sep_of.items():
        if key in kept:
            continue
        g = len(sep & remaining)
        if g > gain:
            best, gain = key, g
    if best is None:
        break
    kept.append(best)
    remaining -= sep_of[best]
print(f"greedy cover: {len(kept)} body(ies) reach the pool's entire separated set")

#: **SPAN FLOOR.** A requirement whose bodies all became redundant still needs one,
#: or the set covers less of the specification than the pool did.
#:
#: "Best" is TWO population-only keys, and the second is not decoration: the first
#: leaves ties -- among 91 floored requirements many bodies separate the same
#: number of cells, and `max` then takes whichever came first, which is source
#: order. Breaking the tie on FEWEST POPULATION CONVICTIONS prefers the less
#: over-strict body where separation is already equal, so it cannot cost a cell.
#:
#: This is `max_convictions` used as a tie-break INSIDE a requirement, never as a
#: global filter -- which is what made it destroy separators in `SELECT.md`
#: (`effective_size` 273 -> 141). Here separation is fixed by the first key before
#: this one is consulted, so it can only choose among bodies that separate
#: equally. And it reads the spec-derived designs, not the control.
have = {req_of[k]["req_uid"] for k in kept}
convicts_of = {k: sum(1 for x in (_v.get(k) or {}).values() if x is False)
               for k in held}
#: **AND THE FLOOR RESTORES ONLY A BODY THAT SEPARATES SOMETHING.**
#: `--floor-must-separate` makes that explicit. A body separating no disagreement
#: cell adds no discriminating power to the set -- the plan's own rule for reading
#: any addition, "admitting or authoring more checks is worth nothing if they
#: cluster with the ones already there" -- and the Ruleset's `min_decides` already
#: encodes that a check deciding nowhere is not evidence.
#:
#: IT COSTS SPAN BY DEFINITION, because span counts requirements that HAVE a check
#: and not requirements whose check discriminates. The cost is reported, and the
#: census below is what says whether the rule is a rule or a single case wearing
#: one: a criterion matching exactly the requirement that convicts is
#: indistinguishable from gating on the grade, which LAST-CONVICTION.md refused.
FLOOR_MUST_SEPARATE = "--floor-must-separate" in sys.argv
added, declined = 0, []
for key in held:
    uid = req_of[key]["req_uid"]
    if uid in have:
        continue
    best = min((k for k in held if req_of[k]["req_uid"] == uid),
               key=lambda k: (-len(sep_of.get(k, ())), convicts_of.get(k, 0), k))
    if FLOOR_MUST_SEPARATE and not sep_of.get(best):
        declined.append(uid)
        have.add(uid)
        continue
    kept.append(best)
    have.add(uid)
    added += 1
if FLOOR_MUST_SEPARATE:
    print(f"floor DECLINED {len(declined)} requirement(s) whose best body "
          f"separates no cell at all:")
    print(f"  {' '.join(sorted(declined)[:24])}"
          + (" ..." if len(declined) > 24 else ""))
print(f"span floor: {added} requirement(s) had no body in the cover, "
      f"best contributor restored\n")

chosen = [req_of[k] for k in kept]
adv = advance(traces, EQ)
v: dict = {}
for r in decide_rtl([held[k] for k in kept], adv, contract, transactional=True,
                    stimulus_by_tp=by_tp):
    if r.broken or r.ok is None:
        continue
    per = v.setdefault(r.req_uid, {})
    per[r.tp_uid] = per.get(r.tp_uid, True) and bool(r.ok)
card = score(oracles=chosen, normalized=normalized, stimulus_by_tp=by_tp,
             contract=contract, population=population,
             requirements=requirements, audit_verdicts=v, audit_absent=absent)
full = score(oracles=bodies, normalized=normalized, stimulus_by_tp=by_tp,
             contract=contract, population=population,
             requirements=requirements)


def line(label, c, audit=True):
    a = (f"AUDIT {c.control_convicted_by}/{c.control_judges} = {c.audit:.4f} "
         f"{'MET' if c.audit == 0 else 'no '}" if audit else "AUDIT (not scored)")
    print(f"  {label:26} bodies {len(chosen) if audit else len(bodies):4}  "
          f"SPAN {c.span:.4f} {'MET' if c.span > 0.90 else 'no '}  "
          f"BLIND {c.blindness:.4f} {'MET' if (c.blindness or 1) < 0.10 else 'no '}"
          f"  {a}  eff {c.effective_size}")


print("target: span > 0.90, blindness < 0.10, audit = 0\n")
line("the whole pool", full, audit=False)
line("the greedy cover", card)
print(f"\n  blindness identical? pool {full.blindness:.4f} vs cover "
      f"{card.blindness:.4f}  -> "
      f"{'YES' if abs((full.blindness or 0) - (card.blindness or 0)) < 1e-9 else 'NO'}")
kind_of = {r["uid"]: str(r.get("unit_kind") or "?") for r in requirements}
left = sorted(u for u, d in v.items() if not all(d.values()))
print(f"\n  remaining convictions: {len(left)}")
for u in left:
    print(f"    {u} [{kind_of.get(u, '?')}]")
