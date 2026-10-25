"""smoke_report.py RUN MODULE TAG -- what a small editor run did, and what golden says of it.

For iterating on the editor with small runs (a few trials) rather than full arms. Prints counts
and verdicts only, never the editor's text:
  - the editor's tool calls by name;
  - every commit: latched or not, the latch's own numbers (agreement before -> after and whether
    behaviour changed, under the consensus latch; passing requirements);
  - golden's view of the start, the final, and every design that latched, as in metrics.py
    (open loop, every run's stimulus, golden X don't-care): edges and testpoints equal to golden,
    and output cells fixed / broken relative to the start.
"""

import json
import os
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
_src = (HERE / "feedback_audit.py").read_text().split("\nout = {")[0]
FA = {"__file__": str(HERE / "feedback_audit.py"), "__name__": "feedback_audit"}
exec(compile(_src, str(HERE / "feedback_audit.py"), "exec"), FA)  # replay + simulator, no main
EQ = Path(os.environ.get("E7_BEHAVIOUR_WORK", "/tmp/e7_behaviour"))
RUNS = Path(os.environ.get("E7_RUNS", "/home/user/runs-cf"))
E = HERE.parent / "e7"

run, mod, tag = sys.argv[1:4]
log = (RUNS / run / "results" / mod / tag / "editor.log").read_text(errors="replace")
calls = FA["log_records"](log, "input")
print(f"{run} {mod} {tag}: tool calls {dict(Counter(t for t, _ in calls).most_common())}")
start = ((E / run / "editor-cf-gen" / mod / "rtl.sv") if mod == "i2c_master_byte_ctrl"
         else (E / run / "editor" / mod / "rtl_generated.sv")).read_text()
traj = [json.loads(line) for line in open(RUNS / run / f"editor-{tag}" / mod / "debug_trajectory.jsonl")]
commits, final, miss = FA["replay"](start, traj, calls, FA["log_records"](log, "output"))
contract = json.loads((EQ / "corpora" / run / mod / "contract.json").read_text())
G = json.loads((EQ / "out" / mod / "golden.json").read_text())
sim = FA["simulator"](mod)
S = sim(start, contract)


def golden(rtl):
    c = FA["compare"](S, sim(rtl, contract), G)
    return (f"edges {100 * c['edge_after']:.1f}%, testpoints {100 * c['tp_after']:.1f}%, "
            f"cells fixed {c['cells_fixed']} / broken {c['cells_broken']} vs start")


print(f"  start: {golden(start)}")
for i, c in enumerate(commits, 1):
    j = c["requirements"] or {}
    print(f"  commit {i}: {'LATCHED' if c['latched'] else 'rejected'}; passing {j.get('passing')}; "
          f"{c['reason'][:110]}")
    if c["latched"]:
        print(f"     golden: {golden(c['submitted'])}")
delivered = (RUNS / run / f"editor-{tag}" / mod / "rtl.sv").read_text()
print(f"  final ({'replay reproduces it' if FA['norm'](final) == FA['norm'](delivered) else 'NOT the replay'}"
      f", {miss} edits unresolved): {golden(delivered)}")
