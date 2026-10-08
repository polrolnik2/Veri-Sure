# normalize produces the SAME form for distinct requirements, and the right form for one of a pair

Two measurements, both exact rather than fuzzy, both offline. They do not lower the
audit column. What they do is settle WHERE the residue's causes live, with an
internal control instead of a licence heuristic.

## 1. The same sentence normalized twice, once right and once wrong

`DEPTH-RESIDUE.md` attributes REQ-0051 to the stimulus stage and REQ-0055 to
`normalize`, and reads them as near-duplicates. Their normalized forms:

    REQ-0051   observable ['clk_en']    until [{'slave_wait': 0}]
    REQ-0055   observable ['cmd_ack']   until [{'sscl': 1}]

    REQ-0051  "...shall hold its timing counter and keep clk_en LOW while
               slave_wait is asserted."
    REQ-0055  "While the slave-wait condition remains active ... shall PAUSE ITS
               TIMING COUNTER until SCL is released."

**They are NOT duplicates** -- a hypothesis of mine that this refutes -- and the
difference is the finding. Both sentences are about holding the timing counter
during a slave wait. `normalize` named `clk_en` for one, which is the port the
requirement is about, and `cmd_ack` for the other, which is not a timing counter at
all.

**That is an internal control on the observable defect.** `OBSERVABLE-LICENCE.md`
had to argue from a licence heuristic that 34% of forms name an unlicensed port;
this is the same specification content normalized twice, once correctly, with no
heuristic in between. The field is not under-determined by the requirement -- the
stage simply got one of them wrong.

## 2. Twenty-one groups of requirements share an EXACTLY identical form

Keyed on `(opens_on, until, aborts_on, effect_follows, observable)` -- exact
equality, no threshold to tune:

    requirements with a normalized form                152
    groups sharing a form exactly                       21
    requirements in such a group                        71   (47%)

Some of that is correct. The largest group is 20 requirements with entirely empty
forms, and they are list markers -- "List-item marker 3 states no requirement",
"The numbered list marker \\"10.\\" states no requirement" -- classified
`scaffolding`, which is exactly right: a marker has no activation and no
observable.

The rest is not. One group of seven:

    opens_on []   until []   observable ['cmd_ack']

      REQ-0014  "The input port clk is the system clock."
      REQ-0015  "All synchronous state updates occur on the rising edge of clk."
      REQ-0018  "The ena input is the core enable signal."
      REQ-0026  "The bit-level command input cmd supports the I2C_CMD_WRITE command."
      REQ-0030  "The scl_i port is the external I2C SCL line input..."
      REQ-0114  "The module handles clock stretching and multi-master clock
                 synchronization in parallel with bus-status..."
      REQ-0120  "The internal timing counter cnt shall be loaded from the clk_cnt
                 prescale input and decremented..."

A definition of `clk`, a definition of `ena`, and an obligation about loading the
timing counter, given one form observing `cmd_ack`. Whatever REQ-0120 requires,
`cmd_ack` with no activation and no close condition is not it.

And genuine duplicates are in there too, which is a different defect -- S1's:

    REQ-0067 / REQ-0112     both "detect a STOP when filtered SDA rises while
                            filtered SCL is high"
    REQ-0061 / REQ-0102 / REQ-0103   all the two-stage synchroniser
    REQ-0075 / REQ-0141     both "capture filtered SDA into dout on each rising
                            edge of filtered SCL"

## What this changes, and what it does not

It does NOT close the audit column. Deduplicating would not drop REQ-0055, which
has no exact duplicate; and choosing which member of a duplicate pair to keep by
which one convicts is gating on the grade.

What it changes is the confidence behind `DEPTH-RESIDUE.md`'s attribution. "Four of
five causes are upstream" rested on reading sentences; this rests on two exact
measurements: the stage names the right port for one of a near-identical pair and
the wrong one for the other, and 47% of its forms are not distinguishable from some
other requirement's. `normalize` is where the residue's causes live, and the
evidence for that is now internal to the stage rather than inferred from what its
output convicts.

Reproduce both with the queries in this document's git history; they read
`normalized.json` and `requirements.json` and nothing else. No model calls, no
design, no control.
