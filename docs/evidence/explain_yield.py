"""What `explain` actually delivered, across every live editor run.

Not an argument about whether the annotation is a good idea -- a count of what
each field contained on all 22 `explain` calls the four sessions made. The
observation in round N's prompt IS round N-1's tool result, so the rendezvous
files are a complete record with nothing reconstructed.

THE FINDING, and it is not the one the section was written expecting:

  what_would_satisfy_it   22 calls, ONE distinct answer. Every single one reads
                          "NO single-value change at the deciding edge satisfies
                          this check, so the defect is TEMPORAL". A field whose
                          output never varies carries no information: it is a
                          constant printed 22 times, not evidence.

                          §5.6 argued the opposite -- "when NO single-value
                          perturbation satisfies it, say so plainly... it tells
                          the agent the defect is TEMPORAL rather than a wrong
                          value". That reasoning holds only if the field can
                          ALSO say the other thing, and on this oracle family it
                          cannot: `_perturb` rewrites the port at the DECIDING
                          EDGE only, while every check here is an
                          `eventually`/`throughout` over a window, so changing
                          one edge at the window's end can almost never satisfy
                          it. The instrument is asking a question whose answer
                          is structurally fixed.

  block_internals         0 signals in run 1 (no waveform dumped), 12 in run 2
                          and ALL TWELVE CONSTANT (the alphabetical cap took
                          localparams; and the lookups were 1000x out anyway),
                          4-10 moving signals from run 3 onward once both were
                          fixed. Correct for two runs, and neither of those runs
                          reached a productive edit -- run 3 was blocked by the
                          driver guard's false positive, run 4 by the splice
                          welding tokens together. So its value is UNMEASURED.

  boundary_ports          4-15 rows every call. Real trace data throughout;
  transitions             1-9 per call. Also real.

WHAT THIS SAYS ABOUT THE INVESTMENT. Four sessions have been spent and the loop
has not once completed a productive edit; each died on a different harness
defect. Of §5.6's five annotation items, one is measurably dead weight, one has
been correct for two runs and never yet acted on, and three have been carrying
real data the whole time. Anyone citing "the editor gets a rich failure
annotation" should read this file first.
"""

import json
import sys
from pathlib import Path

A = Path("/tmp/claude-0/-home-user-Veri-Sure/12bb865e-7a51-5506-b55a-e5ac7cf72a4a"
         "/scratchpad/asrt")
RUNS = ("edit1", "edit2", "edit3", "edit4")


def calls(run: str) -> list[dict]:
    """Every `explain` result the run produced, from the rendezvous files."""
    io = A / run / "io"
    out = []
    if not io.exists():
        return out
    for prompt in sorted(io.glob("edit_r*_prompt.txt")):
        n = int(prompt.stem.split("_r")[1].split("_")[0])
        prev = io / f"edit_r{n - 1}_response.txt"
        if n == 0 or not prev.exists():
            continue
        try:
            if json.loads(prev.read_text()).get("tool") != "explain":
                continue
        except ValueError:
            continue
        body = prompt.read_text().split("LAST OBSERVATION\n", 1)[1]
        try:
            out.append(json.loads(body[:body.rindex("}") + 1]))
        except ValueError:
            continue
    return out


def main() -> int:
    rows, answers = [], set()
    for run in RUNS:
        for d in calls(run):
            internals = dict(d.get("block_internals") or {})
            held = internals.pop("__held_constant__", {})
            sat = d.get("what_would_satisfy_it") or ""
            answers.add(sat)
            rows.append((run, (d.get("requirement") or {}).get("req_uid", "?"),
                         len(internals), len(held),
                         len(d.get("boundary_ports") or []),
                         len(d.get("transitions") or []), sat))
    if not rows:
        print("no rendezvous records found under", A)
        return 1
    print(f"{'run':<7}{'req':<11}{'moved':>6}{'held':>6}{'bound':>6}{'trans':>6}")
    for run, uid, moved, held, bound, trans, _ in rows:
        print(f"{run:<7}{uid:<11}{moved:>6}{held:>6}{bound:>6}{trans:>6}")
    print(f"\n{len(rows)} explain calls.")
    print(f"distinct what_would_satisfy_it answers: {len(answers)}")
    for a in sorted(answers):
        print("   ", a[:100])
    if len(answers) == 1:
        print("\nONE answer in every call: this field carries no information.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
