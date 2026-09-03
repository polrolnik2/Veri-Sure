"""How many derivation steps separate an input port from what the spec talks about?

Not "how big is the design". The question is how far the specification's own
vocabulary sits from the boundary an oracle is allowed to read, because that
distance is exactly what the author has to reconstruct from prose.

Depth 0 is an input port; a signal is one deeper than the shallowest thing it
depends on. Dependence is CONTROL AS WELL AS DATA -- every signal named in an
enclosing `if`/`case` condition counts, because a state machine's dependency on
its guards is the whole of what makes it hard to re-derive, and a data-only
graph would score an FSM as shallow while its author drowns.
"""
import re
from collections import defaultdict
from pathlib import Path

KW = {"begin", "end", "if", "else", "case", "casex", "casez", "endcase", "posedge",
      "negedge", "or", "and", "not", "always", "assign", "reg", "wire", "input",
      "output", "inout", "parameter", "localparam", "module", "endmodule",
      "default", "integer", "signed", "function", "endfunction", "genvar",
      "generate", "endgenerate", "initial", "forever", "repeat", "while", "for"}


#: Compiler directives, whose whole line is noise.
_DIRECTIVE = re.compile(
    r"^[ \t]*`(?:include|define|undef|ifdef|ifndef|elsif|else|endif|timescale"
    r"|default_nettype|line|celldefine|endcelldefine|resetall|unconnected_drive"
    r"|nounconnected_drive)\b[^\n]*", re.M)


def strip(text):
    """Comments and directives out; macro USAGES kept as plain identifiers.

    Deleting from a backtick to end of line -- the obvious reading of "drop the
    preprocessor" -- silently eats the body of any statement that mentions a
    macro. or1200_dc_fsm compares `state` against `OR1200_DCFSM_* constants in
    almost every branch, so that reading removed the entire FSM and scored three
    driven outputs as having no source at all. i2c's bit_ctrl uses `parameter`
    for its states and never exposed it.
    """
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.S)
    text = re.sub(r"//[^\n]*", " ", text)
    text = _DIRECTIVE.sub(" ", text)
    return re.sub(r"`(\w+)", r"\1", text)


def macros(text):
    """Names used as `MACRO -- constants, not signals, so not dependencies."""
    return set(re.findall(r"`(\w+)", text))


def ports(text):
    """Both declaration styles: ANSI inside the header, and bare `input x;`."""
    ins, outs = set(), set()
    head = re.search(r"\bmodule\s+\w+\s*\((.*?)\)\s*;", text, re.S)
    if head:
        cur = None
        for item in head.group(1).split(","):
            m = re.match(r"\s*\b(input|output|inout)\b", item)
            if m:
                cur = m.group(1)
            body = re.sub(r"\[[^\]]*\]", " ", item)
            names = [n for n in re.findall(r"\b[A-Za-z_]\w*\b", body)
                     if n not in {"input", "output", "inout", "reg", "wire", "signed",
                                  "logic"}]
            if cur and names:
                (ins if cur == "input" else outs).add(names[-1])
    body = text[head.end():] if head else text
    for m in re.finditer(r"\b(input|output|inout)\b([^;()]*);", body):
        names = [n for n in re.findall(r"\b[A-Za-z_]\w*\b",
                                       re.sub(r"\[[^\]]*\]", " ", m.group(2)))
                 if n not in {"reg", "wire", "signed", "logic"}]
        (ins if m.group(1) == "input" else outs).update(names)
    return ins, outs


def params(text):
    return set(re.findall(r"\b(?:parameter|localparam)\s*(?:\[[^\]]*\])?\s*(\w+)", text))


def idents(expr):
    expr = re.sub(r"\b\d+\s*'\s*[bhdo]?[0-9a-fA-FxzXZ_]+", " ", expr)
    return {t for t in re.findall(r"\b[A-Za-z_]\w*\b", expr) if t not in KW}


