from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, Iterable, Literal, Set

try:  # optional runtime dependency (preferred)
    from tree_sitter import Language, Parser  # type: ignore[import-not-found]
    import tree_sitter_verilog as _ts_verilog  # type: ignore[import-not-found]
except Exception:  # noqa: BLE001
    Language = None  # type: ignore[assignment]
    Parser = None  # type: ignore[assignment]
    _ts_verilog = None  # type: ignore[assignment]


_KEYWORDS: Set[str] = {
    # SystemVerilog keywords / common tokens
    "module",
    "endmodule",
    "input",
    "output",
    "inout",
    "wire",
    "logic",
    "reg",
    "bit",
    "int",
    "integer",
    "parameter",
    "localparam",
    "typedef",
    "struct",
    "packed",
    "always",
    "always_ff",
    "always_comb",
    "always_latch",
    "assign",
    "begin",
    "end",
    "if",
    "else",
    "case",
    "casez",
    "casex",
    "endcase",
    "for",
    "foreach",
    "while",
    "do",
    "repeat",
    "return",
    "break",
    "continue",
    "default",
    "unique",
    "unique0",
    "priority",
    "posedge",
    "negedge",
    "or",
    "and",
    "not",
    "initial",
    "generate",
    "endgenerate",
    "function",
    "endfunction",
    "task",
    "endtask",
    "genvar",
    "signed",
    "unsigned",
    "always@",
}


def _strip_comments_keep_lines(text: str) -> str:
    """Remove // and /* */ comments while preserving newlines."""
    out: list[str] = []
    i = 0
    n = len(text)
    in_block = False
    while i < n:
        ch = text[i]
        nxt = text[i + 1] if i + 1 < n else ""
        if in_block:
            if ch == "*" and nxt == "/":
                in_block = False
                out.append("  ")
                i += 2
                continue
            if ch == "\n":
                out.append("\n")
            else:
                out.append(" ")
            i += 1
            continue

        if ch == "/" and nxt == "/":
            # line comment: skip to newline
            out.append("  ")
            i += 2
            while i < n and text[i] != "\n":
                out.append(" ")
                i += 1
            continue
        if ch == "/" and nxt == "*":
            in_block = True
            out.append("  ")
            i += 2
            continue

        out.append(ch)
        i += 1
    return "".join(out)


_ATTR_PREFIX = r"(?:\(\*.*?\*\)\s*)*"
_ALWAYS_RE = re.compile(rf"^\s*{_ATTR_PREFIX}(always_ff|always_comb|always_latch|always)\b")
_ASSIGN_RE = re.compile(rf"^\s*{_ATTR_PREFIX}assign\b")


@dataclass(frozen=True)
class RtlBlock:
    id: str
    kind: Literal["always", "assign"]
    start_line: int
    end_line: int
    clocking: str
    code: str
    writes: tuple[str, ...]
    reads: tuple[str, ...]


def _count_word(line: str, word: str) -> int:
    return len(re.findall(rf"\b{re.escape(word)}\b", line))


def _extract_idents(text: str) -> Set[str]:
    idents = set(re.findall(r"\b[a-zA-Z_][a-zA-Z0-9_]*\b", text))
    return {x for x in idents if x not in _KEYWORDS}


def _extract_writes(code: str) -> Set[str]:
    # Heuristic: capture "lhs <=" and "lhs =" occurrences.
    writes: Set[str] = set()
    for m in re.finditer(r"\b([a-zA-Z_][a-zA-Z0-9_]*)\b\s*(?:\[[^\]]+\])?\s*<=", code):
        writes.add(m.group(1))
    for m in re.finditer(r"\b([a-zA-Z_][a-zA-Z0-9_]*)\b\s*(?:\[[^\]]+\])?\s*(?<![=!<>])=(?![=])", code):
        writes.add(m.group(1))
    return writes


def _classify_clocking(header: str) -> str:
    header = " ".join(header.strip().split())
    if "always_comb" in header or "@(*)" in header or "@ *" in header:
        return "comb"
    if "posedge" in header or "negedge" in header:
        return "seq"
    if header.startswith("always_latch"):
        return "latch"
    return "unknown"


def _find_statement_end(lines: list[str], start: int) -> int:
    for j in range(start, len(lines)):
        if ";" in lines[j]:
            return j
    return len(lines) - 1


