"""What the correspondence gate can and cannot reject, measured on full43.

Three things this answers, each of which changed a conclusion:

1. The loop JUDGES three times and REPAIRS twice -- `oracles_stage.py`'s
   `if rounds == verifications: break` sits before the re-ask -- so every
   recorded rejection is an objection the author never answered.
2. The reviewer's self-agreement on a BYTE-IDENTICAL prompt.
3. Whether the `route_requirements` block reached the reviewer, which is the
   only ground on which a requirement that states no obligation can be caught.
   NOTE: `drive.py` filters `requirements` to the 43, and `correspondence.review`
   builds its sibling map from that dict, so a `through_req` pointing outside the
   43 silently loses its block. That is a defect in the DRIVER, and it confounds
   any statistic computed over "routed" rather than "block present".
"""
import json, hashlib, collections, re, sys
from pathlib import Path

A = Path("/tmp/claude-0/-home-user-Veri-Sure/12bb865e-7a51-5506-b55a-e5ac7cf72a4a/scratchpad/asrt")
IO = A / "full43/io"
RUN = Path("/home/user/runs/c1-i2c")
art = json.load(open(A / "full43/run/specflow/oracles.json"))
disp = art["dispositions"]
reqs = {(r.get("req_uid") or r.get("uid")): r for r in
        json.load(open(RUN / "specflow/requirements.json"))["requirements"]}
norm = {(r.get("req_uid") or r.get("uid")): r for r in
        json.load(open(RUN / "specflow/normalized.json"))["normalized"]}
the43 = set(json.load(open(A / "over_strict.json"))["over_strict"])

def verdict(u, r):
    p = IO / f"correspond_{u}_r{r}_response.txt"
    return json.loads(p.read_text()).get("tests_the_requirement") if p.exists() else None

def phash(u, r):
    p = IO / f"correspond_{u}_r{r}_prompt.txt"
    return hashlib.sha1(p.read_bytes()).hexdigest() if p.exists() else None

def block(u):
    p = IO / f"correspond_{u}_r0_prompt.txt"
    return "<route_requirements>" in p.read_text() if p.exists() else False

def routes(u):
    return sorted({(v.get("through_req") or "").strip()
                   for v in (norm.get(u) or {}).get("observed_via") or []} - {""})

print("1. REPAIR ATTEMPTS PER ROUND (label `_fix{round}`)")
fixes = collections.Counter(m[1] for p in IO.glob("oracle_REQ-*_fix*_r*_response.txt")
                            if (m := re.match(r"oracle_REQ-\d+_fix(\d+)_r\d+_response", p.name)))
for k in sorted(fixes):
    print(f"   round {k}: {fixes[k]} re-asks")
print("   round 3: 0 re-asks  <- the break sits before the re-ask\n")

print("2. REVIEWER SELF-AGREEMENT ON AN UNCHANGED PROMPT")
same = flips = 0
detail = []
for u in disp:
    for i in (1, 2):
        if phash(u, i) and phash(u, i) == phash(u, i - 1):
            same += 1
            if verdict(u, i) is not verdict(u, i - 1):
                flips += 1
                detail.append((u, f"r{i}->r{i+1}", verdict(u, i - 1), verdict(u, i), disp[u]))
print(f"   byte-identical adjacent pairs: {same}")
print(f"   verdict changed anyway:        {flips}  ({100*flips/same:.0f}%)")
print(f"   self-agreement:                {100*(same-flips)/same:.0f}%")
for d in detail:
    print("     ", d)
pat = collections.Counter("".join("O" if verdict(u, r) is True else
                                  "R" if verdict(u, r) is False else "?"
                                  for r in (0, 1, 2)) for u in disp)
print("   patterns:", dict(pat.most_common()))
late = sorted(u for u in disp if disp[u] == "ORACLE_INVALID" and verdict(u, 1) is True)
print(f"   passed round 2, killed at round 3: {late}\n")

print("3. DID THE ROUTE BLOCK REACH THE REVIEWER?")
t = collections.Counter((block(u), disp[u]) for u in disp)
for b in (True, False):
    tr, iv = t[(b, "TRUSTED")], t[(b, "ORACLE_INVALID")]
    print(f"   {'block present' if b else 'no block    '}: "
          f"TRUSTED {tr:>2}  ORACLE_INVALID {iv:>2}  reject {100*iv/(tr+iv):>3.0f}%")
sup = [u for u in disp if routes(u) and not block(u)]
print(f"   routed but block SUPPRESSED BY THE DRIVER ({len(sup)}): {sorted(sup)}")
for u in sorted(sup):
    print(f"      {u} -> {routes(u)}  (none in the 43)")
tsup = collections.Counter(disp[u] for u in sup)
print(f"      of those: {dict(tsup)}  -- reject rate "
      f"{100*tsup['ORACLE_INVALID']/len(sup):.0f}%, at the {100*t[(False,'ORACLE_INVALID')]/(t[(False,'TRUSTED')]+t[(False,'ORACLE_INVALID')]):.0f}% base rate\n")

print("4. THE DEFINITIONAL REQUIREMENTS")
OBLIG = re.compile(r"\b(shall|must|releases|drives|asserts|pulses|reloads|resets|"
                   r"pauses|holds|detects|implements|performs|produces|prevents|"
                   r"disables|enables|decodes|captures)\b", re.I)
COP = re.compile(r"\b(is the|is a|indicates that|means that)\b", re.I)
for u in sorted(disp):
    txt = (reqs.get(u) or {}).get("text", "")
    if COP.search(txt) and not OBLIG.search(txt):
        vs = "".join("O" if verdict(u, r) is True else "R" for r in (0, 1, 2))
        rt = ",".join(routes(u)) or "none"
        print(f"   {u}  block={str(block(u)):<5} routes={rt:<28} {vs}  {disp[u]}")
