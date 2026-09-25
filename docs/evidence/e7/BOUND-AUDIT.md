# The audit with the probes bound to golden by hand

## Why

Checks that read a probe could only be judged on the known-good design when a
signal of the SAME NAME and width existed in it. On `full2` that left 43 of 111
accepted checks judgeable and audit read 10/43. The user asked for the probes to
be bound to golden's own internals to test what the audit column was not seeing.
`docs/evidence/e7_bind_golden.py` does it with a per-module binding
(`docs/evidence/e7/golden_bind/`), audit-only: golden's RTL is not modified and
no pipeline stage reads a binding.

## What it shows (full2, shipped set, pipeline rules)

    probes bound            judgeable   convicting   audit
    by name (before)            43          10        23%
    by hand (all 21 of 24)     101          59        58%

Span 97.4% and blindness 9.1% are unchanged (neither reads golden). Every one of
the convicting requirements reads a probe; no port-only check convicts.

## What the convictions are

The bindings are faithful -- each probe is golden's own signal for the quantity
the contract names, at golden's own timing. The convictions are timing
conventions the specification does not state, where the spec-derived population
(Python models that respond within the step) and golden (registered RTL) differ:

    dout read on the filtered-SCL rising-edge row     golden registers dout <= sSDA
    cmd_ack inside a *_sequence window                 golden raises it on the first
                                                        idle row, after the sequence
    sda_oen from din during WRITE                      a two-row lag
    ordered steps inside a sequence                    steps land on other rows
    + the earlier non-timing residue (reset, prescale 0, level vs edge)

## The latency gate against the bound audit

Dropping every body the gate flags (NO repair round), re-cutting the cover:

    gate                                       flagged   span    blind   audit
    none (pipeline today)                          -     97.4%   9.1%    59/101
    obs +1 row, the check's own testpoints        55     89.5%   9.35%   49/89
    five retimings, own testpoints                93     84.2%  17.7%    45/84
    obs +1/+2 rows, ALL passing testpoints       194     70.2%  37.1%    26/66

The gate as wired tests only a check's own `tp_uids` (median ~2), where the
triggering event often never occurs with a value that exposes the lag. Tested on
every passing testpoint it flags 194 of 440 bodies -- 44% of the pool rests on a
latency the specification never stated -- and even dropping all of them leaves
26/66 convicting for non-latency reasons.

## What this means for the goal

audit = 0 was measured over the checks golden could be judged on by name. With
the probes honestly bound, the gap is not a residue of a few checks but a
systematic property of checks authored and screened against a population whose
timing conventions differ from the reference's. Dropping checks cannot close it
without destroying span and blindness; only rewriting them can, which is the
repair round the stage gate buys -- untested at this breadth.
