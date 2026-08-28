"""`eda_agent` may not import `specflow`, and arm A is why.

Arm A -- `benchmarks/make_arm_a.sh` -- is the merge-base tree with specflow
DELETED, plus `config.py` and `model.py` taken whole from HEAD. So any import
of specflow that reaches those two files is a `ModuleNotFoundError` on arm A's
first model call, and arm A is the baseline half of every published comparison.

This happened. A shared usage reader was placed in `specflow.cache_stats` --
reasonably, since that module already knew both API shapes -- and `model.py`
imported it. Arm A died with `No module named 'specflow'` before producing a
byte of RTL, and, per the leaf handler, still exited 0.

The dependency runs one way: specflow imports eda_agent in a dozen places and
never the reverse.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]

#: The files `make_arm_a.sh` copies from HEAD into a specflow-less tree. These
#: are the ones where a specflow import is FATAL rather than merely wrong.
CARRIED_TO_ARM_A = ("eda_agent/config.py", "eda_agent/model.py")


def _imports(path: pathlib.Path) -> set[str]:
    """Every module imported, including inside functions -- a deferred import
    fails just as hard, only later and with the run already part-way in."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            out.add(node.module.split(".")[0])
    return out


@pytest.mark.parametrize("rel", CARRIED_TO_ARM_A)
def test_a_file_carried_into_arm_a_never_imports_specflow(rel):
    got = _imports(REPO / rel)
    assert "specflow" not in got, (
        f"{rel} is copied into arm A, which has no specflow/. "
        f"Put the shared code in this file or another arm A already carries.")


def test_the_carried_list_matches_what_make_arm_a_actually_copies():
    """A pin on the pin: if the script starts carrying another file, this test
    must start guarding it, or the guard silently covers the wrong set."""
    script = (REPO / "benchmarks" / "make_arm_a.sh").read_text(encoding="utf-8")
    for rel in CARRIED_TO_ARM_A:
        assert rel in script, f"{rel} is no longer copied by make_arm_a.sh"
