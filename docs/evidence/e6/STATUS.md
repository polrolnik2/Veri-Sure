# Where the triple stands, and what is blocked

## The target

    span > 90%    blindness < 20%    audit = 0

(Blindness was relaxed from < 10% to < 20% by the owner mid-session.)

## The only honest measurements on the board

Both re-scored by the current code with GOLDEN RTL as the audit control, since
the Python control exposes 0 of 24 declared probes and 97 of 111 accepted
checks abstain on it by construction.

    run     span        blindness     audit             denominator
    full2   0.9737 MET  0.1454 MET    0.2432  NOT MET   37 of 111
    full7   0.9820 MET  0.2896 no     0.3600  NOT MET   50 of 109

`full2` meets span and blindness. **Audit is the only unmet column**, and the
whole of it is accounted for:

    cause                                    checks   after a phase correction
    probe PHASE (registered vs combinational)     5    0   -- VALIDATED
    downstream of the same                        1    0
    `throughout` over a TO_END window             1    0   -- gate shipped
    `slave_wait` EXTENT, sentence ambiguous       2    2   -- OPEN
    cause not found (REQ-0058)                    1    0

Advancing exactly two probes -- `sta_condition` and `sto_condition`, the only
ones the specification writes an equation for -- takes the triple to

    phase-correct sta/sto   SPAN 0.9737 MET   BLIND 0.1454 MET   AUDIT 0.0571

**Audit 24.3% -> 5.7% at no cost to span or blindness**, both holding to four
decimal places. The two survivors are the `slave_wait` sentence, which admits
both a level and an event; golden reads it as an event and the population reads
it as a level in every body it ever wrote.

## What is blocked, and why it is not a choice

The pipeline has NO model access. Verified three ways:

  * `OPENAI_BASE_URL` (the configured gateway) returns
    `429 BUDGET_EXCEEDED` on a direct probe, with the `/v1` suffix and the
    un-prefixed model name;
  * no other API key or token is present in the environment;
  * `ANTHROPIC_BASE_URL` is set to `api.anthropic.com` but carries neither
    `ANTHROPIC_API_KEY` nor `ANTHROPIC_AUTH_TOKEN` -- this session
    authenticates through its harness, not through anything a subprocess can
    use.

So an end-to-end run cannot be started from here by any route. Everything
above is a re-score of stored artifacts by the changed stages, which is what
"run only from the stage you changed" permits and is NOT the same as the
autonomous end-to-end demonstration the goal asks for.

## What shipped this session

    tb/runtime.py          refuse a probe binding wider than declared
    refmodel/compose.py    emit PROBE_WIDTHS; brief the author on wide probes
    refmodel/temporal.py   unbounded_invariant, phase_sensitive, delay_probes
    refmodel/oracles.py    well_formed refuses an invariant over a TO_END window
    refmodel/oracle_gen.py the phase rule, in the probe-conditional block
    probes.py              ProbeEntry carries a width, default 1
    scorecard.py           audit_verdicts, so an RTL control can supply the column

Suite 2625 passed, 1 skipped; ruff clean over `specflow` and `tests`.

## What to do when budget returns, in order

1. **Re-run the probe stage on i2c.** The five value-shaped probes (`fscl`,
   `fsda`, `filter_cnt`, `cscl`, `csda`) should come back with real widths now
   that `ProbeEntry` can carry one. That widens the audit denominator instead
   of shrinking it -- the width guard currently pushes abstentions on golden
   from 75 to 83.
2. **Re-run the oracle stage** from the probe artefacts, so checks are authored
   under the phase rule and the `TO_END` refusal. Expect the five phase checks
   to be written phase-tolerant and REQ-0034/0046/0128 to be repaired or
   abandoned rather than shipped.
3. **Re-score with an RTL control** (`e6_rescore_rtl_control.py`). The
   prediction on the table: audit near 0.057 before the `slave_wait` question
   is settled, span and blindness unmoved.
4. **Settle `slave_wait`.** It is a reading of one sentence, not a mechanical
   fix, and it is the last two convictions.

## Reproducing any of this without the gateway

    docs/evidence/e6_rescore_rtl_control.py   <run>/specflow <shared> <gold-suite>
    docs/evidence/e6_rule_sweep.py            <run>/specflow <gold> <substrate>
    docs/evidence/e6_selection_bound.py       <run>/specflow <gold>
    docs/evidence/e6_subagent_loop.py         brief|apply <run-dir>

All four are zero model calls.
