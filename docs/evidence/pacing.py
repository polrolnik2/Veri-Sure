"""The stimulus is paced too short, and 10 of 90 checks convict golden for it.

MEASURED TWICE ON THE SAME 90 CHECKS, the same 224 testpoints and the same
golden i2c RTL. The ONLY difference is how long each stimulus step is driven:

  stimulus as the pipeline wrote it   FAIL 12   UNCOVERED 27   pass 51
  every step held for 60 edges        FAIL  3   UNCOVERED 27   pass 60

The ten the hold clears all go to PASSES, not to UNCOVERED, and that is the
whole finding. If they had gone silent the hold would merely be hiding them --
a check that never fires accuses nobody. They pass. The design meets those ten
requirements once the stimulus gives it time to, and the pipeline's own
rendering was cutting each command short and then blaming the design.

UNCOVERED is 27 either way, which is the control: the pacing does not change
WHICH checks fire, only what they see once they do.

  cleared by the hold, all to passing
    REQ-0010 REQ-0027 REQ-0054 REQ-0059 REQ-0060
    REQ-0068 REQ-0088 REQ-0105 REQ-0115 REQ-0126

  appears only WITH the hold
    REQ-0006 -- and this is the honest direction. Under the short stimulus its
    window closed before the scenario arose, so it passed for lack of evidence.
    Given time it fails, for the filtered-bus latency reason
    `docs/evidence/repair5.py` names. A longer stimulus makes the instrument
    MORE exercised, not more lenient.

  fails under both
    REQ-0030 REQ-0095 -- the same residue.

WHERE THE DEFECT IS. Not in the schema: `runtime.normalise_step` accepts
`{"inputs": ..., "hold": N}` and `{"inputs": ..., "until": ...}`, and the
stimulus author's prompt documents both. It is in what the author CHOOSES. On
c1-i2c's 1872 steps:

  hold only                        810   median 3 edges, mean 5.7, max 64
  until (waits for a condition)    695
  reset                            184
  bare -- holds for ONE edge       183

`until` is the correct mechanism and it is used on 37% of steps. The rest are
paced by a number, and the numbers are small: 899 of 1872 steps (48%) drive for
eight edges or fewer. The runtime's own comment records the scale they are being
compared against -- "one i2c testpoint sets a prescaler needing 506 edges for a
single command."

WHAT THIS IS NOT. `hold=60` is not the fix and is not proposed as one; it is a
blunt override that happens to exceed every i2c command in this design, and on
another design it would be wrong in the other direction. It is used here to
ISOLATE the variable. The fix belongs in the stimulus author: a step that starts
a transaction should close on `until`, not on a guessed edge count.

WHY IT MATTERS BEYOND THIS SUITE. An over-strictness figure is only meaningful
against a stated stimulus rendering. "43 of 110 convict golden", "5 convict",
"12 convict" and "3 convict" are all measurements of THIS oracle set, and the
spread between the last two is entirely pacing. Any future number has to say
which rendering produced it.

Reproduce:
  loop_run.py <out> <golden.v> 0      # as written
  loop_run.py <out> <golden.v> 0 60   # held
"""

import collections
import json
import statistics
import sys
from pathlib import Path

RUN = Path("/home/user/runs/c1-i2c")


def pacing(stimulus: dict) -> tuple[dict, list[int]]:
    """How every stimulus step decides when it is over."""
    n: collections.Counter = collections.Counter()
    holds: list[int] = []
    for t in stimulus["testpoints"]:
        for s in t["stimulus_steps"]:
            if "reset" in s:
                n["reset"] += 1
            elif "until" in s:
                n["until (waits for a condition)"] += 1
            elif "hold" in s:
                n["hold only"] += 1
                holds.append(int(s["hold"]))
            else:
                n["bare -- one edge"] += 1
    return dict(n), holds


def main() -> int:
    n, holds = pacing(json.loads((RUN / "specflow/stimulus.json").read_text()))
    total = sum(n.values())
    print("c1-i2c stimulus steps, by how each one decides when it is over:")
    for k, v in sorted(n.items(), key=lambda kv: -kv[1]):
        print(f"  {k:<32}{v:>6}{100 * v / total:>6.0f}%")
    print(f"\nhold-only values: median {statistics.median(holds):.0f}  "
          f"mean {statistics.mean(holds):.1f}  max {max(holds)}")
    short = n.get("bare -- one edge", 0) + sum(1 for h in holds if h <= 8)
    print(f"{short} of {total} steps ({100 * short / total:.0f}%) drive for "
          f"eight edges or fewer, against a design where one testpoint's "
          f"prescaler needs 506 edges for a single command.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