def _find_always_end(lines: list[str], start: int) -> int:
    seen_begin = False
    depth = 0
    for j in range(start, len(lines)):
        line = lines[j]
        b = _count_word(line, "begin")
        e = _count_word(line, "end")
        if b:
            seen_begin = True
        depth += b
        depth -= e

        if seen_begin:
            if depth == 0:
                return j
        else:
            if ";" in line:
                return j
    return len(lines) - 1


def parse_rtl_blocks(rtl_text: str) -> list[RtlBlock]:
    """Parse RTL into coarse always/assign blocks with read/write sets.

    Preferred implementation uses tree-sitter-verilog (AST-based) for more accurate
    block boundaries and read/write extraction. Falls back to a heuristic parser
    if tree-sitter isn't available.
    """
    if Parser is None or Language is None or _ts_verilog is None:
        return _parse_rtl_blocks_heuristic(rtl_text)

    try:
        blocks = _parse_rtl_blocks_treesitter(rtl_text)
        if blocks:
            return blocks
    except Exception:  # noqa: BLE001
        # Keep the system usable even if parsing fails.
        pass

    return _parse_rtl_blocks_heuristic(rtl_text)


def _parse_rtl_blocks_heuristic(rtl_text: str) -> list[RtlBlock]:
    """Heuristic fallback parser (regex-based)."""
    clean = _strip_comments_keep_lines(rtl_text)
    raw_lines = rtl_text.splitlines()
    clean_lines = clean.splitlines()

    blocks: list[RtlBlock] = []
    always_idx = 0
    assign_idx = 0
    i = 0
    while i < len(clean_lines):
        line = clean_lines[i]
        if _ALWAYS_RE.match(line):
            always_idx += 1
            end = _find_always_end(clean_lines, i)
            code = "\n".join(raw_lines[i : end + 1]) + "\n"
            header = raw_lines[i]
            clocking = _classify_clocking(header)
            writes = _extract_writes("\n".join(clean_lines[i : end + 1]))
            reads = _extract_idents("\n".join(clean_lines[i : end + 1])) - writes
            block = RtlBlock(
                id=f"A{always_idx}",
                kind="always",
                start_line=i + 1,
                end_line=end + 1,
                clocking=clocking,
                code=code,
                writes=tuple(sorted(writes)),
                reads=tuple(sorted(reads)),
            )
            blocks.append(block)
            i = end + 1
            continue

        if _ASSIGN_RE.match(line):
            assign_idx += 1
            end = _find_statement_end(clean_lines, i)
            code = "\n".join(raw_lines[i : end + 1]) + "\n"
            writes = _extract_writes("\n".join(clean_lines[i : end + 1]))
            reads = _extract_idents("\n".join(clean_lines[i : end + 1])) - writes
            block = RtlBlock(
                id=f"C{assign_idx}",
                kind="assign",
                start_line=i + 1,
                end_line=end + 1,
                clocking="comb",
                code=code,
                writes=tuple(sorted(writes)),
                reads=tuple(sorted(reads)),
            )
            blocks.append(block)
            i = end + 1
            continue

        i += 1

    if not blocks:
        pseudo = _make_pseudo_module_body_block(rtl_text)
        if pseudo is not None:
            return [pseudo]

    return blocks


_TS_LANGUAGE: Language | None = None  # type: ignore[valid-type]
_TS_PARSER: Parser | None = None  # type: ignore[valid-type]


def _get_ts_parser() -> Parser:  # type: ignore[valid-type]
    global _TS_LANGUAGE, _TS_PARSER
    if _TS_PARSER is not None:
        return _TS_PARSER

    assert Parser is not None and Language is not None and _ts_verilog is not None
    _TS_LANGUAGE = Language(_ts_verilog.language())
    _TS_PARSER = Parser()
    _TS_PARSER.language = _TS_LANGUAGE
    return _TS_PARSER


def _node_text(source: bytes, node: object) -> str:
    start = getattr(node, "start_byte")
    end = getattr(node, "end_byte")
    return source[start:end].decode("utf-8", errors="replace")


def _iter_descendants(node: object) -> Iterable[object]:
    stack = [node]
    while stack:
        cur = stack.pop()
        yield cur
        children = getattr(cur, "children", None)
        if children:
            stack.extend(reversed(children))


def _find_first_desc(node: object, typ: str) -> object | None:
    for n in _iter_descendants(node):
        if getattr(n, "type", None) == typ:
            return n
    return None


def _find_all_desc(node: object, typ: str) -> list[object]:
    return [n for n in _iter_descendants(node) if getattr(n, "type", None) == typ]


