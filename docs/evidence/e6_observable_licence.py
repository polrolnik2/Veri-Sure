"""Is the port `normalize` chose to observe one the REQUIREMENT names?

    e6_observable_licence.py <corpus-dir>

**THE MISSING GATE IS NOT ABOUT `effect_follows`. IT IS ABOUT EVERY FIELD OF THE
NORMALIZED FORM.** `EFFECT-FOLLOWS.md` measured one field -- whether the
requirement's words license "the effect follows the trigger" -- found 39 of 52
unlicensed, and deliberately shipped no gate because that share was too large to
act on without knowing how many were harmful. This measures a different field the
same way, and it was found by chasing a single conviction:

    REQ-0055  requirement   "...the bit-level controller shall PAUSE ITS TIMING
                             COUNTER until SCL is released."
              normalize     observable: ['cmd_ack']
              the check     throughout(window, cmd_ack == 0)
              golden        cmd_ack is 1 at the activation row -> CONVICTED

`cmd_ack` is not a timing counter. The contract declares `clk_en`, `cnt_zero` and
`filter_cnt`; normalize picked the command-acknowledge line, the check obediently
asserted it, and the conviction is filed against the author. `oracle_gen`'s own
comment predicts exactly this -- "a wrong window arrives as an instruction and
departs as the author's defect" -- and the field it happens on turns out not to be
only the window.

## The licence test, stated so its limits are visible

A port `P` in `normalized.observable` is LICENSED by its requirement when either

  1. `P` occurs in the requirement's text, matched case-insensitively and also
     with `_` removed and replaced by a space, so `scl_oen` is licensed by
     "scl_oen", "SCL_OEN" and "scl oen"; or
  2. `P` stripped of a conventional direction or enable suffix -- `_o`, `_i`,
     `_oen`, `_en`, `_n` -- occurs in the text. This one is NOT optional and the
     first draft of this file did not have it: "The external SCL and SDA lines
     are controlled using open-drain semantics" observes `scl_o`, `sda_o`,
     `scl_oen` and `sda_oen`, all four of which it plainly IS about, and rule 1
     called every one unlicensed. A rule whose false positives are that easy to
     find is measuring its own spelling; or
  3. the contract entry for `P` carries a `spans` string -- a verbatim quotation
     from the specification, which is what `spans` is for -- that occurs in the
     requirement's text.

Otherwise it is UNLICENSED. **It is still generous in one direction and strict in
another, and both matter.** Generous: a requirement saying "shall acknowledge"
licenses nothing named `cmd_ack` under any rule above unless the contract quoted
the right sentence, so some unlicensed hits remain the test's fault rather than
normalize's. Strict: a port the requirement DOES name can still be the wrong one
to observe, which this cannot see at all.

So the output is a census and a sample to read, not a gate. It reads no audit
column to decide anything; the intersection with the convicting set is reported
afterwards, as a measurement.
"""
import json
import re
import sys
from pathlib import Path

SRC = Path(sys.argv[1])
reqs = {r["uid"]: r for r in
        json.loads((SRC / "requirements.json").read_text())["requirements"]}
_n = json.loads((SRC / "normalized.json").read_text())
norm = _n["normalized"] if isinstance(_n, dict) else _n
contract = json.loads((SRC / "contract.json").read_text())
entry = {str(e.get("name")): e for e in (contract.get("io") or []) if e.get("name")}
oracles = json.loads((SRC / "oracles.json").read_text())["oracles"]
shipped = {o["req_uid"] for o in oracles}


def variants(port: str) -> list[str]:
    p = port.lower()
    return sorted({p, p.replace("_", ""), p.replace("_", " ")})


#: Verilog's conventional direction and enable suffixes. Stripping them is what
#: lets "the external SCL line" license `scl_oen`, and it is domain-neutral --
#: no i2c signal name appears here.
SUFFIXES = ("_oen", "_en", "_o", "_i", "_n")


def _in(text_low: str, token: str) -> bool:
    return bool(re.search(rf"(?<![a-z0-9_]){re.escape(token)}(?![a-z0-9_])",
                          text_low))


