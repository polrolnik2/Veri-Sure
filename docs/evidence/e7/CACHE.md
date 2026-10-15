# The chat path cached nothing through OpenRouter, and why

## What was measured

Five fresh runs (`openai/gpt-6-luna`, OpenRouter, provider `openai/flex`),
first 1,047 calls, all in S1 (`boundary`, `classify`):

    prompt tokens   5,192,121
    cached             77,430   = 1.5%
    written         5,105,353   (~98% of every prompt paid to store)

The prompts were not the problem. 98.5-99% of every S1 prompt is an identical
prefix ending at `fanout.shared_block`'s sentinel:

    boundary   sentinel at 21,262 of 21,501 chars   99.0% shared
    classify   sentinel at 22,905 of 23,262 chars   98.5% shared

## Isolating the cause

The same real prompt sent three times in a row caches on both tiers, so the
tier is not the cause:

    flex       cached 0, 4941/4944, 4941/4944
    standard   cached 0, 4941/4944, 4941/4944

Three DIFFERENT prompts sharing a 99% prefix, sequential, one
`prompt_cache_key`:

    one `user` message                        cached 0, 0, 0
    `system` (prefix) + `user` (suffix)       cached 0, 3933/4000, 3933/4000

The router keys its routing on the leading message; a flat string whose tail
differs is a new destination every time. `PortSettings.developer_role_prefix`
already split the prompt for exactly this reason -- on the Responses path only.
The default chat path sent one flat `user` string.

## The fix, and what it bought

`model_io._chat_messages` applies the same split on the chat path (commit
`11249c7`). Measured on the live runs after the restart at 07:49:57, before any
module's cache was warm:

    all modules      87.3% of prompt tokens cached (first 18 calls)
    fpu_exceptions   97.8%
    i2c_bit_ctrl     83.9%
    or1200_dc_fsm    72.8%   (its first call is the cold write)

and through `ApiPort` directly, three real classify prompts in sequence:
0, 4205/4365, 4205/4356.