def _module_name(source: bytes, module_decl: object) -> str | None:
    header = None
    for c in getattr(module_decl, "children", []):
        if getattr(c, "type", None) == "module_header":
            header = c
            break
    if header is None:
        return None
    ident = _find_first_desc(header, "simple_identifier")
    if ident is None:
        return None
    return _node_text(source, ident).strip()


_IDENT_NODE_TYPES = {"simple_identifier", "escaped_identifier"}
_LVALUE_NODE_TYPES = {"variable_lvalue", "net_lvalue"}


def _collect_idents(source: bytes, node: object, *, skip_lvalues: bool) -> Set[str]:
    idents: Set[str] = set()

    def walk(n: object, in_lvalue: bool) -> None:
        ntype = getattr(n, "type", "")
        if ntype in _IDENT_NODE_TYPES and not (skip_lvalues and in_lvalue):
            idents.add(_node_text(source, n).lstrip("\\"))

        next_in_lvalue = in_lvalue or (ntype in _LVALUE_NODE_TYPES)
        for ch in getattr(n, "children", []):
            walk(ch, next_in_lvalue)

    walk(node, False)
    return {x for x in idents if x and x not in _KEYWORDS}


def _collect_writes(source: bytes, block_node: object) -> Set[str]:
    writes: Set[str] = set()

    # Continuous assignment targets.
    for na in _find_all_desc(block_node, "net_assignment"):
        lval = _find_first_desc(na, "net_lvalue")
        if lval is not None:
            writes |= _collect_idents(source, lval, skip_lvalues=False)

    # Procedural assignment targets.
    for an in _find_all_desc(block_node, "nonblocking_assignment") + _find_all_desc(block_node, "blocking_assignment"):
        lval = _find_first_desc(an, "variable_lvalue")
        if lval is not None:
            writes |= _collect_idents(source, lval, skip_lvalues=False)

    return writes


def _classify_clocking_ts(source: bytes, always_node: object) -> str:
    kw = _find_first_desc(always_node, "always_keyword")
    kw_text = _node_text(source, kw).strip() if kw is not None else ""
    if kw_text == "always_comb":
        return "comb"
    if kw_text == "always_latch":
        return "latch"
    if kw_text in {"always_ff", "always"}:
        # Look for explicit edge triggers.
        if _find_first_desc(always_node, "edge_identifier") is not None:
            return "seq"
        # Detect @(*) / @* via event_control containing '*' token.
        for ec in _find_all_desc(always_node, "event_control"):
            for ch in getattr(ec, "children", []):
                if getattr(ch, "type", None) == "*":
                    return "comb"
        return "unknown"
    return "unknown"


def _parse_rtl_blocks_treesitter(rtl_text: str) -> list[RtlBlock]:
    source = rtl_text.encode("utf-8", errors="replace")
    parser = _get_ts_parser()
    tree = parser.parse(source)
    root = tree.root_node

    modules = _find_all_desc(root, "module_declaration")
    if not modules:
        return []

    chosen = None
    for m in modules:
        if _module_name(source, m) == "TopModule":
            chosen = m
            break
    if chosen is None:
        chosen = modules[0]

    always_nodes = _find_all_desc(chosen, "always_construct")
    assign_nodes = _find_all_desc(chosen, "continuous_assign")

    items: list[tuple[int, str, object]] = []
    for n in always_nodes:
        items.append((getattr(n, "start_byte"), "always", n))
    for n in assign_nodes:
        items.append((getattr(n, "start_byte"), "assign", n))
    items.sort(key=lambda x: x[0])

    blocks: list[RtlBlock] = []
    always_idx = 0
    assign_idx = 0
    for _pos, kind, node in items:
        start_line = getattr(node, "start_point").row + 1
        end_line = getattr(node, "end_point").row + 1
        code = _node_text(source, node)
        if not code.endswith("\n"):
            code += "\n"

        if kind == "always":
            always_idx += 1
            clocking = _classify_clocking_ts(source, node)
            writes = _collect_writes(source, node)
            reads = _collect_idents(source, node, skip_lvalues=True)
            blocks.append(
                RtlBlock(
                    id=f"A{always_idx}",
                    kind="always",
                    start_line=start_line,
                    end_line=end_line,
                    clocking=clocking,
                    code=code,
                    writes=tuple(sorted(writes)),
                    reads=tuple(sorted(reads)),
                )
            )
        else:
            assign_idx += 1
            writes = _collect_writes(source, node)
            reads = _collect_idents(source, node, skip_lvalues=True)
            blocks.append(
                RtlBlock(
                    id=f"C{assign_idx}",
                    kind="assign",
                    start_line=start_line,
                    end_line=end_line,
                    clocking="comb",
                    code=code,
                    writes=tuple(sorted(writes)),
                    reads=tuple(sorted(reads)),
                )
            )

    if not blocks:
        pseudo = _make_pseudo_module_body_block_from_ts(source, chosen)
        if pseudo is not None:
            return [pseudo]

    return blocks


