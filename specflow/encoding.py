"""Symbolic values for a port, so nobody has to guess a number.

WHAT THIS FIXES. A specification names its command encoding by symbol --
`I2C_CMD_START`, `I2C_CMD_WRITE` -- and never states the numbers. The pipeline
needs numbers: an oracle's leaf comparison is `row["inputs"][port] == v` against
integers a simulator produced. Nothing owned the symbol-to-number step, so it
happened at the first stage that had to emit an integer, implicitly, as a guess,
with nothing recording that a guess was made.

Measured on c1-i2c's 122 normalized requirements, 45 of which key on a numeric
`cmd`. Every symbol contradicted itself across the corpus:

    START  true=1  used {1: 8, 4: 1}
    STOP   true=2  used {1: 6, 2: 5}
    WRITE  true=4  used {4: 14, 1: 2, 2: 1, 3: 1}
    READ   true=8  used {3: 6, 1: 2, 8: 4, 4: 1}

Seven requirements used `cmd=3`, which matches no arm of the design's `case` --
their windows can never open, and at decide time that is indistinguishable from
"the design never did it". The only gate that inspected a `cmd` value checked
that it fit in four bits, so 0 through 15 all passed.

It also propagates. In one run the correspondence reviewer took ANOTHER
requirement's wrong normalization as evidence, concluded "WRITE=3, READ=4",
rejected a CORRECT check, and the repair round wrote the illegal value in.

AND IT IS NOT ONLY OUR PROBLEM. ChipVerilog ships `i2c_master_defines.v` inside
the task package and auto-prepends it to every compile, so a candidate could
write `` `I2C_CMD_START `` and be right for free. None of the 15 generated
designs does; all re-declare the constants and 9 of 9 guess wrong, 8 of them
with READ and WRITE swapped -- because the description's prose orders them
"START, STOP, READ, WRITE" five times against its port list's one. The
ambiguity is in the specification, and every reader resolves it the same wrong
way. That is why the table belongs in an artifact rather than in a better
prompt.

WHAT MAY BE ADMITTED, and the rule is not "it was in a defines file". The test
is whether an EXTERNAL agent must know the value to drive the module correctly.
`cmd`'s encoding, yes -- the byte controller cannot function without it, and it
is as much interface as the port's width. An FSM state encoding, no: that is
implementation, and a requirement keyed on one is the internal-mechanism class
`NOT_ASSERTABLE` exists to route away.

TWO SELECTORS, AND THE PIPELINE USES THE SPEC ONE. `symbols_in_spec` picks the
symbols the SPECIFICATION names under a port -- i2c's `cmd` entry reads "this
field is decoded as one of the supported commands" and lists all four -- so the
spec chooses WHICH symbols belong to the port and the header supplies only their
VALUES. `referenced_by_decode` answers the same question from the RTL and is
kept for offline analysis, but it must not drive a contract: the golden design
is the scoring instrument and may not decide what a check looks at, even
indirectly.

WHY READING A DESIGN FILE IS NOT CONTAMINATION HERE, and exactly when it would
be. The golden RTL may not gate (`control_source=None`), so the question is
fair. It turns on DIRECTION OF FLOW, and the test is what happens to a wrong
candidate:

  - frozen as an INPUT, before any design exists -> a candidate that decodes the
    port differently FAILS, correctly: it violated the interface it was handed.
  - harvested from what a candidate EMITTED -> that candidate passes trivially.

Same file, opposite epistemics. So the table is recorded with the source path
and a content hash, and a design that redefines the constants is a finding, not
a new table.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

#: `define NAME 4'b0001 / 4'd8 / 4'h8, and the bare-decimal form.
_DEFINE = re.compile(
    r"^\s*`define\s+(?P<name>\w+)\s+"
    r"(?:(?P<width>\d+)\s*'\s*(?P<base>[bodhBODH])\s*(?P<digits>[0-9a-fA-FxXzZ_]+)"
    r"|(?P<dec>\d+))\s*(?://.*)?$",
    re.M,
)
_BASE = {"b": 2, "o": 8, "d": 10, "h": 16}


def parse_defines(text: str) -> dict[str, int]:
    """Every ``\\`define NAME <literal>`` whose value is a plain integer.

    A macro whose value carries x or z is skipped rather than guessed at: it is
    not a value a check could compare against.
    """
    out: dict[str, int] = {}
    for m in _DEFINE.finditer(text):
        if m.group("dec") is not None:
            out[m.group("name")] = int(m.group("dec"))
            continue
        digits = m.group("digits").replace("_", "")
        if re.search(r"[xXzZ]", digits):
            continue
        try:
            out[m.group("name")] = int(digits, _BASE[m.group("base").lower()])
        except ValueError:
            continue
    return out


def referenced_by_decode(rtl: str, port: str, names: set[str]) -> set[str]:
    """The subset of `names` the design's decode of `port` actually names.

    THIS IS THE ADMISSION RULE, and it is what keeps or1200's 611 defines --
    cache geometry, feature flags, `OR1200_NO_DC` -- out of a contract. A macro
    qualifies only where it is compared against the port or appears in a `case`
    on it, which is exactly "an external agent must know this to drive the
    module".

    Deliberately textual: it runs before any design is elaborated, and a
    parser-grade answer would not change which macros pass on any design here.
    """
    hits: set[str] = set()
    # `case (port) ... `NAME: ...`  -- take the body up to the matching endcase.
    for m in re.finditer(rf"\bcase[xz]?\s*\(\s*{re.escape(port)}\s*\)", rtl):
        body = rtl[m.end():]
        end = body.find("endcase")
        for n in names:
            if re.search(rf"`{re.escape(n)}\b", body[:end if end >= 0 else len(body)]):
                hits.add(n)
    # `port == `NAME` / `` `NAME == port ``
    for n in names:
        if re.search(rf"\b{re.escape(port)}\s*[=!]=+\s*`{re.escape(n)}\b", rtl) or \
           re.search(rf"`{re.escape(n)}\s*[=!]=+\s*\b{re.escape(port)}\b", rtl):
            hits.add(n)
    return hits


