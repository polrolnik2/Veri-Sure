# Where the triple stands, and what is blocked

**Rewritten after the corrections of 2026-09-23.** An earlier version of this file
reported `full2` at audit 0.2432 over 37 checks, and 0.0571 under a phase
correction. **Both figures are withdrawn**: they were measured against a golden
suite whose stimulus provenance was never digest-checked. `TRIPLE.md` carries the
withdrawal and the reason.

## The target

    span > 90%    blindness < 20%    audit = 0

(Blindness was relaxed from < 10% to < 20% by the owner mid-session.)

## TWO OF THREE TARGETS ARE MET AT ONCE, ON THE ORIGINAL BARS

`scorecard.score` stopped keying checks by `req_uid`, so the plan's central
direction -- "fill the pool, then select" -- became measurable. Admitting every
well-formed corpus body beside the accepted set:

    config             bodies   span            blindness       audit
    accepted only         122   0.9737 MET      0.1457          9/42 = 0.2143
    all well-formed       476   0.9737 MET      0.0586 MET     20/52 = 0.3846

**Blindness 14.6% -> 5.9%, under the ORIGINAL 10% bar, at no cost to span.**
`effective_size` goes 99 -> 273, so the added bodies are separators rather than
copies. Audit rises, and must: rejections union, so a bigger set constricts
harder. `POOL-DEPTH.md` has the full sweep and what it overturns.

    target            span > 90%    blindness < 10%    audit = 0
    all well-formed   97.4%  MET    5.9%   MET         38.5%  NOT MET

So the remaining gap is ENTIRELY the audit column, on both the accepted set and
the deep pool. Whether selection takes it back without giving up span or
blindness is measured by `e6_select.py`, whose threshold is chosen by fewest
equivalence classes accepted -- a population-only criterion -- with the audit
column reported afterwards and never consulted.

## The measurement on the ACCEPTED set, on a digest-verified control

`full2`'s frozen artifacts, re-scored by today's code against golden RTL run
through a suite REGENERATED FROM THE CORPUS, whose 482 traces digest-match the
corpus's own stimulus 482 of 482.

    configuration          span            blindness       audit
    baseline               0.9737 MET      0.1457 MET       9/42 = 0.2143
    phase rule only        0.9737 MET      0.1457 MET       1/40 = 0.0250
    licence rule only      0.9737 MET      0.1416 MET       9/42 = 0.2143
    **both rules**         **0.9737 MET**  **0.1416 MET**   **1/40 = 0.0250**

    target     span > 90%    blindness < 20%    audit = 0
    measured   97.4%  MET    14.2%  MET         2.5%  NOT MET

Two rules, neither reading the audit column: **PHASE** (the specification writes
an equation, not a schedule, so `sta_condition`/`sto_condition` may be registered)
and **`|->` NOT `|=>`** (`after_activation=True` demoted wherever the requirement
carries no sequence word and licenses no cycle count -- 28 of 122 matched).

`LAST-CONVICTION.md` is the detail on the one that remains, including why closing
it from here would be grade-gating, and the measured comparison against the
symmetric form of the phase rule (which is worse: 2/35 = 0.0571, because
abstention costs the denominator five checks).

## What remains, and why

    REQ-0055 [behavioural]  the last counted conviction
    REQ-0058 [scaffolding]  not counted by the audit column, and not explained

**REQ-0055's cause is named and is NOT reachable from stored artifacts.** The
requirement says the controller shall "pause its timing counter"; `normalize` set
`observable: ['cmd_ack']`; the check asserted `cmd_ack == 0` and golden holds it
high at the activation row. `cmd_ack` is not a timing counter -- the contract
declares `clk_en`, `cnt_zero`, `filter_cnt`.

And **selection cannot fix it**: all four of REQ-0055's corpus bodies read
`cmd_ack`, as do all 24 bodies across the seven requirements with an unlicensed
observable that convict -- zero deviations across generate, resample, cell and
repair arms. The pool is perfectly obedient to a field nothing licence-checks. See
`OBSERVABLE-LICENCE.md`, which measures the field at **34% of forms unlicensed**,
against `effect_follows`'s 75% on the same corpus.

