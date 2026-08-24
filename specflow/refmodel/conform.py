"""A second implementation of the design, built to be satisfied.

The must-pass leg of oracle promotion needs something an oracle OUGHT to accept.
Today that role is played by `benchmarks/controls/`, which holds exactly one
design -- so the gate that catches over-strict oracles is available for i2c and
nowhere else. Measured on g-i2c: 27 of 77 isolated oracles are failed by that
control, and without it all 27 reach the debug agent unfiltered.

This generates the missing control instead of requiring one.

**It is not a golden model and must never be treated as one.** It is a second
independent reading of the same requirements, so an oracle failing it means the
two readings disagree -- not that the oracle is definitely wrong. That weaker
claim is still the one worth having, because an oracle no reading of the
requirement satisfies is one nothing can ever discharge, and a debug agent sent
after it spends its budget on a demand no implementation meets.

**Why the reference model cannot play this role.** It is the artifact under
debug: deciding an oracle against it and requiring agreement is what gate 1
already does, and a model that is wrong makes every correct oracle look
over-strict. This one is generated once, never edited, and never judged.

**Why the golden control cannot play this role either.** Feeding its behaviour
back into oracle generation would fit oracles to a known-good implementation --
the contamination invariant I1 exists to prevent, arriving through the repair
channel -- and would destroy `golden_check` as a held-out measure. The control
stays out of the loop and grades the result.
"""

from __future__ import annotations

from pathlib import Path

from ..model_io import ModelPort
from ..schema import Issue


def conforming_implementation(
    *,
    requirements: list[dict],
    contract_json: str,
    port: ModelPort,
    workdir: Path,
    max_repairs: int = 2,
) -> tuple[str, list[Issue]]:
    """Generate one implementation of the design. Returns `(source, issues)`.

    Reuses the reference model's own generation path with the judge and the
    debugger switched off, which is already exactly "produce an implementation
    from the requirements, gated on the mechanical checks alone". Sharing it is
    what keeps this from drifting into a different kind of artifact: it is the
    same prompt, the same contract-derived dispatch, the same `validate` gate,
    so anything an oracle may assume about the reference model holds here too.

    Returns `("", issues)` when nothing gate-clean could be produced. A missing
    conforming implementation weakens the promotion gate; it must not fail the
    run, because the run is still better off with unpromoted oracles than with
    no oracles.
    """
    from .compose import run_refmodel

    result, source = run_refmodel(
        requirements=requirements,
        contract_json=contract_json,
        port=port,
        workdir=Path(workdir),
        max_repairs=max_repairs,
        judge_port=None,
        debugger=None,
    )
    return (source if result.ok else ""), list(result.issues)
