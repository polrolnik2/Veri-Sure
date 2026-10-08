"""Deterministic single-operator mutation of a reference model.

Used to ask one question about a requirement oracle: does it actually demand
anything? An oracle that passes every mutant of the code it claims to check is
vacuous, which is the inert-model disease one level up, and the repo already
states the cure -- *"the only way to tell agreement from vacuity is to check
that something WRONG fails"* (`benchmarks/mutate.py`).

`benchmarks/mutate.py` cannot be reused: it is regex-over-Verilog. Its *design*
is what carries over, and the three principles are worth restating because each
one earns its keep here. **One operator**, so a surviving mutant attributes to a
single change. **Deterministic**, so a qualification result is reproducible.
**Reports what it changed**, so a human can read why an oracle was convicted.

The restriction to executed lines is the part that is specific to this use, and
it is not an optimisation. An oracle is driven by ONE requirement's stimulus, so
a mutant on a line that stimulus never reaches is invisible to it for reasons
that have nothing to do with the oracle's quality. Proposing such a mutant at
all would manufacture evidence of vacuity.
"""

from __future__ import annotations

import ast
import sys
from dataclasses import dataclass

from .oracles import EDGE_BUDGET, replay

#: The compile filename `oracles._load` uses, and therefore what the line
#: tracer must match on to see only the model's own frames.
MODEL_FILENAME = "<refmodel>"

#: Comparison flips, in a fixed order. Equality first: it is the operator whose
#: inversion most reliably changes observable behaviour rather than a corner.
_CMP_FLIP: list[tuple[type[ast.cmpop], type[ast.cmpop]]] = [
    (ast.Eq, ast.NotEq),
    (ast.NotEq, ast.Eq),
    (ast.Lt, ast.LtE),
    (ast.LtE, ast.Lt),
    (ast.Gt, ast.GtE),
    (ast.GtE, ast.Gt),
]


@dataclass(frozen=True)
class Mutant:
    source: str
    #: What changed, in the form a human can check: "line 41: == becomes !=".
    description: str
    line: int


def executed_lines(
    source: str,
    contract: dict,
    steps: list[dict],
    *,
    base: str,
    edge_budget: int = EDGE_BUDGET,
) -> set[int]:
    """Line numbers of `source` that running this stimulus actually executes.

    A tracer rather than static reachability, because the question is about THIS
    stimulus: a branch that is reachable in principle and never taken by this
    testpoint is exactly the case that must not yield a mutant.

    `sys.settrace` is the harness's own tooling and is deliberately allowed
    here -- `_FORBIDDEN_IMPORTS` constrains what GENERATED code may import, not
    what the process running it may do.
    """
    hit: set[int] = set()

    def _local(frame, event, arg):  # noqa: ANN001
        if event == "line":
            hit.add(frame.f_lineno)
        return _local

    def _global(frame, event, arg):  # noqa: ANN001
        if frame.f_code.co_filename == MODEL_FILENAME:
            return _local(frame, event, arg)
        return None

    previous = sys.gettrace()
    sys.settrace(_global)
    try:
        replay(source, contract, steps, base=base, edge_budget=edge_budget)
    except Exception:  # noqa: BLE001 -- replay already swallows; belt and braces
        pass
    finally:
        sys.settrace(previous)
    return hit


class _Mutator(ast.NodeTransformer):
    """Applies exactly the `target`-th applicable mutation, and no other."""

    def __init__(self, target: int, lines: set[int] | None):
        self.target = target
        self.lines = lines
        self.seen = 0
        self.applied = ""

    def _eligible(self, node: ast.AST) -> bool:
        line = getattr(node, "lineno", None)
        if line is None:
            return False
        return self.lines is None or line in self.lines

    def _take(self, node: ast.AST, description: str) -> bool:
        if not self._eligible(node):
            return False
        hit = self.seen == self.target
        self.seen += 1
        if hit:
            self.applied = f"line {node.lineno}: {description}"
        return hit

    def visit_Compare(self, node: ast.Compare):  # noqa: N802
        self.generic_visit(node)
        for i, op in enumerate(node.ops):
            for src, dst in _CMP_FLIP:
                if isinstance(op, src):
                    if self._take(node, f"{_sym(src)} becomes {_sym(dst)}"):
                        ops = list(node.ops)
                        ops[i] = dst()
                        return ast.copy_location(
                            ast.Compare(left=node.left, ops=ops,
                                        comparators=node.comparators), node)
                    break
        return node

    def visit_Constant(self, node: ast.Constant):  # noqa: N802
        # Booleans are ints in Python; flip them as booleans, not by +1.
        if isinstance(node.value, bool):
            if self._take(node, f"{node.value} becomes {not node.value}"):
                return ast.copy_location(ast.Constant(value=not node.value), node)
            return node
        if isinstance(node.value, int):
            if self._take(node, f"{node.value} becomes {node.value + 1}"):
                return ast.copy_location(ast.Constant(value=node.value + 1), node)
        return node

    def visit_BoolOp(self, node: ast.BoolOp):  # noqa: N802
        self.generic_visit(node)
        flipped = ast.Or() if isinstance(node.op, ast.And) else ast.And()
        word = "and becomes or" if isinstance(node.op, ast.And) else "or becomes and"
        if self._take(node, word):
            return ast.copy_location(
                ast.BoolOp(op=flipped, values=node.values), node)
        return node


def _sym(op: type[ast.cmpop]) -> str:
    return {ast.Eq: "==", ast.NotEq: "!=", ast.Lt: "<",
            ast.LtE: "<=", ast.Gt: ">", ast.GtE: ">="}[op]


def count(source: str, *, lines: set[int] | None = None) -> int:
    """How many mutation sites this source offers under `lines`."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return 0
    m = _Mutator(-1, lines)          # -1 is never hit; this only counts
    m.visit(tree)
    return m.seen


def mutate(
    source: str, index: int, *, lines: set[int] | None = None
) -> Mutant | None:
    """The `index`-th mutant, or None when there is no such site.

    `lines`, when given, restricts sites to lines a replay actually executed.
    Passing None mutates anywhere, which is right for a unit test and wrong for
    qualifying an oracle.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None
    mutator = _Mutator(index, lines)
    mutated = mutator.visit(tree)
    if not mutator.applied:
        return None
    ast.fix_missing_locations(mutated)
    try:
        text = ast.unparse(mutated)
    except Exception:  # noqa: BLE001
        return None
    return Mutant(source=text, description=mutator.applied,
                  line=int(mutator.applied.split()[1].rstrip(":")))


def mutants(
    source: str, *, lines: set[int] | None = None, limit: int = 12
) -> list[Mutant]:
    """Up to `limit` distinct mutants, in deterministic site order.

    Bounded because qualification runs per oracle per turn: on
    i2c_master_bit_ctrl that is 77 oracles, and an unbounded sweep over a
    300-line model would replace a millisecond gate with a slow one for
    evidence that saturates quickly.
    """
    out: list[Mutant] = []
    seen: set[str] = set()
    for i in range(count(source, lines=lines)):
        if len(out) >= limit:
            break
        m = mutate(source, i, lines=lines)
        if m is None or m.source in seen or m.source == source:
            continue
        seen.add(m.source)
        out.append(m)
    return out
