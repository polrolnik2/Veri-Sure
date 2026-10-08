# Nothing was deleted: the trigger was never encoded, and a generic envelope was

## Correcting the previous reading

An earlier version of this note said the trigger "stayed in prose" and listed ten
requirements as mechanically detectable. Both halves were wrong.

Tracing `normalize_REQ-*_r{0,1}_response.txt` against the final artifact:
`opens_on` was **empty at round 0 and unchanged by every repair round**. Nothing
was deleted, and no gate ever asked about it — the repair rounds that ran were
repairing observation routes, not the activation. Two of the ten (REQ-0029,
REQ-0068) in fact *have* a populated `opens_on`; they were caught only because
the ports my scan matched appear in the expectation text rather than the
activation.

## What actually happened

`aborts_on` was filled with a generic envelope. Across all 89 activations there
are **four distinct values**:

| count | `aborts_on` |
|---|---|
| **54** | `[{"dcqmem_cycstb_i": 0}, {"rst": 1}]` |
| 20 | `[]` |
| 9 | `[{"rst": 1}]` |
| 6 | `[{"biudata_error": 1}, {"dcqmem_cycstb_i": 0}, {"rst": 1}]` |

Fifty-four requirements share one abort pair. REQ-0067's own reasoning states
the move plainly: *"Reset and dropping the request strobe abort the sequence, so
they are listed as `aborts_on`."* That is a defensible envelope — the
requirement really does stop applying if the request goes away — but it is the
same envelope for most of the design, so it carries no per-requirement
information, and it leaves the window open from row 0.

Of the 17 activations with a conditional connective in `text` and an empty
`opens_on`:

| count | what is there instead |
|---|---|
| **14** | a closing condition, but the generic one — while the prose names a *different* trigger (`biudata_valid`, `dc_en`, `dcqmem_we_i`, `biudata_error`) |
| 2 | nothing at all — REQ-0040 "while rst is asserted", REQ-0048 "biudata_error is asserted while a BIU transfer is ongoing" |
| 1 | the named port present, as an abort rather than an opening (REQ-0060, `dcqmem_cycstb_i`) |

## Why the shape is what it is

`aborts_on` is easy to fill with a plausible generic envelope, and filling it
satisfies every check that exists. `opens_on` — the field that would carry the
discriminating condition — has **no requirement to be non-empty**, and
`Activation.unconditional` (`normalize.py:337`) is a lexical regex over `text`
that decides whether a reaching chain is demanded and never reads any temporal
field. The prompt warns about triggers living only in prose
(`normalize.py:900`); nothing enforces it.

So the failure is not extraction and not repair. It is that the schema's
discriminating field is optional while its envelope field is easy, and no gate
compares either against what the requirement says.

## The check to add

Refuse an activation whose `text` names a declared port inside a conditional
clause when NO temporal field mentions that port — 15 of 89 here (the 14 plus
REQ-0048; REQ-0040's `rst` is arguably the envelope itself). Both halves exist
already: the connective regex is `unconditional`'s, the port scan is the string
match `oracles.ports_read` uses, and it costs no model call.

Worth reporting separately: an `aborts_on` value shared by more than half the
requirement set is boilerplate, and a gate that noticed that would have said so
here without knowing anything about caches.