def _family(names: set[str]) -> str:
    """The shared `PREFIX_` two or more referenced symbols belong to.

    THE DECODE IS NOT THE WHOLE ENUMERATION, and taking it for one is a bug this
    caught before shipping. i2c's `case (cmd)` has arms for START, STOP, WRITE
    and READ; `I2C_CMD_NOP` is defined, is a perfectly legal value of the port,
    and has no arm -- it falls to the default. Admitting only what the case
    names and then calling the space CLOSED would reject `cmd=0`, which is
    exactly the kind of false rejection this module exists to prevent.

    So a referenced symbol pulls in its siblings: same file, same `PREFIX_`.
    That is the enumeration the specification's own symbol names describe.
    Requires TWO references, because one symbol's prefix is a guess about a
    family rather than evidence of one.
    """
    if len(names) < 2:
        return ""
    parts = [n.rsplit("_", 1)[0] for n in names]
    if len(set(parts)) != 1 or not parts[0]:
        return ""
    return parts[0] + "_"


def extract_port_encoding(*, defines_text: str, rtl: str, port: str,
                          source: str) -> dict | None:
    """The `encoding` block for one port, or None when nothing qualifies.

    `complete` says the value space is CLOSED -- every value the port may
    meaningfully take is named here -- which is what lets a gate reject a value
    like 3 that no arm decodes. It is claimed only when the decode is a `case`
    on the port, because a scattering of `==` comparisons is evidence about the
    values named and no evidence at all about the ones that are not.
    """
    defines = parse_defines(defines_text)
    if not defines:
        return None
    used = referenced_by_decode(rtl, port, set(defines))
    if not used:
        return None
    prefix = _family(used)
    admitted = set(used)
    if prefix:
        admitted |= {n for n in defines if n.startswith(prefix)}
    cased = bool(re.search(rf"\bcase[xz]?\s*\(\s*{re.escape(port)}\s*\)", rtl))
    return {
        "encoding": {n: defines[n] for n in sorted(admitted)},
        "encoding_complete": cased,
        "encoding_source": {
            "file": source,
            "sha256": hashlib.sha256(defines_text.encode("utf-8")).hexdigest(),
        },
    }


