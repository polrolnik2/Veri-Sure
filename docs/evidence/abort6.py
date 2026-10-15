"""All six checks that convict golden: does splitting the abort out of `until`
move any of them?

REQ-0055 was measured by hand in abort55.py. This does the other five the same
way, by a NARROW source rewrite -- move reset and `al` alternatives out of the
`closes = _any([...])` list and pass them as `aborts=` -- and reports which
checks could not be rewritten mechanically rather than guessing at them.

`al` is only an abort where it is NOT the requirement's own observable. REQ-0028
IS about `al`, so its `al` stays put and only its reset close moves.
"""
import ast
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, "/home/user/Veri-Sure")
from specflow.refmodel.oracles import transactional_view  # noqa: E402
from specflow.refmodel.rtl_trace import load_traces, rows_from  # noqa: E402

S = Path("/tmp/claude-0/-home-user-Veri-Sure/12bb865e-7a51-5506-b55a-e5ac7cf72a4a/scratchpad")
A = S / "asrt"
SIX = ["REQ-0007", "REQ-0020", "REQ-0028", "REQ-0055", "REQ-0057", "REQ-0087"]
#: `al` is the declared observable here, so it is the response, not an abort.
AL_IS_THE_SUBJECT = {"REQ-0028"}
ABORT_KEYS = {"nReset": 0, "rst": 1, "al": 1}


def split_closes(src: str, uid: str) -> tuple[str, str]:
    """Rewrite `closes = _any([...])` into a close list and an abort list.

    Returns (new_source, note). A check this cannot rewrite comes back unchanged
    with a note saying why -- an unmeasured case reported as unmeasured.
    """
    m = re.search(r"^(\s*)(closes|_closes)\s*=\s*_any\(\s*(\[.*?\])\s*\)\s*$",
                  src, re.M | re.S)
    if not m:
        return src, "no `_any([...])` close list to split"
    indent, name, literal = m.groups()
    try:
        alts = ast.literal_eval(literal)
    except Exception:  # noqa: BLE001
        return src, "close list is not a literal"
    keep, move = [], []
    for a in alts:
        aborting = any(k in ABORT_KEYS and v == ABORT_KEYS[k] for k, v in a.items())
        if aborting and not (uid in AL_IS_THE_SUBJECT and "al" in a):
            move.append(a)
        else:
            keep.append(a)
    if not move:
        return src, "no abort condition in the close list"
    if not keep:
        return src, "EVERY close is an abort -- the window would never end"
    new = (f"{indent}{name} = _any({keep!r})\n"
           f"{indent}_voids = _any({move!r})")
    src = src[:m.start()] + new + src[m.end():]
    # `[^)]*` cannot cross a nested call -- `after(trace, lambda r: base(r) ...`
    # has a `)` before `until=` -- and a rewrite that quietly patches NOTHING
    # while still printing a verdict is the silent failure this whole repo is
    # built against. Match `until=<name>` directly and count what was patched.
    src, n = re.subn(rf"until={name}\b", f"until={name}, aborts=_voids", src)
    if not n:
        return src, "REWRITE DID NOT APPLY -- no `until=<name>` call site"
    return src, f"moved {move} out of the close list ({n} call site(s))"


def run(src: str, rows: list) -> tuple:
    ns: dict = {}
    exec(compile(src, "<oracle>", "exec"), ns)          # noqa: S102
    return ns["decide"](rows)


tr = load_traces(S / "rtl_golden2/suite/results")
tr.update(load_traces(A / "staged_golden/suite/results"))
art = json.load(open(A / "full43/run/specflow/oracles.json"))
by = {o["req_uid"]: o for o in art["oracles"]}

print(f"{'req':<10}{'tp':<10}{'frozen':<9}{'split':<9}note")
for uid in SIX:
    o = by.get(uid)
    if o is None:
        print(f"{uid:<10}(not in the artifact)")
        continue
    new, note = split_closes(o["source"], uid)
    for tp in o["tp_uids"]:
        raw = tr.get(tp)
        if raw is None:
            print(f"{uid:<10}{tp:<10}{'-':<9}{'-':<9}no trace")
            continue
        rows = transactional_view(rows_from(raw, side="dut"))
        try:
            a = run(o["source"], rows)[0]
        except Exception as e:                            # noqa: BLE001
            a = f"ERR {type(e).__name__}"
        if "REWRITE DID NOT APPLY" in note or new == o["source"]:
            b = "n/a"          # never report an unrewritten check as unmoved
        else:
            try:
                b = run(new, rows)[0]
            except Exception as e:                        # noqa: BLE001
                b = f"ERR {type(e).__name__}"
        print(f"{uid:<10}{tp:<10}{str(a):<9}{str(b):<9}{note}")
        note = ""
