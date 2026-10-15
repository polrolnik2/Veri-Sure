"""Pins for the glue-form spec renderer.

The load-bearing ones are the two that make the experiment mean what it says:
NO glue prose is added (so a result is attributable to the ports alone), and
the header and the internal-signal list never disagree about the same net.
"""

from __future__ import annotations

import json
import pathlib

import pytest

from benchmarks import glue_spec

REPO = pathlib.Path(__file__).resolve().parents[1]
TASKS = ("i2c_master_byte_ctrl", "or1200_sb")


def _decl(task: str) -> dict:
    return json.loads((REPO / "benchmarks" / "glue" / f"{task}.json")
                      .read_text(encoding="utf-8"))


def _spec(task: str) -> str:
    return (glue_spec.find_task(task) / "description.txt").read_text(encoding="utf-8")


@pytest.mark.parametrize("task", TASKS)
def test_every_child_facing_port_reaches_the_header(task: str) -> None:
    decl = _decl(task)
    out = glue_spec.render(_spec(task), decl)
    header = out.split(");", 1)[0]
    for port in decl["ports"]:
        assert port["glue"] in header, f"{port['glue']} missing from the prototype"


@pytest.mark.parametrize("task", TASKS)
def test_directions_are_stated_from_the_glue_side(task: str) -> None:
    """A child INPUT is a glue OUTPUT. Getting this backwards is the whole bug."""
    decl = _decl(task)
    out = glue_spec.render(_spec(task), decl)
    for port in decl["ports"]:
        verb = "drives" if port["dir"] == "output" else "carries"
        assert f"{port['glue']}" in out
        assert f"{verb} {decl['instance']}.{port['child']}." in out


@pytest.mark.parametrize("task", TASKS)
def test_no_net_is_both_a_port_and_an_internal_wire(task: str) -> None:
    """The header and the signal list must not contradict each other.

    or1200_sb declares all six FIFO nets as internal wires; once they are
    ports, leaving those lines in place is the same two-readings hazard that a
    stripped `output` keyword creates.
    """
    decl = _decl(task)
    out = glue_spec.render(_spec(task), decl)
    body = out.split("Internal reg/wire signals:", 1)
    if len(body) == 1:
        return                       # this spec has no internal-signal section
    listing = body[1].split("\n\n", 1)[0]
    for port in decl["ports"]:
        for line in listing.splitlines():
            assert not glue_spec._INTERNAL_DECL.match(line) or \
                glue_spec._INTERNAL_DECL.match(line).group("net") != port["parent_net"], \
                f"{port['parent_net']} is a port and still listed as internal"


@pytest.mark.parametrize("task", TASKS)
def test_no_glue_vocabulary_is_introduced(task: str) -> None:
    """THE EXPERIMENT'S CONTROL. The user asked for ports, not instruction.

    `child_assumes` in particular is what `_is_composition_contract` keys on,
    so the word appearing here would switch on the whole glue prompt set and a
    result would stop being attributable to the ports.
    """
    out = glue_spec.render(_spec(task), _decl(task)).lower()
    for banned in ("child_assumes", "vestigial", "composition module",
                   "do not reimplement", "glue module"):
        assert banned not in out, f"{banned!r} leaked into the spec"


@pytest.mark.parametrize("task", TASKS)
def test_the_spec_body_is_otherwise_untouched(task: str) -> None:
    """Only the header and the signal list change; the PROSE is the control.

    Paragraphs holding a port list or a signal declaration are excluded --
    those are exactly what this module edits, and an earlier version of this
    test flagged one of them, which is the test being wrong rather than the
    renderer.
    """
    spec = _spec(task)
    out = glue_spec.render(spec, _decl(task))
    prose = [
        para for para in spec.split("\n\n")
        if len(para) > 400
        and "ports:" not in para.lower()
        and not any(glue_spec._INTERNAL_DECL.match(ln) for ln in para.splitlines())
    ]
    assert prose, "no prose paragraph found; the test would pass vacuously"
    for para in prose:
        assert para in out, "a prose paragraph was altered or dropped"


def test_a_missing_prototype_is_an_error_not_a_silent_passthrough() -> None:
    """Returning the spec unchanged would silently be the WRAPPER reading."""
    with pytest.raises(SystemExit):
        glue_spec.render("no prototype here", _decl("or1200_sb"))


@pytest.mark.parametrize("task", TASKS)
def test_declaration_agrees_with_the_golden_rtl(task: str) -> None:
    """The audit is evidence, so it runs in CI rather than by hand.

    `UNCHECKED` is tolerated and MISMATCH/MISSING/EXTRA are not: or1200_sb_fifo
    is not in this repository, so half that audit cannot run, and reporting
    that is different from asserting agreement.
    """
    decl = _decl(task)
    findings = glue_spec.audit(glue_spec.find_task(task), decl)
    bad = [f for f in findings if f.startswith(("MISMATCH", "MISSING", "EXTRA"))]
    assert not bad, "\n".join(bad)
