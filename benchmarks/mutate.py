#!/usr/bin/env python3
"""One deterministic single-operator mutation of a design. A debug instrument.

Phase 2 of the oracle work needs a *wrong* DUT for every design, not just for
the one that happens to have an LLM-written candidate lying around. Without one,
"the generated reference model passes golden" is unfalsifiable: a model that
returns constants passes golden on a quiet stimulus too, and the only way to
tell agreement from vacuity is to check that something WRONG fails.

Deliberately one operator, deliberately deterministic, and it reports what it
changed. A random or multi-site mutant makes a failure hard to attribute, and an
unreported one makes the whole measurement unreproducible.

**Not a mutation-scoring tool.** `specflow/qualify.py` is that (mcy, G8), and it
does the formal equivalence filtering this does not. This produces one wrong
design so a discrimination check has something to discriminate against.

Usage: python -m benchmarks.mutate <golden.v> <out.v> [--op N]
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

#: Ordered so the first applicable one is the most likely to change observable
#: behaviour rather than a corner: arithmetic before bitwise before comparison.
MUTATIONS: list[tuple[str, str, str]] = [
    (r"(?<![+\-*/<>=!&|^~])\+(?![+=])", "-", "+ becomes -"),
    (r"(?<![+\-*/<>=!&|^~])-(?![-=>])", "+", "- becomes +"),
    (r"(?<![*/])\*(?![*/=])", "+", "* becomes +"),
    (r"(?<![&])&(?![&=])", "|", "bitwise & becomes |"),
    (r"(?<![|])\|(?![|=])", "&", "bitwise | becomes &"),
    (r"<<", ">>", "<< becomes >>"),
    (r"(?<![<>=!])==(?!=)", "!=", "== becomes !="),
]

_COMMENT = re.compile(r"//[^\n]*|/\*.*?\*/", re.S)

#: `[msb:lsb]` — a width or part-select range. Editing one resizes a
#: declaration rather than changing logic, and the result is very often an
#: EQUIVALENT mutant: widening `input [`W-1:0] X` to `[`W+1:0]` leaves every
#: driven bit untouched when the extra bits are never read. `or1200_gmultp2_32x32`
#: is the extreme case — all five of its sites were ranges, so the tool could not
#: express a wrong version of that design at all, and the discrimination check it
#: fed reported separation 0 for a reason that had nothing to do with the model.
#: Bit-selects without a colon (`x[i+1]`) stay mutable; they are logic.
_RANGE = re.compile(r"\[[^\[\]\n]*:[^\[\]\n]*\]")


def _maskable(text: str) -> list[tuple[int, int]]:
    """Spans that must not be mutated: comments, strings, `directives, ranges."""
    spans = [(m.start(), m.end()) for m in _COMMENT.finditer(text)]
    spans += [(m.start(), m.end()) for m in re.finditer(r'"[^"\n]*"', text)]
    spans += [(m.start(), m.end()) for m in re.finditer(r"^\s*`\w+[^\n]*", text, re.M)]
    spans += [(m.start(), m.end()) for m in _RANGE.finditer(text)]
    return spans


def mutate(source: str, index: int = 0) -> tuple[str, str]:
    """Apply the `index`-th applicable mutation. Returns `(text, description)`."""
    blocked = _maskable(source)

    def inside(pos: int) -> bool:
        return any(a <= pos < b for a, b in blocked)

    applicable = 0
    for pattern, replacement, description in MUTATIONS:
        for m in re.finditer(pattern, source):
            if inside(m.start()):
                continue
            if applicable != index:
                applicable += 1
                continue
            line = source[:m.start()].count("\n") + 1
            out = source[:m.start()] + replacement + source[m.end():]
            return out, f"line {line}: {description}"
    raise SystemExit(f"no applicable mutation at index {index}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="mutate", description=__doc__)
    ap.add_argument("source", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--op", type=int, default=0, help="which applicable site")
    args = ap.parse_args(argv)

    text, what = mutate(args.source.read_text(errors="ignore"), args.op)
    args.out.write_text(text, encoding="utf-8")
    print(f"{args.source.name} -> {args.out.name}: {what}", file=sys.stderr)
    print(what)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