def _blocks(text):
    """(condition-identifiers, assignment-pairs) per always block, plus assigns."""
    out = []
    for m in re.finditer(r"\bassign\s+([A-Za-z_]\w*)[^=]*?=\s*([^;]+);", text):
        out.append((set(), [(m.group(1), m.group(2))]))
    starts = [m.start() for m in re.finditer(r"\balways\b", text)]
    for i, s in enumerate(starts):
        blk = text[s:starts[i + 1] if i + 1 < len(starts) else len(text)]
        blk = re.split(r"\bendmodule\b", blk)[0]
        cond = set()
        for c in re.findall(r"\bif\s*\(([^;]*?)\)", blk) + \
                 re.findall(r"\bcase[xz]?\s*\(([^)]*)\)", blk):
            cond |= idents(c)
        # the sensitivity list carries no dependence beyond its own signals
        sens = re.match(r"\balways\s*@\s*\(([^)]*)\)", blk)
        if sens:
            cond |= idents(re.sub(r"\b(pos|neg)edge\b", " ", sens.group(1)))
        pairs = re.findall(r"\b([A-Za-z_]\w*)\s*(?:\[[^\]]*\])?\s*<=\s*(?:#\s*\d+\s*)?([^;]+);",
                           blk)
        pairs += [(a, b) for a, b in
                  re.findall(r"\b([A-Za-z_]\w*)\s*(?:\[[^\]]*\])?\s*=(?!=)\s*([^;]+);", blk)]
        out.append((cond, pairs))
    return out


def deps(text, drop=()):
    g = defaultdict(set)
    for cond, pairs in _blocks(text):
        for lhs, rhs in pairs:
            g[lhs] |= (cond | idents(rhs)) - {lhs} - set(drop)
    return g


def instance_edges(text, child_ins, child_outs):
    """A child instance, black-boxed: each child output depends on each child input."""
    g = defaultdict(set)
    for inst in re.finditer(r"\b\w+\s+\w+\s*\(((?:\s*\.\s*\w+\s*\([^)]*\)\s*,?)+)\s*\)\s*;",
                            text):
        conns = {m.group(1): m.group(2).strip()
                 for m in re.finditer(r"\.\s*(\w+)\s*\(\s*([^)]*?)\s*\)", inst.group(1))}
        src = {conns[p] for p in child_ins if conns.get(p)}
        for p in child_outs:
            if conns.get(p):
                g[conns[p]] |= src
    return g


def depths(g, roots):
    d = {r: 0 for r in roots}
    changed = True
    while changed:
        changed = False
        for sig, srcs in g.items():
            cand = [d[s] for s in srcs if s in d]
            if not cand:
                continue
            v = min(cand) + 1
            if d.get(sig, 1 << 30) > v:
                d[sig] = v
                changed = True
    for sig in g:
        d.setdefault(sig, None)
    return d


def _sccs(nodes, succ):
    """Tarjan. A mutually recursive group -- an FSM's state registers -- is ONE
    concept to re-derive, not a chain, so it must collapse to a single node or
    every state machine reads as infinitely deep."""
    index, low, on, stack, out, counter = {}, {}, set(), [], [], [0]

    def go(v):
        work = [(v, iter(succ.get(v, ())))]
        index[v] = low[v] = counter[0]
        counter[0] += 1
        stack.append(v)
        on.add(v)
        while work:
            u, it = work[-1]
            for w in it:
                if w not in nodes:
                    continue
                if w not in index:
                    index[w] = low[w] = counter[0]
                    counter[0] += 1
                    stack.append(w)
                    on.add(w)
                    work.append((w, iter(succ.get(w, ()))))
                    break
                if w in on:
                    low[u] = min(low[u], index[w])
            else:
                work.pop()
                if work:
                    low[work[-1][0]] = min(low[work[-1][0]], low[u])
                if low[u] == index[u]:
                    comp = []
                    while True:
                        w = stack.pop()
                        on.discard(w)
                        comp.append(w)
                        if w == u:
                            break
                    out.append(comp)
    for v in nodes:
        if v not in index:
            go(v)
    return out


def internal_depth(g, ins, outs, consts=()):
    """Longest chain of INTERNAL derivation a signal rests on.

    0 means every source is a port or a constant -- one step from the boundary.
    N means N intermediate concepts, none of them observable, stand between the
    port an oracle may read and the thing the requirement names.
    """
    skip = set(ins) | set(consts)
    internal = {s for s in g if s not in ins and s not in outs}
    succ = {s: {x for x in g[s] if x in internal} for s in g}
    comp_of, comps = {}, _sccs(set(g), succ)
    for i, c in enumerate(comps):
        for s in c:
            comp_of[s] = i
    memo = {}

    def dep(i):
        if i in memo:
            return memo[i]
        memo[i] = 0                                   # guard against re-entry
        best = 0
        for s in comps[i]:
            for src in g.get(s, ()):
                if src in skip or src not in comp_of:
                    continue
                if comp_of[src] == i:
                    continue
                if src in internal:
                    best = max(best, dep(comp_of[src]) + 1)
                else:
                    best = max(best, dep(comp_of[src]))
        memo[i] = best
        return best

    return {s: dep(comp_of[s]) for s in g if s in comp_of}


