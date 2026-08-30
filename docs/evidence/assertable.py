"""Which requirements state a falsifiable obligation on a declared port?

THE BAR, and nothing else counts: a determinate CONDITION, and a determinate
EFFECT that lands on a port the contract declares. Four ways to miss it:

  DEFINITION      copular or descriptive -- "X is the Y", "X indicates that Y".
                  Nothing to falsify.
  INTERNAL        the effect named is a signal the contract does not declare --
                  a counter, sda_chk, slave_wait, clk_en, the FSM's state.
  SCOPE           a role or capability summary. "Translates each command into
                  timed sequences" has no determinate effect to check.
  HEDGED          the effect is qualified into indeterminacy -- "at the
                  appropriate timing phases", "according to I2C timing".

Hand labels for the 32 no-route requirements of the 43 are in HAND, so the rules
can be scored rather than asserted.
"""
import json, re, sys
from pathlib import Path

RUN = Path("/home/user/runs/c1-i2c")
ports = {p["name"] for p in json.load(open(RUN / "contract.json"))["io"]}

INTERNAL = re.compile(
    r"\b(sda_chk|slave_wait|clk_en|filter_cnt|scl_sync|sSCL|sSDA|dscl_oen|"
    r"timing counter|filter counter|clock divider|internal counter|"
    r"counter cnt|the internal|FSM state|idle state|input filter)\b", re.I)
COPULAR = re.compile(r"\b(is the|is a|are the|indicates that|means that)\b", re.I)
OBLIG = re.compile(
    r"\b(shall|must|releases?d?|drives?|driven|asserts?|asserted|deasserts?|"
    r"deasserted|pulses?d?|pulls?|pulled|reloads?|resets?|pauses?d?|holds?|"
    r"sets?|clears?|presents?|captures?|samples?|remains?|prevents?|"
    r"generates?|detects?|causes?)\b", re.I)
SCOPE = re.compile(
    r"\b(implements the|module implements|begins operation|role:|"
    r"translate each|corresponds to|supports generation)\b", re.I)
HEDGE = re.compile(
    r"\b(appropriate|as needed|according to I2C timing|as required)\b", re.I)

def classify(text: str) -> tuple[bool, str]:
    t = " ".join(text.split())
    if SCOPE.search(t):                       return False, "SCOPE"
    if COPULAR.search(t) and not OBLIG.search(t): return False, "DEFINITION"
    if HEDGE.search(t):                       return False, "HEDGED"
    if INTERNAL.search(t):                    return False, "INTERNAL"
    if not OBLIG.search(t):                   return False, "no obligation verb"
    return True, "assertable"

# Hand labels: True = states a falsifiable obligation on a declared port.
HAND = {
 "REQ-0001": False, "REQ-0002": True,  "REQ-0005": True,  "REQ-0006": True,
 "REQ-0007": False, "REQ-0016": False, "REQ-0020": False, "REQ-0026": False,
 "REQ-0028": False, "REQ-0030": True,  "REQ-0050": True,  "REQ-0055": False,
 "REQ-0057": True,  "REQ-0059": True,  "REQ-0063": True,  "REQ-0066": True,
 "REQ-0067": True,  "REQ-0071": True,  "REQ-0073": True,  "REQ-0075": False,
 "REQ-0080": False, "REQ-0087": False, "REQ-0093": True,  "REQ-0095": False,
 "REQ-0097": True,  "REQ-0101": True,  "REQ-0102": False, "REQ-0107": True,
 "REQ-0117": True,  "REQ-0118": True,  "REQ-0121": True,  "REQ-0124": True,
}

if __name__ == "__main__":
    reqs = {(r.get("req_uid") or r.get("uid")): r for r in
            json.load(open(RUN / "specflow/requirements.json"))["requirements"]}
    agree = dis = 0
    print(f"{'req':<10}{'rules':<10}{'hand':<6}{'ground':<22}")
    for u in sorted(HAND):
        ok, why = classify((reqs.get(u) or {}).get("text", ""))
        mark = "" if ok == HAND[u] else "   <-- DISAGREE"
        agree += ok == HAND[u]; dis += ok != HAND[u]
        print(f"{u:<10}{str(ok):<10}{str(HAND[u]):<6}{why:<22}{mark}")
    print(f"\nrules agree with hand on {agree}/{agree+dis}")
