"""Backward dataflow slice over a reference model, from the ports that failed.

The Python counterpart of `eda_agent/trace_slicer.py`, and deliberately the same
shape so the two can be read side by side: parse the source into blocks carrying
read/write sets, invert writes into a driver map, then walk backwards from the
failing signals to a bounded depth.

WHY THIS EXISTS RATHER THAN `covers`. `DebugSession.covers` maps a requirement to
the methods claimed to implement it -- but it is a field the model GENERATOR
fills in (`agent.py:39`), an assertion about code rather than an analysis of it.
It can be wrong, stale after an edit, or simply absent, and nothing checks it. A
debugger steered by it is steered by the same model whose output is under
suspicion.

`trace_slicer.dynamic_slice` had no such option for Verilog and computed the
slice. Here it is EASIER than there, not harder: the model is Python, so `ast`
gives exact attribute reads and writes per method with no heuristics and no
tree-sitter fallback. `covers` becomes a cross-check -- a method it names that
the slice does not reach is worth reporting, because one of the two is wrong.

WHAT A SLICE MUST NOT DO. Over-approximate freely; under-approximate never. A
method missing from the slice is a method the agent cannot read, so every
uncertain case is included. `trace_slicer` makes the same trade
(`_extract_idents` treats every identifier in a block as a read).
"""

from __future__ import annotations

import ast
from dataclasses import dataclass

#: How far back through the attribute graph to walk. Matches
#: `trace_slicer.dynamic_slice`'s default; a reference model is shallower than
#: RTL, so this reaches most of what feeds a port.
MAX_DEPTH = 3


@dataclass(frozen=True)
class Block:
    """One method, with what it reads, writes, calls and supplies.

    `trace_slicer.RtlBlock` plus `calls`. Verilog blocks do not invoke one
    another, so the RTL slicer needs no call edge; Python methods do, and a
    reference model uses them -- `o['scl_oen'] = self.mask(scl_oen, 1)` where
    `scl_oen` came from `self._state_outputs()` puts the real driver one call
    away. Dropping that edge would under-approximate, which is the one direction
    a slice must never err in.
    """

    name: str
    start_line: int
    end_line: int
    #: `self.X` assigned in this method.
    writes: tuple[str, ...]
    #: `self.X` read in this method.
    reads: tuple[str, ...]
    #: `self.m(...)` invoked from this method.
    calls: tuple[str, ...]
    #: Declared output port -> what supplies it here: attribute names, and the
    #: methods a local in the value expression was bound from.
    supplies: dict[str, tuple[str, ...]]


def _attrs(node: ast.AST, *, store: bool) -> set[str]:
    """`self.X` names under `node`, in Store or Load position."""
    want = ast.Store if store else ast.Load
    out: set[str] = set()
    for sub in ast.walk(node):
        if (isinstance(sub, ast.Attribute)
                and isinstance(sub.value, ast.Name) and sub.value.id == "self"
                and isinstance(sub.ctx, want)):
            out.add(sub.attr)
    return out


def _calls(node: ast.AST) -> set[str]:
    """`self.m(...)` method names invoked under `node`."""
    out: set[str] = set()
    for sub in ast.walk(node):
        if (isinstance(sub, ast.Call)
                and isinstance(sub.func, ast.Attribute)
                and isinstance(sub.func.value, ast.Name)
                and sub.func.value.id == "self"):
            out.add(sub.func.attr)
    return out


def _names(node: ast.AST) -> set[str]:
    """Bare local names read under `node`."""
    return {n.id for n in ast.walk(node)
            if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)}


def _local_sources(fn: ast.AST) -> dict[str, set[str]]:
    """local name -> the `self.m()` calls it was bound from.

    `scl_oen, sda_oen = self._state_outputs()` binds two locals to one call.
    Without this the port assigned from `scl_oen` traces back to nothing and the
    slice falls open to the whole model -- measured on the generated i2c model,
    where `scl_oen` and `sda_oen` reach their ports exactly this way.
    """
    out: dict[str, set[str]] = {}
    for node in ast.walk(fn):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)) or node.value is None:
            continue
        called = _calls(node.value)
        if not called:
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        for t in targets:
            for sub in ast.walk(t):
                if isinstance(sub, ast.Name):
                    out.setdefault(sub.id, set()).update(called)
    return out


