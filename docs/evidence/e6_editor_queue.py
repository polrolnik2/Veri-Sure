"""What the RTL editor is ASKED to fix, classified by what it CAN fix.

    python docs/evidence/e6_editor_queue.py <run_dir> <uid> [<uid> ...]

The editor's work queue is `list_failing_requirements`. This classifies that
queue against S1's own `unit_kind`, because a requirement S1 called
`scaffolding` or `interface` states no obligation the DESIGN can discharge --
no edit to the RTL makes "The input port clk is the system clock" true or
false -- and a queue item like that cannot be worked, only guessed at.

Measured on one run's 122 frozen checks against an independently written
candidate:

    kind            failing  in set  fail rate
    behavioural          27     111        24%
    scaffolding           4       5        80%
    interface             3       6        50%
    TOTAL                34     122        28%

**A fifth of the queue is unfixable by construction, and the unfixable items
fail at two to three times the rate of the real ones.** That is a floor under
the editor's achievable score: a perfect design still fails those checks, and
the trials spent on them are spent for nothing.

It also truncates: `list_failing_requirements` cuts requirement text at 200
characters, which bites hardest on the omnibus requirements that most need
their full text -- three of the failing set are longer than that.
"""
from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

RUN = Path(sys.argv[1])
FAIL = [a for a in sys.argv[2:] if a.startswith("REQ-")]
sf = RUN / "specflow"
reqs = {r["uid"]: r for r in json.loads((sf / "requirements.json").read_text())
        ["requirements"]}
held = [x["req_uid"] for x in json.loads((sf / "oracles.json").read_text())
        ["oracles"]]

fk = collections.Counter(reqs.get(u, {}).get("unit_kind") for u in FAIL)
ak = collections.Counter(reqs.get(u, {}).get("unit_kind") for u in held)
print(f"{'kind':14} {'failing':>8} {'in set':>7} {'fail rate':>10}")
for k in ("behavioural", "scaffolding", "interface"):
    rate = 100 * fk.get(k, 0) / max(1, ak.get(k, 0))
    print(f"{k:14} {fk.get(k, 0):>8} {ak.get(k, 0):>7} {rate:>9.0f}%")
print(f"{'TOTAL':14} {len(FAIL):>8} {len(held):>7} "
      f"{100*len(FAIL)/max(1,len(held)):>9.0f}%")

bad = [u for u in FAIL if reqs.get(u, {}).get("unit_kind") != "behavioural"]
print(f"\nUNFIXABLE BY CONSTRUCTION: {len(bad)} of {len(FAIL)} "
      f"= {100*len(bad)/max(1,len(FAIL)):.0f}% of the queue")
for u in bad:
    print(f"  {u} [{reqs.get(u,{}).get('unit_kind')}] "
          f"{str(reqs.get(u,{}).get('text'))[:90]}")

long = sorted(((len(reqs.get(u, {}).get("text") or ""), u) for u in FAIL),
              reverse=True)
over = [(n, u) for n, u in long if n > 200]
print(f"\ntruncated in the queue (text cut at 200 chars): {len(over)}")
for n, u in over:
    print(f"  {u} {n} chars")