def encoding_for(contract: dict, port: str) -> tuple[dict[str, int], bool]:
    """`(symbol -> value, complete)` for one port. `({}, False)` when absent.

    Absent is the default and must stay inert: every design without a shared
    constants header, and every artifact predating this module, has to behave
    exactly as it did.
    """
    for p in (contract.get("io") or []):
        if p.get("name") == port:
            table = p.get("encoding") or {}
            if not isinstance(table, dict):
                return {}, False
            return ({k: v for k, v in table.items() if isinstance(v, int)},
                    bool(p.get("encoding_complete")))
    return {}, False


def resolve(port: str, value, contract: dict) -> tuple[int | None, str]:
    """One value to an integer, with a sentence when it cannot be.

    Returns `(None, why)` on failure. A string is ALWAYS looked up as a symbol,
    never parsed as a number: `"4"` is a mistake worth a message, not a value
    worth guessing at.
    """
    table, complete = encoding_for(contract, port)
    if isinstance(value, str):
        if value in table:
            return table[value], ""
        if not table:
            return None, (f"{port}={value!r} is a symbol, but {port} declares no "
                          f"encoding, so there is nothing to resolve it against")
        return None, (f"{port}={value!r} is not one of its declared symbols "
                      f"({', '.join(sorted(table))})")
    try:
        as_int = int(value)
    except Exception:  # noqa: BLE001
        return None, f"{port}={value!r} is not an integer"
    if table and complete and as_int not in set(table.values()):
        legal = ", ".join(f"{n}={v}" for n, v in sorted(table.items(), key=lambda kv: kv[1]))
        return None, (f"{port}={as_int} is not one of the values {port} is "
                      f"decoded as ({legal}). A value no arm decodes gives a "
                      f"window that can never open, which reads at decide time "
                      f"exactly like a design that never did it")
    return as_int, ""


def resolve_any(port: str, value, contract: dict) -> tuple[tuple[int, ...] | None, str]:
    """One value OR a value-set to the integers it admits.

    A list means ANY OF THESE, so `{"cmd": ["I2C_CMD_START", "I2C_CMD_STOP"]}`
    resolves to `(1, 2)` and the activation opens on either. A scalar resolves
    to a 1-tuple, so every caller downstream handles one shape.

    WHY THE SET EXISTS. `Activation.inputs` is a mapping port -> value, which
    makes it a CONJUNCTION: every named port must hold together. `opens_on`,
    `until` and `aborts_on` all took the list-of-alternatives shape long ago
    for exactly this reason, and `inputs` was the last field that could not say
    "any of". Measured on h2-i2c: of 22 observable requirements whose
    activation carried no trigger at all, 8 had a DISJUNCTIVE one -- "a START,
    STOP, READ, or WRITE command is accepted while the FSM is idle" -- which
    the model wrote into `text`, where no gate and no oracle can reach it. A
    trigger stated only in prose is a trigger the pipeline does not have.

    Returns `(None, why)` if ANY alternative fails to resolve, because a set
    with one bad member is a set whose membership test is wrong, and silently
    dropping the bad one would widen or narrow the window without saying so.
    """
    if isinstance(value, (list, tuple, set)):
        alts = list(value)
        if not alts:
            return None, (f"{port}=[] is an empty value-set, which no value can "
                          f"satisfy. Give the values that open the window, or "
                          f"drop the port")
        out: list[int] = []
        for v in alts:
            as_int, why = resolve(port, v, contract)
            if as_int is None:
                return None, why
            out.append(as_int)
        # Order is not meaningful in a set, and a duplicate is not an error --
        # it is the same alternative said twice.
        return tuple(sorted(set(out))), ""
    as_int, why = resolve(port, value, contract)
    return (None, why) if as_int is None else ((as_int,), "")


def symbol_for(port: str, value: int, contract: dict) -> str:
    """The symbol a value stands for, or "" -- for reporting, never for gating."""
    table, _ = encoding_for(contract, port)
    for name, v in sorted(table.items()):
        if v == value:
            return name
    return ""


