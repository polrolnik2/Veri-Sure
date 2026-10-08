#!/usr/bin/env python3
"""Present a hierarchical task's spec with its CHILD-FACING PORTS on the header.

A parent module that instantiates a child has two readings. As a *wrapper* it
must reimplement everything the child does, and the generated RTL is graded on
behaviour it was never given. As *glue* the child is an external, already
discharged component, and what is graded is the composition -- which is what
the parent's specification actually describes.

Only one thing separates the two, and it is the module header. If the child's
boundary appears on it, the child is outside; if it does not, the child is
inside and has to be rebuilt. So this module extends the prototype the
architect is shown, and nothing else changes: contract generation, S1, the
oracle stage and both arms run exactly as they do on a leaf.

**NO GLUE PROSE IS ADDED, deliberately.** `eda_agent` carries a full glue
vocabulary -- `GLUE_SYSTEM_PROMPT`, the four-shot examples, the vestigial-glue
rejection -- and every bit of it switches on `child_assumes` being present in
the contract (`_is_composition_contract`). Nothing here writes that field, so
none of it engages. These two specifications already describe their glue
logic in their own words: or1200_sb declares `fifo_wr`, `fifo_rd`, `fifo_full`,
`fifo_empty` and both FIFO data buses in its own internal-signal list and
explains `sel_sb`, `outstanding_store` and `fifo_wr_ack` without reference to
the FIFO's internals, and i2c_master_byte_ctrl names `core_cmd`, `core_ack`,
`core_txd` and `core_rxd` and states outright that it "does not directly
implement the concrete START or STOP waveforms". Adding glue instruction on
top would confound the experiment: a result would no longer say whether the
PORTS were what mattered.

**WHERE THE FACTS COME FROM, and why that ordering is the point.** The
declarations in `benchmarks/glue/<parent>.json` are written from the
SPECIFICATION, which names every child-facing net; widths come from the child's
own header, which is a discharged component and legitimately known. The
parent's implementation is not consulted to author them. `--check` then reads
that implementation and reports agreement -- an audit, never a source. This is
the same split the project uses between control and witness: the stronger
evidence checks the claim, and is not allowed to write it.

The clock and reset ports are excluded and named in `shared_domain`. The child
sits in the parent's clock domain by construction, and a glue module driving
its child's clock through a port is not a composition decision -- it is a
structural given, and `build_mock_dut` would randomise it as a glue output.

Usage
-----
    python benchmarks/glue_spec.py --task i2c_master_byte_ctrl --check
    python benchmarks/glue_spec.py --task or1200_sb --emit benchmarks/glue/tasks
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import shutil
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
DES = REPO_ROOT / "benchmarks" / "chipverilog" / "Des"
DECLS = REPO_ROOT / "benchmarks" / "glue"


def find_task(name: str) -> pathlib.Path:
    hits = [p.parent for p in DES.rglob("description.txt") if p.parent.name == name]
    if not hits:
        raise SystemExit(f"no ChipVerilog task named {name!r} under {DES}")
    return hits[0]


def load_decl(parent: str) -> dict:
    path = DECLS / f"{parent}.json"
    if not path.is_file():
        raise SystemExit(f"no child-facing declaration at {path}")
    decl = json.loads(path.read_text(encoding="utf-8"))
    seen: set[str] = set()
    for port in decl.get("ports", []):
        for key in ("child", "glue", "dir", "width", "parent_net"):
            if key not in port:
                raise SystemExit(f"{path}: port {port} is missing {key!r}")
        if port["dir"] not in ("input", "output"):
            raise SystemExit(f"{path}: {port['glue']} has dir {port['dir']!r}")
        if port["glue"] in seen:
            raise SystemExit(f"{path}: duplicate glue port {port['glue']!r}")
        seen.add(port["glue"])
    return decl


# --------------------------------------------------------------- rendering
def _width_text(width: int) -> str:
    return f"[{int(width) - 1}:0]" if int(width) > 1 else ""


_PROTO = re.compile(r"(module\s+(?P<name>\w+)\s*\()(?P<body>[^;]*?)(\)\s*;)", re.S)

#: A direction keyword already inside the prototype body means the header is
#: ANSI-style.
_ANSI = re.compile(r"^\s*(?:input|output|inout)\b", re.M)


def _extend_prototype(spec: str, parent: str, ports: list[dict]) -> tuple[str, int]:
    """Splice the child-facing ports in, IN THE HEADER'S OWN STYLE.

    These two specs write their prototype differently. i2c_master_byte_ctrl
    uses a bare name list -- `module m ( a, b, c );` -- and carries directions
    in the port table below. or1200_sb uses an ANSI header that declares each
    direction and width inline.

    Appending bare names to an ANSI header would leave one prototype written
    in two styles, and the architect would then have 22 ports whose direction
    the header states and 6 whose direction it does not, in the same list. That
    is the same hazard as a spec whose `output` keywords were stripped -- the
    one that has already cost this project four ports on a run -- manufactured
    deliberately. So the style is detected and matched.
    """
    hits = 0

    def _sub(m: re.Match) -> str:
        nonlocal hits
        if m.group("name") != parent:
            return m.group(0)
        hits += 1
        body = m.group("body").rstrip()
        sep = "," if body.strip() else ""
        if _ANSI.search(body):
            decls = [
                f"    {p['dir']}{(' ' + _width_text(p['width'])) if int(p['width']) > 1 else ''} {p['glue']}"
                for p in ports
            ]
            added = "\n\n    // child-facing\n" + ",\n".join(decls) + "\n"
        else:
            added = ("\n\t// child-facing\n\t"
                     + ", ".join(p["glue"] for p in ports) + " ")
        return m.group(1) + body + sep + added + m.group(4)

    return _PROTO.sub(_sub, spec), hits


#: A line in the spec's "Internal reg/wire signals" block, e.g.
#: `    wire [67:0] fifo_dat_i: Fifo data input.`
#: The optional `[67:0]` range must be matched explicitly, NOT skipped with a
#: "anything but a colon" run -- the range contains one, so that spelling
#: silently kept every vectored net in the internal list while removing the
#: scalars. Found by reading the rendered output rather than the regex.
_INTERNAL_DECL = re.compile(
    r"^[ \t]*(?:wire|reg)\b(?:\s*\[[^\]]*\])?\s+(?P<net>\w+)\s*:.*$", re.M)


def _promote_internals(spec: str, decl: dict) -> tuple[str, list[tuple[str, str]]]:
    """Drop promoted nets from the internal-signal list, and say which.

    or1200_sb declares `fifo_dat_i`, `fifo_wr`, `fifo_rd`, `fifo_full` and
    `fifo_empty` under "Internal reg/wire signals". Once the child's boundary
    is on the header those are PORTS, and leaving both statements in place
    hands the architect a header and a signal list that contradict each other
    -- the same two-readings hazard that makes a stripped `output` keyword
    cost four ports a run.

    The line is removed rather than reworded, and the promotion is reported in
    the child-facing block instead, so the mapping stays visible in exactly one
    place. Silent deletion is the thing to avoid, not deletion.
    """
    promoted = {p["parent_net"]: p["glue"] for p in decl["ports"]}
    moved: list[tuple[str, str]] = []

    def _sub(m: re.Match) -> str:
        net = m.group("net")
        if net in promoted:
            moved.append((net, promoted[net]))
            return "\x00"          # marked, stripped below with its newline
        return m.group(0)

    out = _INTERNAL_DECL.sub(_sub, spec)
    out = re.sub(r"\x00\n?", "", out)
    return out, moved


def render(spec: str, decl: dict) -> str:
    """The spec, with the child boundary on the header and in a port table.

    The appended block states names, widths and directions and NOTHING about
    what glue is or how to write it. Every sentence in it is a fact about the
    interface; the behaviour is already in the specification's own prose.
    """
    parent = decl["parent"]
    ports = decl["ports"]
    spec, moved = _promote_internals(spec, decl)
    out, hits = _extend_prototype(spec, parent, ports)
    if hits != 1:
        raise SystemExit(
            f"expected exactly one `module {parent} (` prototype in the spec, "
            f"found {hits}; the header was not extended and the spec would be "
            f"shipped unchanged, which is silently the wrapper reading")

    ins = [p for p in ports if p["dir"] == "input"]
    outs = [p for p in ports if p["dir"] == "output"]
    lines = [
        "",
        "Child-facing ports:",
        f"    {decl['child_module']} is instantiated as `{decl['instance']}` and is "
        "NOT implemented by this module. Its boundary is on this module's port "
        "list, so the ports below carry signals to and from it. Directions are "
        f"stated from {parent}'s side.",
        f"    {', '.join(decl.get('shared_domain', []))} are shared with "
        f"{decl['instance']} directly and are not repeated below.",
        "",
    ]
    if outs:
        lines.append(f"    Driven by {parent}, consumed by {decl['instance']}:")
        for p in outs:
            w = _width_text(p["width"])
            lines.append(f"        {p['glue']}{w}: drives {decl['instance']}.{p['child']}.")
    if ins:
        lines.append(f"    Driven by {decl['instance']}, consumed by {parent}:")
        for p in ins:
            w = _width_text(p["width"])
            lines.append(f"        {p['glue']}{w}: carries {decl['instance']}.{p['child']}.")
    if moved:
        lines.append("")
        lines.append(
            "    The signals below were listed above as internal wires. They "
            "cross the boundary to " + decl["instance"] + ", so they are ports "
            "of this module and are named as such:")
        for net, glue in moved:
            lines.append(f"        {net} is the port {glue}.")
    lines.append("")
    return out.rstrip("\n") + "\n" + "\n".join(lines)


# ------------------------------------------------------------------- audit
_INST = re.compile(
    r"\b(?P<module>\w+)\s+(?P<inst>\w+)\s*\((?P<body>[^;]*?)\)\s*;", re.S)
_CONN = re.compile(r"\.\s*(?P<port>\w+)\s*\(\s*(?P<net>[^)]*?)\s*\)")


def audit(task_dir: pathlib.Path, decl: dict) -> list[str]:
    """Compare the declaration against the golden RTL. REPORTS, never authors.

    Two independent halves, and they are reported apart because they are not
    equally available: the parent's instantiation says which net reaches which
    child port, and the child's own header says each port's direction and
    width. Where the child's RTL is absent -- or1200_sb_fifo is not in this
    repository -- that half comes back `unchecked`, which is a different
    statement from `agrees` and must not be read as one.
    """
    findings: list[str] = []
    parent_v = task_dir / f"{decl['parent']}.v"
    if not parent_v.is_file():
        return [f"UNCHECKED: no {parent_v.name} to audit against"]
    text = parent_v.read_text(encoding="utf-8", errors="ignore")

    inst_body = None
    for m in _INST.finditer(text):
        if (m.group("module") == decl["child_module"]
                and m.group("inst") == decl["instance"]):
            inst_body = m.group("body")
            break
    if inst_body is None:
        return [f"MISMATCH: no instantiation of {decl['child_module']} named "
                f"{decl['instance']} found in {parent_v.name}"]

    conns = {m.group("port"): m.group("net") for m in _CONN.finditer(inst_body)}
    declared = {p["child"]: p for p in decl["ports"]}
    shared = set(decl.get("shared_domain", []))

    for child_port, net in conns.items():
        if child_port in declared:
            want = declared[child_port]["parent_net"]
            if net != want:
                findings.append(
                    f"MISMATCH: {decl['instance']}.{child_port} is wired to "
                    f"{net!r}, declaration says {want!r}")
        elif net not in shared:
            findings.append(
                f"MISSING: {decl['instance']}.{child_port} (net {net!r}) crosses "
                f"the boundary and is neither declared nor in shared_domain")
    for child_port in declared:
        if child_port not in conns:
            findings.append(
                f"EXTRA: declaration names {decl['instance']}.{child_port}, which "
                f"the instantiation does not connect")

    # Half two: the child's own header, where it exists.
    child_v = next((p for p in DES.rglob(f"{decl['child_module']}.v")), None)
    if child_v is None:
        findings.append(
            f"UNCHECKED: {decl['child_module']}.v is not in this repository, so "
            "the declared directions and widths could not be confirmed against "
            "the child's own header")
    else:
        head = re.search(r"module\s+" + decl["child_module"] + r"\s*\((.*?)\)\s*;",
                         child_v.read_text(encoding="utf-8", errors="ignore"), re.S)
        body = head.group(1) if head else ""
        for p in decl["ports"]:
            pat = re.compile(
                r"\b(?P<dir>input|output)\b(?:\s+(?:reg|wire|logic))?"
                r"(?:\s*\[\s*(?P<hi>[^:\]]+):\s*(?P<lo>[^\]]+)\])?"
                r"\s+" + re.escape(p["child"]) + r"\b")
            m = pat.search(body)
            if not m:
                findings.append(f"UNCHECKED: {p['child']} not found in "
                                f"{decl['child_module']}'s header")
                continue
            # Inverted: a child input is a glue output.
            want_dir = "output" if m.group("dir") == "input" else "input"
            if want_dir != p["dir"]:
                findings.append(
                    f"MISMATCH: {p['glue']} is declared {p['dir']}, but "
                    f"{p['child']} is a child {m.group('dir')} so the glue side "
                    f"is {want_dir}")
            if m.group("hi") is not None:
                try:
                    width = int(m.group("hi").strip()) - int(m.group("lo").strip()) + 1
                except ValueError:
                    continue          # a parameterised width; not decidable here
                if width != int(p["width"]):
                    findings.append(
                        f"MISMATCH: {p['glue']} declared width {p['width']}, "
                        f"child header says {width}")
            elif int(p["width"]) != 1:
                findings.append(
                    f"MISMATCH: {p['glue']} declared width {p['width']}, child "
                    "header declares no range (width 1)")
    return findings


# -------------------------------------------------------------------- main
def emit(task_dir: pathlib.Path, decl: dict, dest_root: pathlib.Path) -> pathlib.Path:
    """Write a runnable task dir: glue-form spec plus the files scoring needs.

    Placed OUTSIDE `Des/` on purpose. `run_chipverilog.find_task` globs
    `Des/**/description.txt` and matches on the directory name, so a
    same-named copy under `Des/` would give two hits and the winner would be
    whichever `rglob` reached first -- a run silently using the wrapper spec
    while reporting the glue one.
    """
    dest = dest_root / decl["parent"]
    dest.mkdir(parents=True, exist_ok=True)
    spec = (task_dir / "description.txt").read_text(encoding="utf-8")
    (dest / "description.txt").write_text(render(spec, decl), encoding="utf-8")
    for extra in task_dir.iterdir():
        if extra.name != "description.txt" and extra.is_file():
            shutil.copy2(extra, dest / extra.name)
    return dest


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--task", required=True, help="parent module name")
    ap.add_argument("--check", action="store_true",
                    help="audit the declaration against the golden RTL and report")
    ap.add_argument("--emit", type=pathlib.Path,
                    help="write a runnable glue-form task dir under this root")
    ap.add_argument("--print", action="store_true", dest="show",
                    help="print the glue-form spec to stdout")
    args = ap.parse_args(argv)

    task_dir = find_task(args.task)
    decl = load_decl(args.task)
    spec = (task_dir / "description.txt").read_text(encoding="utf-8")
    glue = render(spec, decl)

    if args.check:
        findings = audit(task_dir, decl)
        print(f"=== audit: {args.task} ({len(decl['ports'])} child-facing ports) ===")
        if not findings:
            print("  every declared port agrees with the golden RTL")
        for f in findings:
            print(f"  {f}")
        if any(f.startswith(("MISMATCH", "MISSING", "EXTRA")) for f in findings):
            return 1
    if args.emit:
        dest = emit(task_dir, decl, args.emit)
        print(f"wrote {dest}/description.txt "
              f"(+{len(decl['ports'])} child-facing ports)")
    if args.show:
        print(glue)
    return 0


if __name__ == "__main__":
    sys.exit(main())