def analyse(text, extra=None):
    """(depth per signal, components, component id) for one module's text.

    Depth counts derivation steps from the ports; a mutually recursive group is
    ONE step, because re-deriving it is one problem and not a chain. That
    distinction is the whole point: a deep FEED-FORWARD chain can be handed to
    an oracle author by the testbench, and a cycle cannot be, because computing
    it from inputs alone means re-implementing the design.
    """
    P = params(text)
    g = deps(text, drop=P)
    for p in P:
        g.pop(p, None)                          # a constant is not a derivation
    if extra:
        for k, v in extra.items():
            g[k] |= v
    nodes = set(g)
    succ = {v: {s for s in g[v] if s in nodes} for v in nodes}
    comps = _sccs(nodes, succ)
    cid = {s: i for i, c in enumerate(comps) for s in c}
    cedge = defaultdict(set)
    for v in nodes:
        for s in succ[v]:
            if cid[s] != cid[v]:
                cedge[cid[v]].add(cid[s])
    memo = {}

    def d(i):
        if i in memo:
            return memo[i]
        memo[i] = 0
        memo[i] = 1 + max((d(j) for j in cedge[i]), default=-1)
        return memo[i]

    return {s: d(cid[s]) for s in nodes}, comps, cid


def declared(text, ins, outs):
    noise = {"input", "output", "inout", "reg", "wire", "signed", "logic"}
    out = set()
    for m in re.finditer(r"\b(?:reg|wire)\b\s*(?:\[[^\]]*\])?\s*([^;]+);", text):
        out |= set(re.findall(r"\b[A-Za-z_]\w*\b", m.group(1)))
    return (out | params(text)) - set(ins) - set(outs) - noise


def report(name, rtl_path, spec_path, child=None):
    import collections
    text = strip(Path(rtl_path).read_text())
    ins, outs = ports(text)
    extra = None
    if child:
        ctext = strip(Path(child).read_text())
        ci, co = ports(ctext)
        extra = instance_edges(text, ci, co)
    d, comps, _cid = analyse(text, extra)
    internal = declared(text, ins, outs)
    words = collections.Counter(
        re.findall(r"\b[A-Za-z_]\w*\b", Path(spec_path).read_text()))
    named = sorted(((k, v) for k, v in words.items() if k in internal),
                   key=lambda x: -x[1])
    pm = sum(v for k, v in words.items() if k in (ins | outs))
    im = sum(v for _k, v in named)
    core = max(comps, key=len)
    inside = sum(v for k, v in named if k in core)
    print(f"\n== {name}   {len(ins | outs)} ports, {len(internal)} internals, "
          f"max depth {max(d.values())}")
    print(f"   largest mutually recursive group: {len(core)} signals")
    print(f"   spec names ports {pm}x, internals {im}x "
          f"({im / max(1, pm + im):.0%} internal)")
    print(f"   of those internal mentions, {inside}/{im} = "
          f"{inside / max(1, im):.0%} sit INSIDE the recursive core")
    print("   internal, as named by the spec        mentions  depth")
    for k, v in named[:12]:
        dep = d.get(k)
        tag = "   <- recursive core" if k in core else ""
        print(f"     {k:<32} {v:>6}   {dep if dep is not None else '-'}{tag}")


if __name__ == "__main__":
    R = Path("benchmarks/chipverilog/Src/i2c/rtl/verilog")
    D = Path("benchmarks/chipverilog/Des/i2c")
    report("i2c_master_bit_ctrl", R / "i2c_master_bit_ctrl.v",
           D / "i2c_master_bit_ctrl/description.txt")
    report("i2c_master_byte_ctrl (child black-boxed)",
           R / "i2c_master_byte_ctrl.v",
           D / "i2c_master_byte_ctrl/description.txt",
           child=R / "i2c_master_bit_ctrl.v")