So **audit = 0 is not reachable without a model call**, and the model is
unavailable (below). That is the state, not a preference.

## What shipped this session

    tb/runtime.py            record the sampled width of every signal into the trace
    refmodel/temporal.py     _nothing_read: a strong existential over ZERO rows
                             abstains; eventually / until / sequence / nth
    refmodel/rtl_trace.py    over_width_ports (a value that does not fit its
                             declared width) and declared_width_gap (a port the
                             simulator reports wider than declared), both folded
                             into the abstention decide_rtl already produced
    docs/sva-divergence.md   U1 extended to the existential half of its own
                             sentence; U1b added for the width guard

Suite 2664 passed, 1 skipped; ruff clean over `specflow` and `tests`.

The three fixes together took baseline audit 16/45 -> 9/42 and, with the two
rules, 6/43 -> 1/40. Blindness moved +0.0003 at baseline and not at all with the
rules applied. Span unmoved to four places throughout.

## The corpora, and why they exist

**`/home/user/runs` was reclaimed again between sessions -- the fifth such loss on
this branch.** The two committed corpora are what survived, and `full2` re-scored
from its tarball in a cold container at span 0.9737 / blindness 0.1454 unchanged.

    docs/evidence/e6/corpora/full2.tar.gz   390 KB, + a readable MANIFEST.json
    docs/evidence/e6/corpora/full7.tar.gz   395 KB

`CORPORA.md` has the re-run and unattended-run commands. Every audit figure since
has come from a suite regenerated out of a corpus, which is also the test of the
claim that `suite/` need not be packed.

## What is blocked, and why it is not a choice

The pipeline has NO model access. Re-verified at the end of this session:

  * `OPENAI_BASE_URL` returns `429 BUDGET_EXCEEDED` on a four-token probe, with
    the `/v1` suffix and the un-prefixed model name;
  * no other API key or token is present in the environment;
  * `ANTHROPIC_BASE_URL` is set but carries neither `ANTHROPIC_API_KEY` nor
    `ANTHROPIC_AUTH_TOKEN` -- this session authenticates through its harness,
    not through anything a subprocess can use.

So an end-to-end run cannot be started from here by any route. Everything above is
a re-score of stored artifacts by the changed stages, which is what "run only from
the stage you changed" permits and is NOT the autonomous end-to-end demonstration
the goal asks for.

## What to do when budget returns, in order

1. **Re-run the probe stage on i2c.** The six over-width probes (`cscl`, `csda`,
   `fscl`, `fsda`, `filter_cnt`, `idle`) should come back with real widths now
   that `ProbeEntry` carries one. That WIDENS the audit denominator instead of
   shrinking it -- today all six are refused, which is right and is still a loss
   of reach.
2. **Re-run normalize**, and read `OBSERVABLE-LICENCE.md` and
   `LAST-CONVICTION.md` first. 34% of forms
   name an observable the requirement's words do not license, and REQ-0055 is one
   of them. This is the only route to audit = 0 identified.
3. **Re-run the oracle stage** from those artifacts, so checks are authored under
   the phase rule and the `TO_END` refusal rather than having them applied
   afterwards -- `LAYERED-GATES.md` shows what applying a gate late costs
   (0.88 span points and no convictions, because the library fixes had already
   removed the two it would have caught).
4. **Re-score and pack** with `e6_autorun.py`, which preflights the gateway,
   passes the control as `audit_control` only, and packs on completion AND on
   failure.

## Reproducing any of this without the gateway

    e6_verify_corpus.py     <corpus-dir> [<golden-suite-dir>]
    e6_replay_corpus.py     <corpus-dir> <rtl.v> <out-dir>
    e6_corrected_triple.py  <corpus-dir> <golden-suite-dir>
    e6_unbounded_rule.py    <corpus-dir> <golden-suite-dir>
    e6_phase_abstain.py     <corpus-dir> <golden-suite-dir>
    e6_observable_licence.py <corpus-dir>
    e6_rescore_rtl_control.py / e6_rule_sweep.py / e6_selection_bound.py

All zero model calls. `e6_replay_corpus.py` runs a simulator; the rest are replay
and set arithmetic. **Golden is RUN and never read.**
