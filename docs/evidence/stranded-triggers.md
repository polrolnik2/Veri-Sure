# No — the `unconditional` check never looks at `opens_on`

`Activation.unconditional` (`specflow/normalize.py:337`) is a lexical regex over
`activation.text`. Its job is to decide `state_dependent`, which decides whether
an `activated_via` reaching chain is demanded. It never reads `opens_on`,
`until` or `aborts_on`, and no other validator cross-checks them against the
prose.

The failure mode is documented — `normalize.py:900` tells the model that
"a requirement whose trigger lives only in `text` reads as unconditional" — but
documentation in a prompt is not a gate, and nothing rejects an activation that
does exactly that.

## Measured on k1-dcfsm's 89 normalized activations

| `activation.text` | `opens_on` | count |
|---|---|---|
| has a conditional connective | **empty** | **17** |
| has a conditional connective | set | 12 |
| neither connective nor "always" | empty | 54 |
| neither | set | 6 |

Seventeen requirements state a condition in prose and give the checker nothing
to open on. Ten of those are **mechanically detectable without a model call**:
the prose names a DECLARED PORT inside the conditional clause, and
`opens_on`/`until`/`aborts_on` omit it.

```
REQ-0040  "while rst is asserted (active-high)"                    missing rst
REQ-0044  "while a CPU-side request is presented (dcqmem_cycstb_i  missing dcqmem_cycstb_i
           asserted) and the data-cache is enabled"
REQ-0060  "a new data-cache request is accepted while dc_en and    missing dc_en
           dcqmem_cycstb_i are asserted"
REQ-0061  "a new request is accepted while dcqmem_we_i is low"     missing dcqmem_we_i
REQ-0048  "biudata_error is asserted while an external BIU         missing biudata_error
           transfer for the current access is ongoing"
REQ-0067  "the first external word is returned with biudata_valid  missing biudata_valid
           asserted"
REQ-0068  "the FSM enters LREFILL3 when the first external word    missing biudata_valid
           is returned (biudata_valid)"
REQ-0025  ...  missing biudata_valid
REQ-0029  ...  missing dc_addr, start_addr
REQ-0032  ...  missing biudata_valid, dcqmem_ci_i
```

Each of these produces a check that fires on every row while the specification
said "while X". That is an over-strictness generator, and it is also why the
FSM-vocabulary escape looked better than it is: 35 of 45 requirements stopped
naming `state`, but most of them stopped naming any condition at all rather than
finding the port bracket that was available.

## The check that is missing

Refuse an activation whose `text` names a declared port inside a conditional
clause when no temporal field mentions that port. Both halves already exist:
the connective regex is `unconditional`'s, and the port-name scan is the same
string match `oracles.ports_read` uses. It costs no model call and would have
caught 10 of 89 here.

The remaining 7 of the 17 name no port in the prose, so they need the author
asked rather than refused -- but they can still be reported, because "you stated
a condition and gave the checker nothing to open on" is true regardless of
whether the condition mentions a port.