def _make_pseudo_module_body_block(rtl_text: str) -> RtlBlock | None:
    """Fallback: create a single "body" block when no always/assign blocks are found."""
    lines = rtl_text.splitlines()
    if not lines:
        return None

    start_mod = None
    for i, line in enumerate(lines):
        if re.search(rf"^\s*{_ATTR_PREFIX}module\s+TopModule\b", line):
            start_mod = i
            break
    if start_mod is None:
        for i, line in enumerate(lines):
            if re.search(rf"^\s*{_ATTR_PREFIX}module\b", line):
                start_mod = i
                break
    if start_mod is None:
        return None

    end_mod = None
    for j in range(start_mod + 1, len(lines)):
        if re.search(r"^\s*endmodule\b", lines[j]):
            end_mod = j
            break
    if end_mod is None:
        end_mod = len(lines) - 1

    header_end = start_mod
    for j in range(start_mod, end_mod + 1):
        if ";" in lines[j]:
            header_end = j
            break

    body_start = min(header_end + 1, end_mod)
    body_end = max(body_start, end_mod - 1)

    code = "\n".join(lines[body_start : body_end + 1]) + "\n"
    return RtlBlock(
        id="A1",
        kind="always",
        start_line=body_start + 1,
        end_line=body_end + 1,
        clocking="unknown",
        code=code,
        writes=tuple(),
        reads=tuple(),
    )


def _make_pseudo_module_body_block_from_ts(source: bytes, module_decl: object) -> RtlBlock | None:
    # Find the semicolon that ends the module header (usually a direct child).
    header_end_row = getattr(module_decl, "start_point").row
    endmodule_row = getattr(module_decl, "end_point").row

    semis = [c for c in getattr(module_decl, "children", []) if getattr(c, "type", None) == ";"]
    if semis:
        header_end_row = semis[0].end_point.row

    endmods = [c for c in getattr(module_decl, "children", []) if getattr(c, "type", None) == "endmodule"]
    if endmods:
        endmodule_row = endmods[0].start_point.row

    body_start_row = min(header_end_row + 1, endmodule_row)
    body_end_row = max(body_start_row, endmodule_row - 1)

    text = source.decode("utf-8", errors="replace").splitlines()
    if not text:
        return None
    if body_start_row >= len(text):
        body_start_row = max(0, len(text) - 1)
    if body_end_row >= len(text):
        body_end_row = len(text) - 1

    code = "\n".join(text[body_start_row : body_end_row + 1]) + "\n"
    return RtlBlock(
        id="A1",
        kind="always",
        start_line=body_start_row + 1,
        end_line=body_end_row + 1,
        clocking="unknown",
        code=code,
        writes=tuple(),
        reads=tuple(),
    )


def build_driver_map(blocks: Iterable[RtlBlock]) -> Dict[str, list[RtlBlock]]:
    drivers: Dict[str, list[RtlBlock]] = {}
    for b in blocks:
        for w in b.writes:
            drivers.setdefault(w, []).append(b)
    return drivers


def dynamic_slice(
    *,
    fail_signals: Iterable[str],
    drivers: Dict[str, list[RtlBlock]],
    max_depth: int = 3,
) -> list[RtlBlock]:
    """Coarse backward slice from fail signals via driver graph."""
    frontier = set(fail_signals)
    seen_signals = set(frontier)
    seen_blocks: dict[str, RtlBlock] = {}

    for _ in range(max(1, max_depth)):
        next_frontier: Set[str] = set()
        for sig in frontier:
            for block in drivers.get(sig, []):
                seen_blocks[block.id] = block
                for r in block.reads:
                    if r not in seen_signals:
                        seen_signals.add(r)
                        next_frontier.add(r)
        frontier = next_frontier
        if not frontier:
            break

    return list(seen_blocks.values())
