# The span graph is real, and today it is a LAYOUT graph

Naming spec spans is cheap, already done, and already carries character offsets
— so a dependency graph falls out of overlaps for free: an edge from A to B
wherever A's `spec_spans` overlap B's obligation. Built on both runs:

| | requirements | with spans | span-overlap edges |
|---|---|---|---|
| h3-i2c | 118 | 82 | 106 |
| k1-dcfsm | 89 | 49 | 63 |

Every requirement carrying a span produces one or two edges. The graph exists.

## But it encodes position, not derivation

**Every edge in both runs is positionally adjacent — 106 of 106, and 63 of 63,
all within 1200 characters of the citing requirement's own obligation. Zero
distant edges.** The pattern in the uids is just as blunt: REQ-0057 → REQ-0056,
REQ-0066 → REQ-0065, REQ-0086 → REQ-0085, REQ-0100 → REQ-0099, REQ-0101 →
REQ-0100. The span-picker cites the neighbouring paragraph.

So it recovers the i2c filter chain in **1 of 9** cases, and that one
(REQ-0052 → REQ-0051) is also uid−1 — layout, not retrieval.

## Which explains the depth result a second way

The i2c filter definition sits far from everything that needs it:

| consumer | distance to REQ-0051 (defines `sSCL`) |
|---|---|
| REQ-0057 | 895 chars |
| REQ-0066 | 1821 |
| REQ-0028 | 2560 |
| REQ-0027 | 2836 |
| REQ-0086 | 4347 |
| REQ-0099 | 6027 |
| REQ-0100 | 6087 |
| REQ-0101 | 6195 |

dc_fsm's REQ-0007 → REQ-0006, the "accepted request" definition its oracle
built its whole window from, is **90 characters** away — the previous sentence.

So dc_fsm is not only shallower, its specification is **written in derivation
order**, and positional adjacency therefore coincides with semantic dependency.
i2c's is not: the filter has its own section, far from every requirement that
depends on it. A layout graph is a derivation graph exactly when the author of
the document happened to write it that way, and nothing checks that.

## The change that makes the idea work

The field, the offsets, the emission and the delivery to normalize, testplan,
oracle and witness all exist. What is wrong is the question being asked. Today
the span-picker is asked for supporting text and returns what is nearby. Ask
instead:

> for each term this requirement uses that is NOT a declared port, cite the span
> that DEFINES that term, wherever it is in the document

and the same field becomes a derivation edge. Three things follow for free:

* the edge is **labelled** with the term, so it is a typed dependency rather
  than a proximity;
* it is **checkable without a model** — a span cited as defining `sSCL` must
  contain `sSCL`;
* it is **spec-derived, never RTL-derived**, so it carries none of the
  circularity that rules out slicing the artifact under test.

That is also the stratification the fixpoint construction needs
(`fixpoint-not-a-graph.md`), supplied at S1 by a question that costs no extra
call — the span is being written either way.

The evidence that it would work is the case where it accidentally already does:
when the definition happens to be adjacent, the span is exactly right, and
k1's oracle author used it verbatim to build a window the normalized
activation never carried.
