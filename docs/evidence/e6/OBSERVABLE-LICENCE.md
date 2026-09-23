# The missing gate is not about `effect_follows`. It is about every field of the normalized form.

`EFFECT-FOLLOWS.md` measured ONE field of `normalize`'s output -- whether the
requirement's own words license "the effect follows the trigger" -- found **39 of
52 unlicensed**, and deliberately shipped no gate, because that share was too
large to act on without knowing how many were harmful rather than merely
unlicensed.

This is a different field, measured the same way. It was found by chasing a single
conviction.

## REQ-0055, which is where this started

    requirement   "While the slave-wait condition remains active because a bus
                   participant holds SCL low, the bit-level controller shall
                   PAUSE ITS TIMING COUNTER until SCL is released."
    normalize     observable: ['cmd_ack']
    the check     throughout(window, cmd_ack == 0, after_activation=False)
    golden        cmd_ack is 1 at the activation row  ->  CONVICTED

**`cmd_ack` is not a timing counter.** The contract declares `clk_en`, `cnt_zero`
and `filter_cnt`; normalize named the command-acknowledge line, the check
obediently asserted it, and the conviction is filed against the author.
`oracle_gen`'s own comment predicts exactly this -- "a wrong window arrives as an
instruction and departs as the author's defect" -- and it turns out the field it
happens on is not only the window.

This also supersedes an earlier reading. `TRIPLE.md` once attributed REQ-0055 to
the degenerate-stimulus finding, on the strength of its text saying "timing
counter". The check does not read a timing counter.

## The licence test, stated so its limits are visible

A port `P` in `normalized.observable` is LICENSED by its requirement when

  1. `P` occurs in the requirement's text -- case-insensitively, and with `_`
     removed and replaced by a space, so `scl_oen` is licensed by "scl_oen",
     "SCL_OEN" and "scl oen"; or
  2. `P` stripped of a conventional direction or enable suffix (`_o`, `_i`,
     `_oen`, `_en`, `_n`) occurs in the text; or
  3. the contract entry for `P` carries a `spans` string -- a verbatim quotation
     from the specification, which is what `spans` is for -- that occurs in the
     text.

**Rule 2 is not optional, and the first draft of this measurement did not have
it.** "The external SCL and SDA lines are controlled using open-drain semantics"
observes `scl_o`, `sda_o`, `scl_oen` and `sda_oen`, all four of which it plainly
IS about, and rule 1 alone called every one unlicensed -- 49% unlicensed overall,
measuring this test's spelling rather than normalize's reading. With rule 2 the
figure is 35%.

It remains generous in one direction and strict in another. Generous: "shall
acknowledge" licenses nothing named `cmd_ack` unless the contract quoted the right
sentence, so some unlicensed hits are still the test's fault. Strict: a port the
requirement DOES name can be the wrong one to observe, which this cannot see.

## The census, on `full2`

    observable ports named by a normalized form          243
      licensed -- the requirement names the port         119
      licensed -- its base name, suffix stripped          35
      licensed -- a contract `spans` quotation             4
      **UNLICENSED**                                      85   (35%)

    normalized forms naming at least one observable       132
      ...where NOT ONE observable port is licensed         45   (34%)
      ...of those, a shipped check reads it                42
      ...of those, it convicts golden                       7

        REQ-0055 REQ-0061 REQ-0066 REQ-0102 REQ-0110 REQ-0111 REQ-0112

**34%, against `effect_follows`'s 75% on the same corpus.** Two different fields
of the same artifact, neither licence-checked, both unlicensed at a rate far too
high to gate on blind.

### The unlicensed hits are SPREAD, not one default

    cmd_ack 16 (19%)   scl_oen 12 (14%)   busy 5   sda_oen 5   al 4   cscl 4
    csda 4   dout 4   sda_chk 4   sscl 4   ssda 4   ...and nine more at 1-3

So "normalize has one fallback observable" is **not** what this shows, and an
earlier draft of this note said it did. Fifteen ports appear.

The sharper cut is the 45 forms where nothing at all is licensed, because those
are the sentences where the test found no anchor and normalize named ports anyway:

    REQ-0014  "The input port clk is the system clock."              -> cmd_ack
    REQ-0015  "All synchronous state updates occur on the rising
               edge of clk."                                          -> cmd_ack
    REQ-0018  "The ena input is the core enable signal."              -> cmd_ack

**A definition of an INPUT has no output to observe.** Naming one is a default,
not a reading -- which is word for word what `EFFECT-FOLLOWS.md` concluded about
`effect_follows` on a definition: "A definition has no effect to follow anything.
`effect_follows=True` on one is not a reading of the sentence; it is a default."

Two fields, two defaults, one cause.

## What this does NOT propose

**No gate, and deliberately.** 34% of forms is the same order as the 75% that
stopped `EFFECT-FOLLOWS.md` from shipping one, and for the same reason: an
unlicensed observable can still be the right port, and refusing on this test as
written would refuse REQ-0016 ("the internal state, counters, filtered inputs,
bus-status flags, and command FSM are reset" observing `busy`, `al`, `cmd_ack`)
where the sentence does license those semantically and only the spelling fails.

What it establishes is the SHAPE of the defect: `normalize.gate_one` "checks that
the response parsed, that there is one block, that `clk` is not in the window and
that the port names are declared. It never asks whether [the fields] are licensed
by the requirement's own words." That sentence was written about the window. It is
true of the observable too, and of `effect_follows`, and nothing measures how many
other fields it is true of.

Reproduce with `docs/evidence/e6_observable_licence.py <corpus-dir>` -- no model
calls, no design, no control.
