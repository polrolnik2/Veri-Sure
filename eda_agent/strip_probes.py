"""Remove probe ports before the design is handed on.

A probe is a port of the generated module -- that is the point of it, because
`asserter.py` and the boolean miter both skip a non-port direction, so an
assertion that ships has nowhere to attach otherwise. But the module that ships
must be black-box: golden RTL has no probes, and a design carrying extra outputs
is not the design the specification describes.

So they are stripped, and "stripping changed nothing" is a CHECKED FACT rather
than an assumption. That is the one place probes could silently alter the shipped
design: a probe assigned from a signal is inert, but a probe an author wired INTO
a real output changes behaviour, and removing it then changes behaviour back.
`traces_agree` is the pin, and the fixture deliberately includes a wired probe so
the pin can be shown to fail.

Verilog is parsed here with regular expressions, which is normally wrong. It is
defensible for exactly this shape: the names come from the contract, so they are
known exactly rather than discovered, and every edit is anchored on one of them.
Anything that cannot be matched confidently is LEFT IN PLACE and reported --
shipping a probe is a visible defect the equivalence check will catch, while
deleting the wrong line silently is not.
"""

from __future__ import annotations

import re


def _port_pattern(name: str) -> re.Pattern:
    """A port declaration for `name`, in either Verilog-2001 or -1995 style."""
    return re.compile(
        r"(?:^|(?<=[,(\s]))\s*(?:output|input|inout)\b[^,;)]*?\b"
        + re.escape(name) + r"\b\s*(?=[,;)])", re.M)


def _driver_pattern(name: str) -> re.Pattern:
    """A continuous assignment or always-block assignment TO `name`."""
    return re.compile(
        r"^[ \t]*(?:assign\s+)?" + re.escape(name)
        + r"\s*(?:<=|=)[^;]*;[ \t]*\n?", re.M)


def strip_probes(rtl: str, probes: list[str]) -> tuple[str, list[str]]:
    """Return `(rtl without the probes, names that could not be removed)`.

    Removes the port from the header and any statement whose only job is to
    drive it. A probe read by something else is NOT removed -- it is reported,
    because taking away a signal another line depends on produces RTL that does
    not compile, and a confusing compile error is worse than a visible extra
    port.
    """
    out = rtl
    left: list[str] = []
    for name in probes or []:
        if not name:
            continue
        # Read anywhere other than its own declaration or its own driver?
        without_decl = _port_pattern(name).sub("", out)
        without_driver = _driver_pattern(name).sub("", without_decl)
        if re.search(r"\b" + re.escape(name) + r"\b", without_driver):
            left.append(name)
            continue
        if without_decl == out:
            # The port was never declared under that name -- say so rather than
            # reporting a successful removal of nothing.
            left.append(name)
            continue
        out = without_driver
    # A header that ended up with a dangling comma or an empty port slot.
    out = re.sub(r",(\s*)\)", r"\1)", out)
    out = re.sub(r"\(\s*,", "(", out)
    out = re.sub(r",\s*,", ",", out)
    return out, left


def traces_agree(before: dict, after: dict, real_ports: list[str]) -> list[str]:
    """THE PIN: the stripped module behaves identically on its REAL ports.

    `before` and `after` map a testpoint to its recorded rows. Returns the
    differing `(testpoint, edge, port)` triples as strings, empty when the strip
    changed nothing observable.

    This is what makes "probes are removed before handoff" a fact. A probe that
    is merely assigned from existing state is inert and this returns nothing; a
    probe an author wired into a real output changes the design, and this says
    which port at which edge.
    """
    bad: list[str] = []
    for tp in sorted(set(before) | set(after)):
        rows_b = before.get(tp) or []
        rows_a = after.get(tp) or []
        if len(rows_b) != len(rows_a):
            bad.append(f"{tp}: {len(rows_b)} rows before, {len(rows_a)} after")
            continue
        for i, (rb, ra) in enumerate(zip(rows_b, rows_a)):
            ob, oa = (rb.get("outputs") or {}), (ra.get("outputs") or {})
            for port in real_ports:
                if ob.get(port) != oa.get(port):
                    bad.append(f"{tp} edge {i} {port}: "
                               f"{ob.get(port)!r} -> {oa.get(port)!r}")
    return bad