def _supplied(fn: ast.AST, declared: set[str]) -> dict[str, set[str]]:
    """port -> the attributes and methods its value expression comes from.

    Two shapes, both live in this repo: a returned dict literal
    (`return {'cmd_ack': self.cmd_ack}`) and subscript assignment into an
    outputs mapping (`o['cmd_ack'] = self.mask(self.cmd_ack, 1)`), which is what
    the generated i2c model actually does. Handling only the first found nothing
    at all there.
    """
    locals_from = _local_sources(fn)
    out: dict[str, set[str]] = {}

    def _record(port: str, value: ast.AST) -> None:
        if declared and port not in declared:
            return
        src = _attrs(value, store=False) | _calls(value)
        for name in _names(value):
            src |= locals_from.get(name, set())
        out.setdefault(port, set()).update(src)

    for node in ast.walk(fn):
        if isinstance(node, ast.Return) and isinstance(node.value, ast.Dict):
            for key, value in zip(node.value.keys, node.value.values):
                if isinstance(key, ast.Constant) and isinstance(key.value, str):
                    _record(key.value, value)
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                if (isinstance(t, ast.Subscript)
                        and isinstance(t.slice, ast.Constant)
                        and isinstance(t.slice.value, str)):
                    _record(t.slice.value, node.value)
    return out


def parse_methods(source: str, ports: set[str] | None = None) -> list[Block]:
    """Every method of the model class, with its read/write/call/supply sets.

    Returns [] on a source that does not parse -- an unparseable model is the
    editor's problem and not this module's, and raising here would take out the
    tool that was about to report it.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    declared = ports or set()
    blocks: list[Block] = []
    for cls in (n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)):
        for fn in cls.body:
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            blocks.append(Block(
                name=fn.name,
                start_line=fn.lineno,
                end_line=getattr(fn, "end_lineno", fn.lineno) or fn.lineno,
                writes=tuple(sorted(_attrs(fn, store=True))),
                reads=tuple(sorted(_attrs(fn, store=False))),
                calls=tuple(sorted(_calls(fn))),
                supplies={k: tuple(sorted(v))
                          for k, v in sorted(_supplied(fn, declared).items())},
            ))
    return blocks


def build_driver_map(blocks: list[Block]) -> dict[str, list[Block]]:
    """attribute -> the methods that assign it. `trace_slicer.build_driver_map`."""
    drivers: dict[str, list[Block]] = {}
    for b in blocks:
        for w in b.writes:
            drivers.setdefault(w, []).append(b)
    return drivers


def backward_slice(
    *,
    fail_ports: set[str],
    blocks: list[Block],
    max_depth: int = MAX_DEPTH,
) -> list[Block]:
    """The methods that could have produced these ports. Coarse and backward.

    Empty `fail_ports`, or ports nothing supplies, returns EVERYTHING. A slice
    that could not be computed must never be mistaken for a slice that is empty,
    or the agent is told there is nothing to read.
    """
    if not fail_ports or not blocks:
        return list(blocks)
    by_name = {b.name: b for b in blocks}
    drivers = build_driver_map(blocks)

    seen: dict[str, Block] = {}
    frontier: set[str] = set()   # attributes still to trace back
    pending: set[str] = set()    # methods on the port's path, to expand

    for b in blocks:
        for port, sources in b.supplies.items():
            if port not in fail_ports:
                continue
            # The method that writes the port is in the slice, but its OTHER
            # calls are not followed: a `_write_outputs` supplying all eight
            # ports calls whatever any of them needs, and following all of it
            # from one failing port pulls in the whole model. Measured: doing so
            # took `cmd_ack` from 6 methods to 11 of 11.
            seen[b.name] = b
            for src in sources:
                (pending if src in by_name else frontier).add(src)

    for _ in range(max(1, max_depth)):
        nxt: set[str] = set()
        # Calls are followed only from methods NAMED as supplying this port, and
        # transitively from those. That is the path the value actually took --
        # `o['scl_oen'] = self.mask(scl_oen, 1)` with `scl_oen` bound from
        # `self._state_outputs()` -- and it is the edge `trace_slicer` has no
        # need of, because Verilog blocks do not invoke one another.
        while pending:
            name = pending.pop()
            block = by_name.get(name)
            if block is None or name in seen:
                continue
            seen[name] = block
            nxt |= set(block.reads)
            pending |= {c for c in block.calls if c in by_name and c not in seen}
        # Attribute drivers contribute their READS, not their calls: reaching a
        # method because it assigns an attribute says nothing about why it calls
        # what it calls.
        for attr in frontier:
            for block in drivers.get(attr, []):
                if block.name in seen:
                    continue
                seen[block.name] = block
                nxt |= set(block.reads)
        frontier = nxt
        if not frontier and not pending:
            break
    return sorted(seen.values(), key=lambda b: b.start_line) or list(blocks)