def annotate(inputs: dict, contract: dict) -> dict[str, int | list[int]]:
    """`{port: value}` with every symbol resolved; unresolvable entries dropped.

    The DROP is deliberate and the gate is what reports it. This function is
    used to build the numeric form the author writes against, and an entry it
    could not resolve has no number to offer -- inventing one is the whole
    defect this module exists to remove.
    """
    out: dict[str, int | list[int]] = {}
    for port, value in (inputs or {}).items():
        vals, _ = resolve_any(port, value, contract)
        if not vals:
            continue
        # A 1-tuple renders as the bare number it was written as. Wrapping every
        # scalar in a list would change what every existing author sees for no
        # gain, and the numeric form is what the author writes comparisons
        # against.
        out[port] = vals[0] if len(vals) == 1 else list(vals)
    return out


#: A port entry in a prose port list: `name`, an optional `[15:0]`, then a colon.
_PORT_ENTRY = re.compile(r"^\s*(\w+)\s*(?:\[[^\]]*\])?\s*:", re.M)


def symbols_in_spec(spec: str, port: str, names: set[str]) -> set[str]:
    """The macro names the SPECIFICATION associates with this port.

    THE SELECTOR THE PIPELINE USES, and it deliberately does not read a design.
    `referenced_by_decode` answers the same question from the RTL, which is fine
    for offline analysis but wrong here: the golden design is the scoring
    instrument and may not decide what a check looks at, even indirectly. The
    specification already answers it -- i2c's `cmd` entry reads "this field is
    decoded as one of the supported commands" and then lists all four -- so the
    spec picks WHICH symbols belong to the port and the header supplies only
    their VALUES. `source_of_truth: "spec"` survives the selection intact.
    """
    m = next((m for m in _PORT_ENTRY.finditer(spec) if m.group(1) == port), None)
    if m is None:
        return set()
    nxt = _PORT_ENTRY.search(spec, m.end())
    para = spec[m.end():nxt.start() if nxt else len(spec)]
    return {n for n in names if re.search(rf"\b{re.escape(n)}\b", para)}


def find_defines(*roots: Path) -> list[Path]:
    """Shared constants headers beside a design: `*defines*.v`, `*defs*.v`.

    The same rule ChipVerilog's own harness uses to decide what to prepend to
    every compile (`prefix_files_for_family`), which is why a candidate could
    write `` `I2C_CMD_START `` and be correct for free -- and why the values are
    interface rather than implementation.
    """
    out: list[Path] = []
    for root in roots:
        if root is None:
            continue
        d = Path(root)
        d = d if d.is_dir() else d.parent
        for cand in (d, d.parent):
            if not cand.is_dir():
                continue
            for p in sorted(cand.glob("*.v")):
                low = p.name.lower()
                if ("defines" in low or "defs" in low) and p not in out:
                    out.append(p)
    return out


def enrich_contract(contract: dict, *, spec: str, defines: list[Path]) -> list[str]:
    """Attach an `encoding` to every port the spec names symbols for.

    Mutates `contract` and returns one line per port enriched, for the log. A
    no-op when no header is found or the spec names no symbols, which is the
    inert default every design without a shared header keeps.
    """
    if not defines:
        return []
    table: dict[str, int] = {}
    provenance: list[dict] = []
    for path in defines:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        parsed = parse_defines(text)
        if not parsed:
            continue
        table.update(parsed)
        provenance.append({"file": path.name,
                           "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()})
    if not table:
        return []

    notes: list[str] = []
    for port in (contract.get("io") or []):
        name = str(port.get("name") or "")
        if not name or port.get("encoding"):
            continue
        named = symbols_in_spec(spec, name, set(table))
        if len(named) < 2:
            # One symbol is a mention, not an enumeration, and calling the value
            # space closed off a single name would reject every other value the
            # port legitimately takes.
            continue
        prefix = _family(named)
        admitted = set(named) | ({n for n in table if n.startswith(prefix)}
                                 if prefix else set())
        port["encoding"] = {n: table[n] for n in sorted(admitted)}
        # The SPEC listed them as the values this field is decoded as, so the
        # space is closed. That is what lets the gate reject a value no symbol
        # names -- the seven `cmd=3` requirements on c1-i2c.
        port["encoding_complete"] = True
        port["encoding_source"] = provenance if len(provenance) > 1 else provenance[0]
        notes.append(f"{name}: {len(port['encoding'])} symbols from "
                     f"{provenance[0]['file']}")
    return notes
