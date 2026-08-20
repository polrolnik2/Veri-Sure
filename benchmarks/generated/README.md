# Generated artifacts, kept as evidence

What the pipeline produced end to end for one task, plus the numbers measured
from it. **Not repo code, not fixtures, and nothing imports them.** They are
here because the measurements in `docs/specflow-migration.md` are otherwise
unreproducible: the runs that made them live in a scratch directory on an
ephemeral container, and a claim like "the generated reference model scores
40/40 against golden and 0/40 against a mutant" is worth exactly as much as the
model it was measured on.

Each directory holds:

| file | what it is |
| --- | --- |
| `ref_model.py` | the reference model the pipeline generated — the oracle under test |
| `rtl.sv` | the RTL the pipeline generated, exactly as emitted |
| `measurement.json` | the scores, the mutant that produced them, and the caveats |

`rtl.sv` is stored **as generated**, including defects. The `alu` candidate has
`input logic` ports, which is what cost it its verdict; rewriting them is a
separate experiment described in its `measurement.json`, not an edit applied
here. An artifact tidied up before storage stops being evidence.

## Reproducing a measurement

    python -m benchmarks.mutate <golden.v> /tmp/mutant.v          # see measurement.json for --op
    python -m benchmarks.golden_check --run <run-dir> \
        --model benchmarks/generated/<task>/ref_model.py \
        --dut golden=<golden.v> --dut mutant=/tmp/mutant.v \
        --top <task> --include <dir>

`golden_check` needs a run directory for the testplan, coverage model and
stimulus; those are large and stay out of the repo, so a full re-measurement
means re-running the pipeline. What is preserved here is the thing being
judged, which is the part that cannot be regenerated identically.

## Read both numbers, never one

A model that returns constants passes golden on a quiet stimulus. Every entry
records the score against a **wrong** DUT next to the score against golden, and
the separation between them. A separation of 0 indicts the mutant before it
indicts the model — `or1200_gmultp2_32x32` read exactly that way for a while,
and the model was correct.