def licensed(port: str, text: str) -> str | None:
    """`None` when unlicensed, else which rule licensed it."""
    low = text.lower()
    for v in variants(port):
        if _in(low, v):
            return "named"
    for suf in SUFFIXES:
        if port.lower().endswith(suf) and len(port) > len(suf):
            base = port.lower()[: -len(suf)]
            if base and any(_in(low, v) for v in variants(base)):
                return "base"
    for span in (entry.get(port, {}).get("spans") or []):
        s = str(span).strip().lower()
        if len(s) > 8 and s in low:
            return "span"
    return None


rows: list[tuple] = []
for n in norm:
    uid = n.get("req_uid") or n.get("uid")
    if uid not in reqs:
        continue
    text = str(reqs[uid].get("text") or "")
    for port in (n.get("observable") or []):
        rows.append((uid, str(port), licensed(str(port), text)))

total = len(rows)
by_rule: dict = {}
for _, _, how in rows:
    by_rule[how] = by_rule.get(how, 0) + 1
unlicensed = [(u, p) for u, p, how in rows if how is None]
print(f"observable ports named by a normalized form      {total}")
print(f"  licensed -- the requirement names the port      {by_rule.get('named', 0)}")
print(f"  licensed -- its base name, suffix stripped      {by_rule.get('base', 0)}")
print(f"  licensed -- a contract `spans` quotation        {by_rule.get('span', 0)}")
print(f"  **UNLICENSED**                                 {len(unlicensed)}"
      f"  ({100 * len(unlicensed) / max(1, total):.0f}%)")

ship_un = sorted({u for u, _ in unlicensed if u in shipped})
print(f"\nrequirements with an unlicensed observable that a SHIPPED check "
      f"reads: {len(ship_un)} of {len(shipped)}")

CONV = ("REQ-0034 REQ-0035 REQ-0053 REQ-0055 REQ-0058 REQ-0061 REQ-0066 "
        "REQ-0067 REQ-0069 REQ-0096 REQ-0100 REQ-0102 REQ-0110 REQ-0111 "
        "REQ-0112 REQ-0113 REQ-0128").split()
hit = [u for u in CONV if u in ship_un]
print(f"  ...of the 17 that convict golden: {len(hit)}  {' '.join(hit)}")

#: WHICH PORTS THE UNLICENSED HITS ARE. **They are SPREAD, not concentrated** --
#: `cmd_ack` is the most common at 19% and fifteen ports appear, so "normalize has
#: one fallback observable" is NOT what this shows and an earlier draft of this
#: comment said it did.
#:
#: The sharper cut is below: requirements where NOT ONE of the observable ports
#: is licensed by any rule. Those are the sentences where the test found nothing
#: and normalize named ports anyway -- "The input port clk is the system clock"
#: observing `cmd_ack`, "The ena input is the core enable signal" observing
#: `cmd_ack`. A definition of an input has no output to observe, and naming one
#: is a default rather than a reading, which is what `EFFECT-FOLLOWS.md`
#: concluded about a different field of the same form.
count: dict = {}
for u, prt in unlicensed:
    count[prt] = count.get(prt, 0) + 1
print("\nunlicensed observables BY PORT:")
for prt, k in sorted(count.items(), key=lambda kv: (-kv[1], kv[0])):
    print(f"  {prt:14} {k:3}  ({100 * k / max(1, len(unlicensed)):.0f}% of the unlicensed)")

per_req: dict = {}
for n in norm:
    uid = n.get("req_uid") or n.get("uid")
    if uid not in reqs:
        continue
    ports = [str(x) for x in (n.get("observable") or [])]
    if not ports:
        continue
    text = str(reqs[uid].get("text") or "")
    per_req[uid] = sum(1 for prt in ports if licensed(prt, text) is not None)
blind_forms = sorted(u for u, k in per_req.items() if k == 0)
print(f"\nnormalized forms naming at least one observable          {len(per_req)}")
print(f"  ...where NOT ONE observable port is licensed           {len(blind_forms)}"
      f"  ({100 * len(blind_forms) / max(1, len(per_req)):.0f}%)")
print(f"  ...of those, a SHIPPED check reads it                  "
      f"{len([u for u in blind_forms if u in shipped])}")
print(f"  ...of those, it convicts golden                        "
      f"{len([u for u in blind_forms if u in CONV])}"
      f"  {' '.join(u for u in blind_forms if u in CONV)}")

print("\na sample to READ, because the test's own limits are the finding:")
for u, p in unlicensed[:14]:
    t = " ".join(str(reqs[u].get("text") or "").split())
    print(f"  {u} -> {p:14} {t[:112]}")
